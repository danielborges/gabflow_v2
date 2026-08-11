import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { apiDownload, apiRequest } from "../api";
import { OperationalDashboard } from "./OperationalDashboard";

vi.mock("../api", () => ({ apiRequest: vi.fn(), apiDownload: vi.fn() }));

describe("OperationalDashboard", () => {
  it("exibe indicadores, fila prioritária e inteligência territorial", async () => {
    apiDownload.mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" }));
    apiRequest.mockImplementation(async (path, options = {}) => {
      if (path.startsWith("/api/v1/painel/territorial/metricas-execucao")) {
        return { abertas: 2, taxaConclusaoPercentual: 50, coberturaEvidenciasPercentual: 50, cumprimentoPrazoPercentual: 100, tempoMedioConclusaoHoras: 8 };
      }
      if (path.startsWith("/api/v1/painel/territorial/alertas")) {
        return { content: [], total: 0 };
      }
      if (path.startsWith("/api/v1/painel/territorial/acoes")) {
        if (options.method === "POST") return { id: "action-1", status: "PENDENTE" };
        return {
          content: [],
          page: 1,
          total: 0,
          totalPages: 1,
          permissoes: { podeCriar: true, podeGerenciar: true, escopo: "GABINETE" },
          responsaveis: [{ id: "user-1", nome: "Equipe A" }],
        };
      }
      if (path === "/api/v1/painel/territorial/geocodificar" && options.method === "POST") {
        return { geocodificadas: 1, pendentes: 0, metodo: "LOCAL_APROXIMADO" };
      }
      if (path.startsWith("/api/v1/painel/relatorios")) {
        return {
          tipo: "OPERACIONAL",
          titulo: "Relatório Operacional Executivo",
          gabinete: { nome: "Gabinete A", jurisdicao: "Juiz de Fora/MG" },
          periodo: { ano: 2026, mes: 7, inicio: "2026-07-01", fim: "2026-07-31", rotulo: "07/2026" },
          resumo: {
            solicitacoesRecebidas: 5,
            solicitacoesMovimentadas: 6,
            encaminhadas: 3,
            resolvidasOuEncerradas: 2,
            emAberto: 4,
            atrasadas: 1,
            taxaResolucaoPercentual: 40,
            cumprimentoPrazoPercentual: 80,
            documentosLegislativos: 2,
            acoesGeradas: 7,
          },
          comparacao: { variacaoVolumePercentual: 25, variacaoResolucaoPercentual: 10 },
          semaforo: [{ nivel: "aviso", titulo: "Demandas em atraso", descricao: "16,7% terminaram atrasadas.", valor: "16,7%" }],
          rankings: {
            eficienciaEquipe: [{ id: "user-1", nome: "Equipe A", score: 86, demandas: 4, resolvidas: 3, cumprimentoPrazoPercentual: 100, interacoes: 8, tarefasConcluidas: 2 }],
            cidadaosAtuantes: [{ id: "citizen-1", nome: "Maria Silva", total: 3 }],
          },
          graficos: {
            volumePeriodo: [{ nome: "2026-07-01", total: 2 }, { nome: "2026-07-02", total: 5 }],
            horariosAtendimento: Array.from({ length: 24 }, (_, hora) => ({ hora, rotulo: `${String(hora).padStart(2, "0")}h`, total: hora === 10 ? 5 : 0 })),
            territorios: [{ nome: "Centro", total: 4 }],
            demandasRecorrentes: [{ nome: "Saúde", total: 3 }],
            producaoLegislativa: [{ nome: "REQUERIMENTO", total: 2 }],
            acoesGeradas: [{ nome: "Tarefas", total: 4 }, { nome: "Encaminhamentos", total: 3 }],
          },
          picoAtendimento: { hora: 10, rotulo: "10h", total: 5 },
          producaoLegislativa: { total: 2, demandasComDocumento: 2, porTipo: [{ nome: "REQUERIMENTO", total: 2 }] },
          acoesGeradas: { total: 7, porTipo: [{ nome: "Tarefas", total: 4 }] },
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
          qualidadeDados: {
            total: 2,
            territorioIdentificado: 1,
            territorioIdentificadoPercentual: 50,
            coordenadasAproximadas: 1,
            coordenadasVerificadas: 0,
            coordenadasAmbiguas: 0,
            foraDaJurisdicao: 0,
            semCoordenadas: 1,
          },
          privacidade: {
            minimoPorGrupo: 3,
            pontosSuprimidos: 1,
            hotspotsSuprimidos: 1,
            visualizacaoPontosPermitida: true,
          },
          revisoesLocalizacao: {
            total: 1,
            detalhesTecnicosPermitidos: true,
            content: [{
              id: "1",
              protocolo: "GF-2026-000001",
              titulo: "Demanda urgente",
              status: "APPROXIMATE",
              territorio: "Centro",
              territorioId: "territory-1",
              latitude: -21.7619,
              longitude: -43.3496,
              confianca: 0.72,
              metodo: "LOCAL_APPROXIMATE",
            }],
          },
          hotspots: [{ nome: "Centro", total: 2, abertas: 2, atrasadas: 1 }],
          heatmap: [{
            territorio: "Centro",
            territorioId: "territory-1",
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
            territorioId: "territory-1",
            latitude: -21.7619,
            longitude: -43.3496,
            atrasada: true,
          }],
          comparacao: {
            periodoAtual: { inicio: "2026-07-09", fim: "2026-08-07", amostra: 4 },
            periodoAnterior: { inicio: "2026-06-09", fim: "2026-07-08", amostra: 3 },
            metodo: "JANELAS_EQUIVALENTES",
            estado: "DISPONIVEL",
            variacaoVolumePercentual: 33.3,
          },
          tabelaTerritorial: [{
            id: "territory-1",
            nome: "Centro",
            total: 4,
            atrasadas: 1,
            solucionadas: 2,
            percentualAtraso: 25,
            taxaSolucao: 50,
            tempoMedianoPrimeiraRespostaHoras: 2.5,
            tempoMedianoResolucaoHoras: 12,
            qualidadeGeograficaPercentual: 75,
            tendencia: "CRESCIMENTO",
            comparacao: {
              estado: "DISPONIVEL",
              variacaoVolumePercentual: 33.3,
              variacaoAtrasoPontosPercentuais: 5,
              variacaoSolucaoPontosPercentuais: 10,
            },
            detalhes: {
              categorias: [{ nome: "Saúde", total: 3 }],
              orgaos: [{ nome: "Secretaria de Saúde", total: 3 }],
              responsaveis: [{ nome: "Equipe A", total: 3 }],
              alertas: [],
              amostra: [{ id: "1", protocolo: "GF-2026-000001", titulo: "Demanda urgente", status: "NOVA" }],
            },
            filtroSolicitacoes: { inicio: "2026-07-09", fim: "2026-08-07", territorioId: "territory-1" },
          }],
        },
      };
    });

    const onOpenRequests = vi.fn();
    const onOpenRequest = vi.fn();
    render(<OperationalDashboard onOpenRequests={onOpenRequests} onOpenRequest={onOpenRequest} />);
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
    fireEvent.click(screen.getByRole("tab", { name: "Inteligência territorial" }));
    expect(screen.getByText("PostGIS ativo")).toBeInTheDocument();
    expect(screen.getAllByText("Juiz de Fora/MG").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Câmara Municipal · MG")).toBeInTheDocument();
    expect(screen.getByText(/Dados territoriais com menos de 3 solicitações/)).toBeInTheDocument();
    expect(screen.getByText("Mapa de calor")).toBeInTheDocument();
    expect(screen.queryByLabelText("Categoria")).not.toBeInTheDocument();
    expect(screen.queryByText("Atrasadas")).not.toBeInTheDocument();
    expect(screen.queryByText("Hotspots")).not.toBeInTheDocument();
    expect(screen.queryByText("Pontos geocodificados")).not.toBeInTheDocument();
    expect(screen.getByText("Localizações que exigem revisão")).toBeInTheDocument();
    expect(screen.getByText("Baixa precisão · Centro")).toBeInTheDocument();
    expect(screen.getByLabelText("Mapa visual de calor territorial")).toBeInTheDocument();
    expect(screen.queryByText("2 demanda(s)")).not.toBeInTheDocument();
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
    expect(screen.getByText("território identificado")).toBeInTheDocument();
    expect(screen.getByText("coordenadas aproximadas")).toBeInTheDocument();
    expect(screen.getAllByText("GF-2026-000001").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Abrir solicitação GF-2026-000001" }));
    expect(screen.getByLabelText("Demandas selecionadas no mapa")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abrir solicitação" }));
    expect(onOpenRequest).toHaveBeenCalledWith(expect.objectContaining({ id: "1" }));
    expect(screen.getByText("Tabela territorial")).toBeInTheDocument();
    expect(screen.getByText("Comparação temporal")).toBeInTheDocument();
    expect(screen.getByText("Crescimento")).toBeInTheDocument();
    expect(screen.getByText("Operação territorial")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar status das ações")).toHaveValue("ABERTAS");
    expect(screen.getByLabelText("Ações por página")).toHaveValue("10");
    const newActionButton = screen.getByRole("button", { name: "Nova ação" });
    await waitFor(() => expect(newActionButton).toBeEnabled());
    fireEvent.click(newActionButton);
    expect(screen.getByRole("dialog", { name: "Criar ação territorial" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Responsável"), { target: { value: "user-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar ação" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/painel/territorial/acoes",
      expect.objectContaining({ method: "POST" }),
    ));
    fireEvent.click(screen.getAllByRole("button", { name: "Ver solicitações" })[0]);
    expect(onOpenRequests).toHaveBeenCalledWith(expect.objectContaining({ territorioId: "territory-1" }));

    fireEvent.click(screen.getByRole("button", { name: /Geocodificar/ }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/painel/territorial/geocodificar",
      { method: "POST" },
    ));

    fireEvent.click(screen.getByRole("tab", { name: "Relatórios" }));
    expect(screen.getByText("Relatórios do mandato")).toBeInTheDocument();
    expect(screen.getByLabelText("Tipo de relatório")).toHaveValue("operacional");
    expect(screen.getByLabelText("Data início do relatório")).toBeInTheDocument();
    expect(screen.getByLabelText("Data fim do relatório")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Gerar relatório/ }));
    await waitFor(() => expect(screen.getByText("Evidências rastreáveis")).toBeInTheDocument());
    expect(screen.getAllByText(/07\/2026/).length).toBeGreaterThan(0);
    expect(screen.getByText("Tema mais recorrente")).toBeInTheDocument();
    expect(screen.getByText("Ranking de eficiência da equipe")).toBeInTheDocument();
    expect(screen.getByText("Maria Silva")).toBeInTheDocument();
    expect(screen.getByText("Semáforo executivo")).toBeInTheDocument();
    expect(screen.getByText(/GF-2026-000001/)).toBeInTheDocument();
  });
});
