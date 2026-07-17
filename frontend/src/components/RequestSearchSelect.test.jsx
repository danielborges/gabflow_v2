import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { RequestSearchSelect } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const requests = [
  {
    id: "current-request",
    protocolo: "SOL-2026-001",
    titulo: "Solicitação atual",
    status: "NOVA",
  },
  {
    id: "related-request",
    protocolo: "SOL-2026-014",
    titulo: "Iluminação apagada na Rua das Flores",
    status: "EM_ATENDIMENTO",
  },
];

describe("RequestSearchSelect", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ content: requests });
  });

  it("consulta a API e exclui a solicitação que está sendo editada", async () => {
    render(
      <RequestSearchSelect
        value=""
        excludeId="current-request"
        onChange={vi.fn()}
      />,
    );

    fireEvent.focus(screen.getByRole("combobox", { name: "Solicitação relacionada" }));

    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith("/api/v1/solicitacoes?size=8");
    });
    expect(screen.queryByText("Solicitação atual")).not.toBeInTheDocument();
    expect(screen.getByText("Iluminação apagada na Rua das Flores")).toBeInTheDocument();
  });

  it("busca por texto e seleciona um resultado", async () => {
    const onChange = vi.fn();
    render(
      <RequestSearchSelect
        value=""
        excludeId="current-request"
        onChange={onChange}
      />,
    );

    const input = screen.getByRole("combobox", { name: "Solicitação relacionada" });
    fireEvent.change(input, { target: { value: "Rua das Flores" } });

    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/v1/solicitacoes?size=8&q=Rua+das+Flores",
      );
    });
    fireEvent.click(screen.getByRole("option"));

    expect(onChange).toHaveBeenCalledWith("related-request");
    expect(input).toHaveValue(
      "SOL-2026-014 · Iluminação apagada na Rua das Flores",
    );
    expect(input).toHaveAttribute("aria-expanded", "false");
  });
});
