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
      if (path.startsWith("/api/v1/painel/relatorio-mensal")) {
        return {
          periodo: { ano: 2026, mes: 7, inicio: "2026-07-01", fim: "2026-07-31", rotulo: "07/2026" },
          resumo: {
            solicitacoesRecebidas: 5,
            solicitacoesMovimentadas: 6,
            encaminhadas: 3,
            resolvidasOuEncerradas: 2,
            emAbertoAoFimDoMes: 4,
            atrasadasAoFimDoMes: 1,
          },
          indicadores: {
            porCategoria: [{ nome: "Saúde", total: 3 }],
            porTerritorio: [{ nome: "Centro", total: 3 }],
            porOrgao: [{ nome: "Secretaria de Saúde", total: 3 }],
          },
          privacidadeAgregacao: {
            minimoPorGrupo: 3,
            gruposSuprimidos: 1,
            registrosSuprimidos: 1,
            dimensoes: { porCanal: { grupos: 1, registros: 1 } },
          },
          destaques: [{
            tipo: "categoria",
            titulo: "Tema mais recorrente",
            descricao: "Saúde concentrou 3 solicitações.",
          }],
          evidencias: [{
            protocolo: "GF-2026-000001",
            titulo: "Demanda urgente",
            status: "RESOLVIDA",
            categoria: "Saúde",
            territorio: "Centro",
            orgao: "Secretaria de Saúde",
            eventos: [{
              tipo: "encaminhamento",
              data: "2026-07-10T10:00:00Z",
              descricao: "Encaminhado para Secretaria de Saúde",
            }],
          }],
          alertas: { reincidencias: [], crescimentosAnormais: [], regras: {} },
        };
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
        porOrgao: [{ nome: "Secretaria de Saúde", total: 2 }],
        porCanal: [{ nome: "WHATSAPP", total: 3 }],
        porPeriodo: [{ nome: "2026-07", total: 3 }],
        privacidadeAgregacao: {
          minimoPorGrupo: 3,
          gruposSuprimidos: 2,
          registrosSuprimidos: 2,
          dimensoes: {
            porCategoria: { grupos: 1, registros: 1 },
            porTerritorio: { grupos: 1, registros: 1 },
          },
        },
        filtros: {
          selecionados: {
            inicio: "",
            fim: "",
            categoria: "",
            canal: "",
            territorioId: "",
            orgaoId: "",
            granularidade: "dia",
          },
          opcoes: {
            categorias: ["Saúde"],
            canais: ["WHATSAPP"],
            territorios: [{ id: "territory-1", nome: "Centro" }],
            orgaos: [{ id: "agency-1", nome: "Secretaria de Saúde" }],
          },
        },
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
        alertasDemanda: {
          reincidencias: [{
            categoria: "Mobilidade urbana",
            territorio: "Centro",
            celula: "-21.76,-43.35",
            total: 3,
            abertas: 2,
            atrasadas: 1,
            regra: "3 demandas em 30 dias no mesmo recorte",
            exemplos: [{ id: "1", protocolo: "GF-2026-000001", titulo: "Demanda urgente" }],
          }],
          crescimentosAnormais: [{
            categoria: "Saúde",
            territorio: "Centro",
            atual: 4,
            baseSemanal: 1,
            fatorCrescimento: 4,
            regra: "4 demandas nos últimos 7 dias",
          }],
          regras: {},
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
          jurisdicao: {
            tipoCasa: "CAMARA_MUNICIPAL",
            nome: "Juiz de Fora/MG",
            municipio: "Juiz de Fora",
            uf: "MG",
            centro: { latitude: -21.7619, longitude: -43.3496 },
            limites: {
              minLatitude: -21.92,
              maxLatitude: -21.58,
              minLongitude: -43.58,
              maxLongitude: -43.17,
            },
          },
          coberturaPercentual: 50,
          geocodificadas: 1,
          semCoordenadas: 1,
          privacidade: {
            minimoPorGrupo: 3,
            pontosSuprimidos: 1,
            hotspotsSuprimidos: 1,
          },
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
    expect(screen.getByLabelText("Categoria")).toBeInTheDocument();
    expect(screen.getByLabelText("Canal")).toBeInTheDocument();
    expect(screen.getByText("Por órgão")).toBeInTheDocument();
    expect(screen.getByText("Por canal")).toBeInTheDocument();
    expect(screen.getByText("Por período")).toBeInTheDocument();
    expect(screen.getAllByText("Secretaria de Saúde").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Centro").length).toBeGreaterThan(0);
    expect(screen.getByText("Nova")).toBeInTheDocument();
    expect(screen.getByText("Aguardando cidadão")).toBeInTheDocument();
    expect(screen.queryByText("AGUARDANDO_CIDADAO")).not.toBeInTheDocument();
    expect(screen.getByText("Métricas operacionais")).toBeInTheDocument();
    expect(screen.getByText("Primeira resposta")).toBeInTheDocument();
    expect(screen.getByText("2,5 h")).toBeInTheDocument();
    expect(screen.getByText("Reaberturas")).toBeInTheDocument();
    expect(screen.getByText("Alertas de demanda")).toBeInTheDocument();
    expect(screen.getByText("Agregação mínima aplicada")).toBeInTheDocument();
    expect(screen.getByText(/Gráficos exibem apenas recortes com pelo menos 3 solicitações/)).toBeInTheDocument();
    expect(screen.getByText("Demandas reincidentes")).toBeInTheDocument();
    expect(screen.getByText("3 demandas · 2 abertas · 1 atrasadas")).toBeInTheDocument();
    expect(screen.getByText("Crescimento anormal")).toBeInTheDocument();
    expect(screen.getByText("4 recentes · base semanal 1")).toBeInTheDocument();
    expect(screen.getByText("Inteligência territorial")).toBeInTheDocument();
    expect(screen.queryByText("PostGIS ativo")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inteligência territorial" }));
    expect(screen.getByText("PostGIS ativo")).toBeInTheDocument();
    expect(screen.getAllByText("Juiz de Fora/MG").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Câmara Municipal · MG")).toBeInTheDocument();
    expect(screen.getByText(/Dados territoriais com menos de 3 solicitações/)).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole("button", { name: "Relatório mensal" }));
    expect(screen.getByText("Relatório mensal do mandato")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Gerar relatório/ }));
    await waitFor(() => expect(screen.getByText("Evidências rastreáveis")).toBeInTheDocument());
    expect(screen.getByText("07/2026")).toBeInTheDocument();
    expect(screen.getByText("Tema mais recorrente")).toBeInTheDocument();
    expect(screen.getByText(/GF-2026-000001/)).toBeInTheDocument();
  });
});
