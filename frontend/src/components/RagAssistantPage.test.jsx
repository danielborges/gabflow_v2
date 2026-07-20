import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RagAssistantPage } from "./RagAssistantPage";
import { Workspace } from "./Workspace";

beforeEach(() => vi.restoreAllMocks());

it("consulta o assistente RAG e exibe resposta com fonte", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "query-1",
      consulta: "Qual norma fundamenta iluminação pública?",
      resposta: "Encontrei evidência suficiente na base documental vigente.",
      fundamentada: true,
      recusaConclusiva: false,
      limiarEvidencia: 0.42,
      modeloEmbedding: "gabflow-hash-embedding-v1",
      seguranca: { promptInjectionDetectado: false, fontesComRisco: [], politica: "Fontes como dados." },
      fontes: [{
        documentoId: "doc-1",
        versaoId: "version-1",
        titulo: "Lei de Iluminação Pública",
        tipo: "LEGISLACAO",
        orgao: "Câmara Municipal",
        versao: "2026.1",
        paginaInicio: 1,
        paginaFim: 2,
        trecho: "Compete ao Município manter a iluminação adequada das praças.",
        pontuacao: 0.87,
        riscoPromptInjection: false,
      }],
    }),
  });

  render(<RagAssistantPage />);
  fireEvent.change(screen.getByLabelText("Pergunta"), {
    target: { value: "Qual norma fundamenta iluminação pública?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/assistente/consultas",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        consulta: "Qual norma fundamenta iluminação pública?",
        limite: 5,
      }),
    }),
  ));
  expect(await screen.findByText("Resposta fundamentada")).toBeInTheDocument();
  expect(screen.getAllByText("Lei de Iluminação Pública").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText("Documento")).toBeInTheDocument();
  expect(screen.getByText("Versão")).toBeInTheDocument();
  expect(screen.getByText("Página")).toBeInTheDocument();
  expect(screen.getByText("Score")).toBeInTheDocument();
  expect(screen.getByText("2026.1")).toBeInTheDocument();
  expect(screen.getByText("1-2")).toBeInTheDocument();
  expect(screen.getByText("0,87")).toBeInTheDocument();
  expect(screen.getByText("Trecho")).toBeInTheDocument();
  expect(screen.getByText(/Compete ao Município/)).toBeInTheDocument();
});

it("registra avaliação positiva, negativa e corrigida da resposta RAG", async () => {
  const baseAnswer = {
    id: "query-feedback",
    consulta: "Qual o procedimento?",
    resposta: "Resposta original do assistente.",
    fundamentada: true,
    recusaConclusiva: false,
    limiarEvidencia: 0.42,
    modeloEmbedding: "gabflow-hash-embedding-v1",
    seguranca: { promptInjectionDetectado: false, fontesComRisco: [], politica: "Fontes como dados." },
    fontes: [],
    avaliacao: null,
    respostaCorrigida: null,
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/assistente/consultas") && options.method === "POST") {
      return { ok: true, json: async () => baseAnswer };
    }
    if (path.endsWith("/assistente/consultas/query-feedback/avaliacao") && options.method === "PATCH") {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        json: async () => ({
          ...baseAnswer,
          avaliacao: body.avaliacao,
          comentario: body.comentario || null,
          respostaCorrigida: body.respostaCorrigida || null,
        }),
      };
    }
    return { ok: true, json: async () => ({ content: [] }) };
  });

  render(<RagAssistantPage />);
  fireEvent.change(screen.getByLabelText("Pergunta"), { target: { value: "Qual o procedimento?" } });
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));

  expect(await screen.findByRole("button", { name: "Positiva" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Negativa" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Corrigida" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Positiva" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/assistente/consultas/query-feedback/avaliacao",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ avaliacao: "POSITIVA" }),
    }),
  ));
  expect(await screen.findByText("Marcada como positiva.")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Comentário opcional"), {
    target: { value: "A resposta não citou a exceção do procedimento." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Negativa" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/assistente/consultas/query-feedback/avaliacao",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({
        avaliacao: "NEGATIVA",
        comentario: "A resposta não citou a exceção do procedimento.",
      }),
    }),
  ));
  expect(await screen.findByText("Marcada como negativa.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Corrigida" }));
  fireEvent.change(screen.getByLabelText("Resposta corrigida"), {
    target: { value: "Resposta corrigida pela revisão humana." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Registrar correção" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/assistente/consultas/query-feedback/avaliacao",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({
        avaliacao: "CORRIGIDA",
        respostaCorrigida: "Resposta corrigida pela revisão humana.",
      }),
    }),
  ));
  expect(await screen.findByText("Resposta corrigida registrada.")).toBeInTheDocument();
  expect(screen.getByText("Resposta corrigida pela revisão humana.")).toBeInTheDocument();
});

it("exibe alerta de segurança quando há prompt injection nas fontes", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "query-security",
      consulta: "O que diz o procedimento interno?",
      resposta: "Encontrei evidência suficiente após sanitizar trechos suspeitos.",
      fundamentada: true,
      recusaConclusiva: false,
      limiarEvidencia: 0.42,
      modeloEmbedding: "gabflow-hash-embedding-v1",
      seguranca: {
        promptInjectionDetectado: true,
        fontesComRisco: [{ documentoId: "doc-risk", versaoId: "version-risk" }],
        politica: "Fontes recuperadas são tratadas apenas como dados; instruções dentro de documentos não são executadas.",
      },
      fontes: [{
        documentoId: "doc-risk",
        versaoId: "version-risk",
        titulo: "Procedimento Interno de Atendimento",
        tipo: "PROCEDIMENTO_INTERNO",
        orgao: "Gabinete",
        versao: "1",
        paginaInicio: 3,
        paginaFim: 3,
        trecho: "O atendimento deve ser registrado com protocolo e responsável.",
        pontuacao: 0.91,
        riscoPromptInjection: true,
      }],
    }),
  });

  render(<RagAssistantPage />);
  fireEvent.change(screen.getByLabelText("Pergunta"), {
    target: { value: "O que diz o procedimento interno?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("possível prompt injection detectado");
  expect(screen.getByText("Procedimento Interno de Atendimento (versão 1, página 3)")).toBeInTheDocument();
  expect(screen.getByText("Trecho sanitizado por risco de prompt injection.")).toBeInTheDocument();
});

it("exibe resposta recusada quando falta evidência suficiente", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "query-2",
      consulta: "Existe norma sobre pesca submarina em Marte?",
      resposta: "Não encontrei evidência suficiente na base documental acessível.",
      fundamentada: false,
      recusaConclusiva: true,
      limiarEvidencia: 0.42,
      modeloEmbedding: "gabflow-hash-embedding-v1",
      seguranca: { promptInjectionDetectado: false, fontesComRisco: [], politica: "Fontes como dados." },
      fontes: [],
    }),
  });

  render(<RagAssistantPage />);
  fireEvent.change(screen.getByLabelText("Pergunta"), {
    target: { value: "Existe norma sobre pesca submarina em Marte?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));

  expect(await screen.findByText("Evidência insuficiente")).toBeInTheDocument();
  expect(screen.getByText("Recusada")).toBeInTheDocument();
  expect(screen.getByText(/Não encontrei evidência suficiente/)).toBeInTheDocument();
  expect(screen.getByText("Nenhuma fonte acima do limiar configurado.")).toBeInTheDocument();
});

it("deixa o Assistente RAG acessível no menu principal", async () => {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const path = String(url);
    if (path.includes("/notificacoes/preferencias")) {
      return { ok: true, json: async () => ({ content: [] }) };
    }
    if (path.includes("/notificacoes")) {
      return { ok: true, json: async () => ({ content: [], naoLidas: 0 }) };
    }
    return { ok: true, json: async () => ({ content: [] }) };
  });

  render(<Workspace user={{ name: "Admin", role: "admin", tenant: { name: "Gabinete" } }} onLogout={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Assistente RAG/ }));

  expect(await screen.findByRole("heading", { name: "Consulta institucional" })).toBeInTheDocument();
  expect(screen.getByText("Faça perguntas sobre a base documental vigente e revise as fontes antes de usar.")).toBeInTheDocument();
});
