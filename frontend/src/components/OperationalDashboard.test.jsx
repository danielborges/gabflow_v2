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
        metricasOperacionais: {
          tempoMedioPrimeiraRespostaHoras: 2.5,
          tempoMedioPrimeiroEncaminhamentoHoras: 4,
          tempoMedioEncerramentoHoras: null,
          tempoMedioResolucaoHoras: null,
          primeirasRespostasRegistradas: 2,
          encaminhamentosRegistrados: 1,
          encerramentosRegistrados: 0,
          resolucoesRegistradas: 0,
          reaberturas: 1,
        },
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
          metodo: "POSTGIS",
          coberturaPercentual: 50,
          geocodificadas: 1,
          semCoordenadas: 1,
          hotspots: [{ nome: "Centro", total: 2, abertas: 2, atrasadas: 1 }],
          heatmap: [{
            territorio: "Centro",
            latitude: -21.7619,
            longitude: -43.3496,
            total: 2,
            abertas: 2,
            raioMetros: 1000,
          }],
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
    expect(screen.getByText("Métricas operacionais")).toBeInTheDocument();
    expect(screen.getByText("Primeira resposta")).toBeInTheDocument();
    expect(screen.getByText("2,5 h")).toBeInTheDocument();
    expect(screen.getByText("Reaberturas")).toBeInTheDocument();
    expect(screen.getByText("Inteligência territorial")).toBeInTheDocument();
    expect(screen.getByText("PostGIS ativo")).toBeInTheDocument();
    expect(screen.getByText("Mapa de calor")).toBeInTheDocument();
    expect(screen.getByLabelText("Mapa visual de calor territorial")).toBeInTheDocument();
    expect(screen.getByText("2 demanda(s)")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("GF-2026-000001")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Geocodificar/ }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/painel/territorial/geocodificar",
      { method: "POST" },
    ));
  });
});
