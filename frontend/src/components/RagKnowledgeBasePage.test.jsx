import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  fireEvent.change(screen.getByLabelText("Título do documento"), { target: { value: "Lei de Serviços Urbanos" } });
  fireEvent.change(screen.getByLabelText("Órgão"), { target: { value: "Câmara Municipal" } });
  fireEvent.change(screen.getByLabelText("Versão documental"), { target: { value: "2026.1" } });
  const file = new File(["conteúdo normativo suficiente para indexação"], "lei.txt", { type: "text/plain" });
  fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar para ingestão" }));

  await waitFor(() => {
    const call = global.fetch.mock.calls.find(([, options]) => options.method === "POST");
    expect(call[1].body.get("titulo")).toBe("Lei de Serviços Urbanos");
    expect(call[1].body.get("arquivo")).toBe(file);
  });
  expect(await screen.findByText("Histórico de versões")).toBeInTheDocument();
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
  fireEvent.click(screen.getByRole("button", { name: "Publicar" }));
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
