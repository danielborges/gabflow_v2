import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { OperationalDashboard } from "./OperationalDashboard";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("OperationalDashboard", () => {
  it("exibe indicadores e a fila prioritária", async () => {
    apiRequest.mockResolvedValue({
      indicadores: {
        abertas: 3,
        atrasadas: 1,
        proximasDoPrazo: 1,
        semResponsavel: 2,
        aguardandoOrgao: 1,
        tarefasPendentes: 4,
      },
      porStatus: [
        { nome: "NOVA", total: 2 },
        { nome: "AGUARDANDO_CIDADAO", total: 1 },
      ],
      porCategoria: [{ nome: "Saúde", total: 2 }],
      porTerritorio: [{ nome: "Centro", total: 1 }],
      filaPrioritaria: [{
        id: "1",
        protocolo: "GF-2026-000001",
        titulo: "Demanda urgente",
        status: "NOVA",
        prazo: null,
        atrasada: true,
      }],
    });
    render(<OperationalDashboard onOpenRequests={() => {}} />);
    await waitFor(() => expect(screen.getByText("Demanda urgente")).toBeInTheDocument());
    expect(screen.getByText("Atrasadas")).toBeInTheDocument();
    expect(screen.getByText("Centro")).toBeInTheDocument();
    expect(screen.getByText("Nova")).toBeInTheDocument();
    expect(screen.getByText("Aguardando cidadão")).toBeInTheDocument();
    expect(screen.queryByText("AGUARDANDO_CIDADAO")).not.toBeInTheDocument();
  });
});
