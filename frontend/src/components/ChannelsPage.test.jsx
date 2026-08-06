import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { ChannelsPage } from "./ChannelsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const pendingReview = {
  id: "review-1",
  status: "PENDENTE",
  estadoResolucao: "CORRESPONDENCIA_UNICA",
  criterios: ["CONTATO_EXATO"],
  mensagem: {
    id: "message-1",
    canal: "EMAIL",
    remetenteNome: "Ana",
    remetenteContatoMascarado: "a***@example.org",
    assunto: "Iluminação",
    conteudo: "Há um poste apagado próximo à minha residência.",
    recebidaEm: "2026-08-06T12:00:00Z",
  },
  candidatos: [{ id: "citizen-1", nome: "Ana Cidadã", nomeSocial: null, vip: false }],
  revisadoPor: null,
  revisadaEm: null,
};

describe("ChannelsPage assisted identity review", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/canais/mensagens") return Promise.resolve({ content: [] });
      if (path === "/api/v1/canais/revisoes-identidade?status=PENDENTE") {
        return Promise.resolve({ content: [pendingReview] });
      }
      if (options.method === "POST" && path.endsWith("/decisao")) {
        return Promise.resolve({ ...pendingReview, status: "VINCULADA" });
      }
      return Promise.resolve({ content: [] });
    });
  });

  it("exige revisão humana e vincula somente após ação explícita", async () => {
    render(<ChannelsPage />);

    expect(await screen.findByText("Ana Cidadã")).toBeInTheDocument();
    expect(screen.getByText("Nenhum cidadão é criado ou mesclado automaticamente.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Vincular cidadão" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/canais/revisoes-identidade/review-1/decisao",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ decisao: "VINCULAR", cidadaoId: "citizen-1" }),
      }),
    ));
  });

  it("abre o cadastro assistido sem criar cidadão automaticamente", async () => {
    const onStartAssistedRegistration = vi.fn();
    render(<ChannelsPage user={{ role: "staff" }} onStartAssistedRegistration={onStartAssistedRegistration} />);

    await screen.findByText("Ana Cidadã");
    fireEvent.click(screen.getByRole("button", { name: "Preparar novo cadastro" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/canais/revisoes-identidade/review-1/preparar-cadastro",
      { method: "POST" },
    ));
    expect(onStartAssistedRegistration).toHaveBeenCalledWith("review-1");
    expect(apiRequest).not.toHaveBeenCalledWith(
      "/api/v1/cidadaos",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
