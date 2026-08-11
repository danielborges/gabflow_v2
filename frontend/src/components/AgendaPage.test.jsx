import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiDownload, apiRequest } from "../api";
import { AgendaPage } from "./AgendaPage";

vi.mock("../api", () => ({ apiRequest: vi.fn(), apiDownload: vi.fn() }));
vi.mock("./GooglePlaceAutocompleteInput", () => ({
  GooglePlaceAutocompleteInput: ({ value, onChange, inputProps }) => <input {...inputProps} value={value} onChange={(event) => onChange(event.target.value)} />,
}));

describe("AgendaPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-08-11T12:00:00-03:00"));
    apiRequest.mockImplementation(async (path, options = {}) => {
      if (path === "/api/v1/agenda/compromissos" && options.method === "POST") return { id: "event-2" };
      if (path === "/api/v1/agenda/compromissos/event-1" && options.method === "PATCH") return { id: "event-1" };
      if (path === "/api/v1/agenda/compromissos") return { content: [{ id: "event-1", tipo: "REUNIAO", status: "AGENDADO", titulo: "Reunião estratégica", descricao: "Planejamento semanal", local: "Gabinete", inicio: "2026-08-11T14:00:00-03:00", fim: "2026-08-11T15:00:00-03:00", presencaParlamentar: true, participantes: [{ id: "staff-1", nome: "Assessora de Agenda", perfil: "staff" }], pendencias: [] }] };
      if (path === "/api/v1/agenda/participantes") return { content: [{ id: "staff-1", nome: "Assessora de Agenda", perfil: "staff" }, { id: "admin-1", nome: "Chefe de Gabinete", perfil: "admin" }] };
      if (path === "/api/v1/agenda/roteiros-visita") return { content: [{ territorioId: "territory-1", territorio: "Centro", totalDemandas: 4 }] };
      if (path === "/api/v1/admin/jurisdicao") return { limites: null };
      return {};
    });
    apiDownload.mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("oferece visões de calendário e cria compromisso com presença e múltiplos participantes", async () => {
    render(<AgendaPage />);

    expect(await screen.findByRole("button", { name: /Reunião estratégica/ })).toHaveClass("with-representative");
    expect(screen.getByRole("button", { name: "Dia" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Semana" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mês" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Compromisso" }));
    const dialog = screen.getByRole("dialog", { name: "Adicionar à agenda" });
    fireEvent.change(within(dialog).getByPlaceholderText("Adicionar título"), { target: { value: "Audiência com secretarias" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Presença do Parlamentar/i }));
    fireEvent.focus(within(dialog).getByRole("combobox", { name: "Participantes" }));
    fireEvent.click(await screen.findByRole("option", { name: /Assessora de Agenda/i }));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.focus(within(dialog).getByRole("combobox", { name: "Participantes" }));
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Salvar compromisso" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/agenda/compromissos",
      expect.objectContaining({ method: "POST" }),
    ));
    const createCall = apiRequest.mock.calls.find(([path, options]) => path === "/api/v1/agenda/compromissos" && options?.method === "POST");
    const payload = JSON.parse(createCall[1].body);
    expect(payload).toEqual(expect.objectContaining({
      titulo: "Audiência com secretarias",
      presencaParlamentar: true,
      participanteIds: ["staff-1"],
    }));
  });

  it("edita um compromisso e recalcula o fim para uma hora depois do início", async () => {
    render(<AgendaPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Reunião estratégica/ }));
    fireEvent.click(screen.getByRole("button", { name: "Editar compromisso" }));

    const dialog = screen.getByRole("dialog", { name: "Atualizar compromisso" });
    const startsAt = within(dialog).getByLabelText("Início");
    const endsAt = within(dialog).getByLabelText("Fim");
    fireEvent.change(startsAt, { target: { value: "2026-08-13T09:30" } });
    expect(endsAt).toHaveValue("2026-08-13T10:30");
    fireEvent.change(within(dialog).getByPlaceholderText("Adicionar título"), { target: { value: "Reunião estratégica atualizada" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/agenda/compromissos/event-1",
      expect.objectContaining({ method: "PATCH" }),
    ));
    const updateCall = apiRequest.mock.calls.find(([path, options]) => path === "/api/v1/agenda/compromissos/event-1" && options?.method === "PATCH");
    const updatePayload = JSON.parse(updateCall[1].body);
    expect(updatePayload.titulo).toBe("Reunião estratégica atualizada");
    expect(new Date(updatePayload.fim).getTime() - new Date(updatePayload.inicio).getTime()).toBe(60 * 60 * 1000);
  });
});
