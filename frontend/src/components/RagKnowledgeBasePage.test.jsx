import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RagKnowledgeBasePage } from "./RagKnowledgeBasePage";

beforeEach(() => vi.restoreAllMocks());

it("envia documento e metadados para ingestão", async () => {
  let documents = [];
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    if (String(url).endsWith("/rag/documentos") && options.method === "POST") {
      const body = options.body;
      const created = {
        id: "doc-1", titulo: body.get("titulo"), tipo: body.get("tipo"),
        orgao: body.get("orgao"), nivelAcesso: body.get("nivelAcesso"),
        quantidadeVersoes: 1,
        ultimaVersao: { statusIngestao: "PENDENTE" },
        versoes: [{ id: "version-1", versao: body.get("versao"), estado: "RASCUNHO", statusIngestao: "PENDENTE", arquivo: "lei.txt", tamanhoBytes: 100, checksum: "abcdef1234567890", fragmentos: 0, paginas: null, downloadUrl: "/download" }],
      };
      documents = [created];
      return { ok: true, json: async () => created };
    }
    return { ok: true, json: async () => ({ content: documents }) };
  });

  render(<RagKnowledgeBasePage />);
  fireEvent.click(screen.getByRole("button", { name: "Novo documento" }));
  expect(document.querySelector(".rag-upload-form").parentElement).toHaveClass("rag-content-form");
  expect(screen.getByText(/quem publicou ou responde pelo documento.*deixe em branco/i)).toBeInTheDocument();
  expect(screen.getByText(/publicação original para conferência e proveniência/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Título do documento"), { target: { value: "Lei de Serviços Urbanos" } });
  fireEvent.change(screen.getByLabelText("Órgão responsável"), { target: { value: "Câmara Municipal" } });
  fireEvent.change(screen.getByLabelText("Identificação da revisão"), { target: { value: "2026.1" } });
  const file = new File(["conteúdo normativo suficiente para indexação"], "lei.txt", { type: "text/plain" });
  fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar para ingestão" }));

  await waitFor(() => {
    const call = global.fetch.mock.calls.find(([, options]) => options.method === "POST");
    expect(call[1].body.get("titulo")).toBe("Lei de Serviços Urbanos");
    expect(call[1].body.get("arquivo")).toBe(file);
  });
  expect(await screen.findByText("Histórico de revisões")).toBeInTheDocument();
  expect((await screen.findAllByText("Na fila")).length).toBeGreaterThan(0);
});

it("publica versão indexada e preserva indicadores de proveniência", async () => {
  let documentValue = {
    id: "doc-2", titulo: "Regimento Interno", tipo: "LEGISLACAO", orgao: "Câmara",
    nivelAcesso: "RESTRITO", quantidadeVersoes: 1,
    ultimaVersao: { statusIngestao: "INDEXADO" },
    versoes: [{ id: "version-2", versao: "2026", estado: "RASCUNHO", statusIngestao: "INDEXADO", arquivo: "regimento.pdf", tamanhoBytes: 2048, checksum: "1234567890abcdef1234", fragmentos: 12, paginas: 8, modeloEmbedding: "nomic-embed-text", downloadUrl: "/download" }],
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/estado") && options.method === "PATCH") {
      documentValue = { ...documentValue, versoes: [{ ...documentValue.versoes[0], estado: "VIGENTE" }] };
      return { ok: true, json: async () => documentValue.versoes[0] };
    }
    if (path.endsWith("/doc-2")) return { ok: true, json: async () => documentValue };
    return { ok: true, json: async () => ({ content: [documentValue] }) };
  });

  render(<RagKnowledgeBasePage />);
  fireEvent.click(await screen.findByRole("button", { name: /Regimento Interno/ }));
  expect(await screen.findByText("12 fragmentos · 8 página(s)")).toBeInTheDocument();
  expect(screen.getByText("nomic-embed-text")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Tornar vigente" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/rag/documentos/doc-2/versoes/version-2/estado",
    expect.objectContaining({ method: "PATCH" }),
  ));
  expect(await screen.findByText("Vigente")).toBeInTheDocument();
});

it("bloqueia documentos acima de 25 MB antes do envio", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ content: [] }) });

  render(<RagKnowledgeBasePage />);
  fireEvent.click(screen.getByRole("button", { name: "Novo documento" }));
  fireEvent.change(screen.getByLabelText("Título do documento"), { target: { value: "Plano de mobilidade" } });
  const file = new File(["conteudo"], "plano.pdf", { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: 25 * 1024 * 1024 + 1 });
  fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [file] } });

  expect(await screen.findByRole("alert")).toHaveTextContent("limite da base documental RAG é 25 MB");
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

it("exibe catálogo paginado e ordenável abaixo da área de trabalho", async () => {
  const documents = Array.from({ length: 12 }, (_, index) => ({
    id: `doc-${index + 1}`,
    titulo: `Documento ${String(index + 1).padStart(2, "0")}`,
    tipo: index % 2 ? "ATA" : "LEGISLACAO",
    orgao: `Órgão ${12 - index}`,
    nivelAcesso: "INTERNO",
    quantidadeVersoes: index + 1,
    ultimaVersao: { statusIngestao: "INDEXADO" },
  }));
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const id = String(url).match(/documentos\/(doc-\d+)$/)?.[1];
    if (id) {
      const item = documents.find((document) => document.id === id);
      return { ok: true, json: async () => ({ ...item, versoes: [] }) };
    }
    return { ok: true, json: async () => ({ content: documents }) };
  });

  render(<RagKnowledgeBasePage />);
  const workspaceTitle = screen.getByText("Área de trabalho documental");
  const catalogTitle = screen.getByRole("heading", { name: "Documentos do gabinete" });
  expect(workspaceTitle.compareDocumentPosition(catalogTitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  const table = await screen.findByRole("table");
  await waitFor(() => expect(within(table).getByText("Documento 01")).toBeInTheDocument());
  expect(within(table).queryByText("Documento 11")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
  expect(await within(table).findByText("Documento 11")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Revisões/ }));
  fireEvent.click(screen.getByRole("button", { name: /Revisões/ }));
  expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Documento 12");
  fireEvent.click(within(table).getByRole("button", { name: /Documento 12/ }));
  expect(await screen.findByRole("heading", { name: "Documento 12" })).toBeInTheDocument();
});

it("separa memórias automáticas e apresenta origem, estado e retenção", async () => {
  const documentValue = {
    id: "doc-manual", titulo: "Manual do gabinete", tipo: "PROCEDIMENTO_INTERNO",
    orgao: "Gabinete", nivelAcesso: "INTERNO", quantidadeVersoes: 1,
    ultimaVersao: { statusIngestao: "INDEXADO" },
  };
  const memoryValue = {
    id: "memory-1", titulo: "Solicitação de iluminação", modulo: "SOLICITACOES",
    entidadeId: "12345678-aaaa-bbbb-cccc-123456789012", estado: "ATIVA",
    estadoNome: "Disponível", disponivelParaInteligencia: true,
    finalidade: "ACOMPANHAMENTO_DE_ENCAMINHAMENTOS_E_RESPOSTAS_OFICIAIS",
    nivelAcesso: "INTERNO", retencaoAte: "2027-08-13",
    atualizadaEm: "2026-08-13T15:00:00Z",
    origem: { sistema: "GabFlow", moduloNome: "Solicitações", entidadeNome: "Solicitação", entidadeId: "12345678-aaaa-bbbb-cccc-123456789012" },
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    if (String(url).endsWith("/rag/fontes-operacionais")) {
      return { ok: true, json: async () => ({ content: [memoryValue] }) };
    }
    return { ok: true, json: async () => ({ content: [documentValue] }) };
  });

  render(<RagKnowledgeBasePage />);
  expect(await screen.findByText("Manual do gabinete")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Memórias do GabFlow/ }));
  expect(await screen.findByText("Solicitação de iluminação")).toBeInTheDocument();
  expect(screen.queryByText("Manual do gabinete")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Solicitação de iluminação/ }));
  expect(await screen.findByText("Disponível para a inteligência do gabinete")).toBeInTheDocument();
  expect(screen.getAllByText("Solicitações").length).toBeGreaterThan(0);
  expect(screen.getByText("Após o prazo, o conteúdo é descartado")).toBeInTheDocument();
  expect(screen.getByText("Acompanhar encaminhamentos realizados pelo gabinete e as respostas oficiais recebidas.")).toBeInTheDocument();
  expect(screen.queryByText("ACOMPANHAMENTO_DE_ENCAMINHAMENTOS_E_RESPOSTAS_OFICIAIS")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Adicionar revisão" })).not.toBeInTheDocument();
});
