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

  it("apresenta conversas na caixa 2.0 e abre o histórico", async () => {
    apiRequest.mockImplementation((path) => {
      if (path === "/api/v1/canais/mensagens") return Promise.resolve({ content: [] });
      if (path.startsWith("/api/v1/canais/revisoes-identidade?")) return Promise.resolve({ content: [], resumo: {}, responsaveis: [] });
      if (path === "/api/v1/canais/configuracao-cadastro-assistido") return Promise.resolve({ baseLegalPadrao: "", slaHoras: 24, retencaoDias: 365 });
      if (path === "/api/v1/tenants/tenant-a/conversations?") return Promise.resolve({
        content: [{ id: "conversation-1", estado: "PRIVACY_NOTICE", modo: "BOT", naoLidas: 1, ultimaMensagemEm: "2026-08-12T12:00:00Z", contato: { nome: "Maria", whatsappMascarado: "***0000" }, ultimaMensagem: { conteudo: "Preciso de ajuda" }, responsavel: null }],
        resumo: { total: 1, naoLidas: 1, humanas: 0 },
        responsaveis: [{ id: "user-1", nome: "Assessora" }],
      });
      if (path === "/api/v1/tenants/tenant-a/conversations/conversation-1") return Promise.resolve({ id: "conversation-1", estado: "PRIVACY_NOTICE", modo: "BOT", naoLidas: 0, janelaAberta: true, janelaExpiraEm: "2026-08-13T12:00:00Z", contato: { nome: "Maria", whatsappMascarado: "***0000" }, responsavel: null, mensagens: [{ id: "message-1", direcao: "INBOUND", tipo: "text", status: "RECEIVED", conteudo: "Preciso de ajuda", ocorridaEm: "2026-08-12T12:00:00Z" }], midias: [{ id: "media-1", tipo: "audio", nome: "audio.ogg", mimeType: "audio/ogg", status: "READY", analise: { tipo: "TRANSCRIPTION", status: "COMPLETED", statusRevisao: "PENDING", confianca: 0.94, textoGerado: "Relato transcrito" } }] });
      return Promise.resolve({});
    });

    render(<ChannelsPage user={{ role: "staff", tenant: { id: "tenant-a" } }} />);

    expect(await screen.findByText("Maria")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Maria/ }));
    expect(await screen.findByText(/Janela até/)).toBeInTheDocument();
    expect(screen.getAllByText("Preciso de ajuda").length).toBeGreaterThan(0);
    expect(screen.getByText(/M.dia e IA assistiva/)).toBeInTheDocument();
    expect(screen.getByText("94%")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mensagem WhatsApp"), { target: { value: "Retorno do gabinete" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar pelo WhatsApp" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/tenants/tenant-a/conversations/conversation-1/messages",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": expect.stringContaining("inbox-conversation-1-") }),
        body: JSON.stringify({ texto: "Retorno do gabinete" }),
      }),
    ));
  });

  it("conduz privacidade, identificação e solicitação em uma jornada explícita", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/canais/mensagens") return Promise.resolve({ content: [] });
      if (path.startsWith("/api/v1/canais/revisoes-identidade?")) return Promise.resolve({ content: [], resumo: {}, responsaveis: [] });
      if (path === "/api/v1/canais/configuracao-cadastro-assistido") return Promise.resolve({ baseLegalPadrao: "EXECUCAO_POLITICA_PUBLICA", slaHoras: 24, retencaoDias: 365 });
      if (path === "/api/v1/tenants/tenant-a/conversations?") return Promise.resolve({
        content: [{ id: "conversation-1", estado: "PRIVACY_NOTICE", modo: "BOT", naoLidas: 0, contato: { nome: "Maria" }, responsavel: null }],
        resumo: { total: 1 },
        responsaveis: [],
      });
      if (path === "/api/v1/tenants/tenant-a/conversations/conversation-1" && !options.method) return Promise.resolve({
        id: "conversation-1",
        estado: "PRIVACY_NOTICE",
        modo: "BOT",
        naoLidas: 0,
        janelaAberta: true,
        contato: { nome: "Maria", whatsappMascarado: "***0000" },
        responsavel: null,
        mensagens: [],
        categorias: [],
        jornada: {
          privacidade: { solicitada: true, reconhecida: false },
          cidadao: null,
          sugestoesCidadao: [],
          rascunhoSolicitacao: null,
          solicitacao: null,
        },
      });
      if (path.endsWith("/privacy") && options.method === "POST") return Promise.resolve({ estado: "IDENTIFICATION" });
      return Promise.resolve({});
    });

    render(<ChannelsPage user={{ role: "staff", tenant: { id: "tenant-a" } }} />);
    fireEvent.click(await screen.findByRole("button", { name: /Maria/ }));
    expect(await screen.findByText("Transparência antes da coleta")).toBeInTheDocument();
    expect(screen.getByText("O atendimento institucional é processado pelo GabFlow", { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Registrar aviso apresentado" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/tenants/tenant-a/conversations/conversation-1/privacy",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          baseLegal: "EXECUCAO_POLITICA_PUBLICA",
          consentimentoNecessario: false,
        }),
      }),
    ));
  });

  it("envia o Flow de nova solicitaÃ§Ã£o pela conversa", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/canais/mensagens") return Promise.resolve({ content: [] });
      if (path.startsWith("/api/v1/canais/revisoes-identidade?")) return Promise.resolve({ content: [], resumo: {}, responsaveis: [] });
      if (path === "/api/v1/canais/configuracao-cadastro-assistido") return Promise.resolve({ baseLegalPadrao: "EXECUCAO_POLITICA_PUBLICA", slaHoras: 24, retencaoDias: 365 });
      if (path === "/api/v1/tenants/tenant-a/conversations?") return Promise.resolve({
        content: [{ id: "conversation-1", estado: "DATA_COLLECTION", modo: "BOT", naoLidas: 0, contato: { nome: "Maria" }, responsavel: null }], resumo: { total: 1 }, responsaveis: [],
      });
      if (path === "/api/v1/tenants/tenant-a/conversations/conversation-1/flows/new_service_request/launch" && options.method === "POST") return Promise.resolve({ modo: "FLOW", sessaoId: "session-1" });
      if (path === "/api/v1/tenants/tenant-a/conversations/conversation-1" && !options.method) return Promise.resolve({
        id: "conversation-1", estado: "DATA_COLLECTION", modo: "BOT", naoLidas: 0, janelaAberta: true,
        contato: { nome: "Maria", whatsappMascarado: "***0000" }, responsavel: null, mensagens: [], categorias: [],
        whatsappFlow: { sessao: null, fallbackDisponivel: true },
        jornada: {
          privacidade: { solicitada: true, reconhecida: true },
          cidadao: { id: "citizen-1", nome: "Maria" }, sugestoesCidadao: [], rascunhoSolicitacao: null, solicitacao: null,
        },
      });
      return Promise.resolve({});
    });

    render(<ChannelsPage user={{ role: "staff", tenant: { id: "tenant-a" } }} />);
    fireEvent.click(await screen.findByRole("button", { name: /Maria/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Coletar solicitaÃ§Ã£o pelo WhatsApp Flow" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/tenants/tenant-a/conversations/conversation-1/flows/new_service_request/launch",
      { method: "POST" },
    ));
    expect(await screen.findByText(/Envio do Flow solicitado/)).toBeInTheDocument();
  });
});
