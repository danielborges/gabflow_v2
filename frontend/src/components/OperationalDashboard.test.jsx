import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { OperationalDashboard } from "./OperationalDashboard";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("OperationalDashboard", () => {
  it("exibe indicadores, fila prioritária e inteligência territorial", async () => {
    apiRequest.mockImplementation(async (path, options = {}) => {
      if (path === "/api/v1/painel/territorial/geocodificar" && options.method === "POST") {
        return { geocodificadas: 1, pendentes: 0, metodo: "LOCAL_APROXIMADO" };
      }
      return {
        indicadores: {
          abertas: 3,
          atrasadas: 1,
          proximasDoPrazo: 1,
          semResponsavel: 2,
          aguardandoOrgao: 1,
          tarefasPendentes: 4,
          retornosVencidos: 0,
          retornosProximos: 0,
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
        retornosPrioritarios: [],
        territorial: {
          coberturaPercentual: 50,
          geocodificadas: 1,
          semCoordenadas: 1,
          hotspots: [{ nome: "Centro", total: 2, abertas: 2, atrasadas: 1 }],
          pontos: [{
            id: "1",
            protocolo: "GF-2026-000001",
            titulo: "Demanda urgente",
            status: "NOVA",
            categoria: "Saúde",
            territorio: "Centro",
            latitude: -21.7619,
            longitude: -43.3496,
            atrasada: true,
          }],
        },
      };
    });

    render(<OperationalDashboard onOpenRequests={() => {}} />);
    await waitFor(() => expect(screen.getByText("Demanda urgente")).toBeInTheDocument());
    expect(screen.getByText("Atrasadas")).toBeInTheDocument();
    expect(screen.getAllByText("Centro").length).toBeGreaterThan(0);
    expect(screen.getByText("Nova")).toBeInTheDocument();
    expect(screen.getByText("Aguardando cidadão")).toBeInTheDocument();
    expect(screen.queryByText("AGUARDANDO_CIDADAO")).not.toBeInTheDocument();
    expect(screen.getByText("Inteligência territorial")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("GF-2026-000001")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Geocodificar/ }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/painel/territorial/geocodificar",
      { method: "POST" },
    ));
  });
});
