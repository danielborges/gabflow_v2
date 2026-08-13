import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { LegislativeDocumentsPage } from "./LegislativeDocumentsPage";
import { Workspace } from "./Workspace";

function DocumentsHarness({ user, initialSection = "drafts" }) {
  const [section, setSection] = useState(initialSection);
  return <LegislativeDocumentsPage user={user} activeSection={section} onSectionChange={setSection} />;
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

it("expõe as quatro áreas de Documentos como submenu lateral", async () => {
  window.history.replaceState({}, "", "/?tela=documents&secao=drafts");
  vi.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ content: [] }) });
  render(<Workspace user={{ name: "Admin", role: "admin", tenant: { name: "Gabinete", modulosHabilitados: ["documentos"] } }} onLogout={vi.fn()} />);

  const submenu = await screen.findByRole("group", { name: "Submenu Documentos" });
  expect(within(submenu).getByRole("button", { name: "Minutas" })).toHaveAttribute("aria-current", "page");
  expect(within(submenu).getByRole("button", { name: "Precedentes" })).toBeInTheDocument();
  expect(within(submenu).getByRole("button", { name: "Templates" })).toBeInTheDocument();
  expect(within(submenu).getByRole("button", { name: "Base normativa" })).toBeInTheDocument();
  expect(screen.queryByRole("tablist", { name: "Área legislativa" })).not.toBeInTheDocument();

  fireEvent.click(within(submenu).getByRole("button", { name: "Precedentes" }));
  expect(await screen.findByRole("heading", { name: "Precedentes legislativos" })).toBeInTheDocument();
  expect(window.location.search).toContain("secao=precedents");
});

it("lista minutas em tabela com busca, filtros, ordenação e paginação", async () => {
  const draft = {
    id: "draft-table-1",
    titulo: "Mobilidade ativa",
    tipo: "INDICACAO",
    status: "RASCUNHO",
    protocolo: null,
    atualizadaEm: "2026-08-13T12:00:00Z",
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url) => ({
    ok: true,
    json: async () => String(url).includes("/templates")
      ? { content: [] }
      : { content: [draft], page: 0, size: 25, totalElements: 31, totalPages: 2 },
  }));

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);

  expect(await screen.findByRole("columnheader", { name: "Título" })).toBeInTheDocument();
  expect(await screen.findByText("31 minutas encontradas")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Pesquisar minutas"), { target: { value: "mobilidade" } });
  fireEvent.change(screen.getByLabelText("Filtrar minutas por status"), { target: { value: "RASCUNHO" } });
  fireEvent.click(screen.getByRole("button", { name: "Título" }));

  await waitFor(() => {
    const listCall = global.fetch.mock.calls.findLast(([url]) => String(url).includes("/minutas?"));
    expect(String(listCall[0])).toContain("q=mobilidade");
    expect(String(listCall[0])).toContain("status=RASCUNHO");
    expect(String(listCall[0])).toContain("sort=titulo");
    expect(String(listCall[0])).toContain("direction=asc");
  });
  expect(screen.getByRole("button", { name: /Próxima/ })).toBeEnabled();
});

it("apresenta minuta, fundamentação pendente e protocolo somente manual", async () => {
  const draft = {
    id: "draft-1",
    tipo: "INDICACAO",
    status: "APROVADA",
    statusGeracao: "CONCLUIDA",
    titulo: "Manutenção da praça central",
    versaoAtual: 2,
    protocolo: null,
    conteudo: "Solicita manutenção da iluminação.",
    justificativa: "Demanda apresentada pelos moradores.",
    trechosSemFundamentacao: [{
      trecho: "Fundamentação normativa",
      motivo: "Nenhuma fonte normativa foi validada.",
    }],
    fontes: [],
    proposicoesSemelhantes: [],
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const body = String(url).includes("/templates")
      ? { content: [] }
      : String(url).endsWith("/draft-1")
        ? draft
        : { content: [draft] };
    return { ok: true, json: async () => body };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);
  fireEvent.click(await screen.findByText("Manutenção da praça central"));

  expect(await screen.findByText("Fundamentação pendente")).toBeInTheDocument();
  expect(screen.getByText("O GabFlow nunca protocola automaticamente.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Registrar" })).toBeDisabled();
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/minutas/draft-1",
    expect.objectContaining({ credentials: "include" }),
  ));
});

it("usa cores diferentes para o indicador de status da minuta na lista", async () => {
  const approved = {
    id: "draft-approved",
    tipo: "REQUERIMENTO",
    status: "APROVADA",
    statusGeracao: "CONCLUIDA",
    titulo: "Requerimento aprovado",
    versaoAtual: 1,
    protocolo: null,
    conteudo: "Conteúdo aprovado.",
    justificativa: "Justificativa.",
    trechosSemFundamentacao: [],
    fontes: [],
    proposicoesSemelhantes: [],
  };
  const draft = {
    id: "draft-draft",
    tipo: "INDICACAO",
    status: "RASCUNHO",
    statusGeracao: "CONCLUIDA",
    titulo: "Indicação em rascunho",
    versaoAtual: 1,
    protocolo: null,
    conteudo: "Conteúdo em edição.",
    justificativa: "Justificativa.",
    trechosSemFundamentacao: [],
    fontes: [],
    proposicoesSemelhantes: [],
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const path = String(url);
    const body = path.includes("/templates")
      ? { content: [] }
      : path.endsWith("/draft-approved")
        ? approved
        : path.endsWith("/draft-draft")
          ? draft
          : { content: [approved, draft] };
    return { ok: true, json: async () => body };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);

  expect(await screen.findByLabelText("Status da minuta: Aprovada")).toHaveClass("draft-status-aprovada");
  expect(screen.getByLabelText("Status da minuta: Rascunho")).toHaveClass("draft-status-rascunho");
});

it("apresenta a timeline e registra um novo andamento legislativo", async () => {
  let draft = {
    id: "draft-2",
    tipo: "PROJETO_LEI",
    status: "APROVADA",
    statusGeracao: "CONCLUIDA",
    titulo: "Projeto de iluminação pública",
    versaoAtual: 3,
    protocolo: "CM-2026-002",
    statusTramitacao: "PROTOCOLADA",
    conteudo: "Dispõe sobre a iluminação pública.",
    justificativa: "Interesse público.",
    trechosSemFundamentacao: [],
    fontes: [],
    proposicoesSemelhantes: [],
    tramitacoes: [{
      id: "movement-1",
      status: "PROTOCOLADA",
      etapa: "Protocolo",
      referenciaExterna: "CM-2026-002",
      ocorridaEm: "2026-07-17T12:00:00+00:00",
    }],
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    if (String(url).includes("/tramitacoes/movement-2/retificacoes") && options.method === "POST") {
      const payload = JSON.parse(options.body);
      draft = {
        ...draft,
        statusTramitacao: payload.status,
        tramitacoes: [
          draft.tramitacoes[0],
          { ...draft.tramitacoes[1], retificada: true, retificadaPorId: "movement-3" },
          { id: "movement-3", ...payload, tipoRegistro: "RETIFICACAO", retificaId: "movement-2", motivoRetificacao: payload.motivo, ocorridaEm: "2026-07-17T13:00:00+00:00" },
        ],
      };
      return { ok: true, json: async () => draft };
    }
    if (String(url).endsWith("/tramitacoes") && options.method === "POST") {
      const movement = {
        id: "movement-2",
        ...JSON.parse(options.body),
        status: "EM_COMISSAO",
        ocorridaEm: "2026-07-17T13:00:00+00:00",
      };
      draft = { ...draft, statusTramitacao: "EM_COMISSAO", tramitacoes: [...draft.tramitacoes, movement] };
      return { ok: true, json: async () => draft };
    }
    const body = String(url).includes("/templates")
      ? { content: [] }
      : String(url).endsWith("/draft-2")
        ? draft
        : { content: [draft] };
    return { ok: true, json: async () => body };
  });

  render(<LegislativeDocumentsPage user={{ role: "manager" }} />);
  fireEvent.click(await screen.findByText("Projeto de iluminação pública"));

  expect(await screen.findByText("Tramitação legislativa")).toBeInTheDocument();
  expect(screen.getAllByText("Protocolada")).toHaveLength(2);
  const submit = screen.getByRole("button", { name: "Registrar andamento" });
  expect(submit).toBeDisabled();

  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "EM_COMISSAO" } });
  fireEvent.change(screen.getByLabelText("Etapa"), { target: { value: "Comissão de Justiça" } });
  fireEvent.click(submit);

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/minutas/draft-2/tramitacoes",
    expect.objectContaining({ method: "POST" }),
  ));
  expect((await screen.findAllByText("Em comissão")).length).toBeGreaterThan(0);
  expect(screen.getByText("Comissão de Justiça")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retificar andamento" }));
  fireEvent.change(screen.getByLabelText("Status retificado"), { target: { value: "DISTRIBUIDA" } });
  fireEvent.change(screen.getByLabelText("Etapa retificada"), { target: { value: "Distribuição à comissão" } });
  fireEvent.change(screen.getByLabelText("Motivo da retificação"), { target: { value: "Correção de erro material no status registrado." } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar retificação" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/minutas/draft-2/tramitacoes/movement-2/retificacoes",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByText("Distribuição à comissão")).toBeInTheDocument();
  expect(screen.getByText(/Correção de erro material/)).toBeInTheDocument();
});

it("permite criar, editar e desativar templates pela gestão visual", async () => {
  let templates = [{
    id: "template-1",
    tipo: "INDICACAO",
    nome: "Indicação urbana",
    estrutura: "EMENTA\nOBJETO\nJUSTIFICATIVA",
    ativo: true,
  }];
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/template-1") && options.method === "PUT") {
      const payload = JSON.parse(options.body);
      templates = [{ ...templates[0], ...payload }];
      return { ok: true, json: async () => templates[0] };
    }
    if (path.endsWith("/template-1/status") && options.method === "PATCH") {
      templates = [{ ...templates[0], ativo: false }];
      return { ok: true, json: async () => templates[0] };
    }
    if (path.endsWith("/templates") && options.method === "POST") {
      const created = { id: "template-2", ...JSON.parse(options.body), ativo: true };
      templates = [...templates, created];
      return { ok: true, json: async () => created };
    }
    return {
      ok: true,
      json: async () => path.includes("/templates") ? { content: templates } : { content: [] },
    };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} activeSection="templates" />);

  expect((await screen.findAllByText("Indicação urbana")).length).toBeGreaterThan(0);
  const name = await screen.findByLabelText("Nome");
  fireEvent.change(name, { target: { value: "Indicação de zeladoria" } });
  fireEvent.change(screen.getByLabelText("Estrutura"), {
    target: { value: "EMENTA\nLOCAL\nPROVIDÊNCIA\nJUSTIFICATIVA" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/templates/template-1",
    expect.objectContaining({ method: "PUT" }),
  ));
  expect((await screen.findAllByText("Indicação de zeladoria")).length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole("button", { name: "Desativar" }));
  expect(await screen.findByRole("button", { name: "Reativar" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Novo template" }));
  fireEvent.change(screen.getByLabelText("Tipo de documento"), { target: { value: "OFICIO" } });
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ofício padrão" } });
  fireEvent.change(screen.getByLabelText("Estrutura"), { target: { value: "DESTINATÁRIO\nASSUNTO\nCORPO" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar template" }));
  expect(await screen.findByText("Ofício padrão")).toBeInTheDocument();
});

it("vincula uma solicitação principal e várias relacionadas na nova minuta", async () => {
  const requests = [
    { id: "request-main", protocolo: "GF-2026-101", titulo: "Iluminação da praça", status: "NOVA" },
    { id: "request-related", protocolo: "GF-2026-102", titulo: "Postes apagados no bairro", status: "EM_ATENDIMENTO" },
  ];
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.includes("/solicitacoes?") && options.method !== "POST") {
      return { ok: true, json: async () => ({ content: requests }) };
    }
    if (path.endsWith("/solicitacoes/request-main/gerar-minuta") && options.method === "POST") {
      return {
        ok: true,
        json: async () => ({
          id: "draft-multiple",
          tipo: "INDICACAO",
          status: "RASCUNHO",
          statusGeracao: "PENDENTE",
          titulo: "Indicação conjunta",
          versaoAtual: 0,
          protocolo: null,
        }),
      };
    }
    return {
      ok: true,
      json: async () => path.includes("/templates") ? { content: [] } : { content: [] },
    };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Nova minuta" }));

  const primary = screen.getByRole("combobox", { name: "Solicitação principal" });
  fireEvent.focus(primary);
  fireEvent.click(await screen.findByText("Iluminação da praça"));

  const related = screen.getByRole("combobox", { name: "Adicionar solicitação relacionada" });
  fireEvent.focus(related);
  expect(await screen.findByText("Postes apagados no bairro")).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /GF-2026-101/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Postes apagados no bairro"));

  expect(screen.getByText("GF-2026-102")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Gerar rascunho" }));

  await waitFor(() => {
    const request = global.fetch.mock.calls.find(([url, options]) => (
      String(url).endsWith("/solicitacoes/request-main/gerar-minuta")
      && options.method === "POST"
    ));
    expect(JSON.parse(request[1].body).solicitacoesRelacionadasIds).toEqual(["request-related"]);
  });
});

it("compara e restaura versões preservando o histórico", async () => {
  let draft = {
    id: "draft-history",
    tipo: "INDICACAO",
    status: "RASCUNHO",
    statusGeracao: "CONCLUIDA",
    titulo: "Iluminação revisada",
    versaoAtual: 2,
    protocolo: null,
    conteudo: "Solicita a troca das luminárias.",
    justificativa: "Segurança dos moradores.",
    trechosSemFundamentacao: [],
    fontes: [],
    proposicoesSemelhantes: [],
    solicitacoes: [],
    versoes: [
      { id: "version-2", numero: 2, motivo: "Ajuste de clareza", autor: "Admin A", criadaEm: "2026-07-17T13:00:00Z" },
      { id: "version-1", numero: 1, motivo: "Versão inicial", autor: "Admin A", criadaEm: "2026-07-17T12:00:00Z" },
    ],
  };
  const comparison = {
    de: 1,
    para: 2,
    camposAlterados: ["conteudo"],
    linhasAdicionadas: 1,
    linhasRemovidas: 1,
    campos: {
      conteudo: {
        alterado: true,
        linhasAdicionadas: 1,
        linhasRemovidas: 1,
        diferencas: [
          { tipo: "REMOVIDA", texto: "Solicita manutenção das luminárias." },
          { tipo: "ADICIONADA", texto: "Solicita a troca das luminárias." },
        ],
      },
    },
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/versoes/1")) {
      return { ok: true, json: async () => ({
        numero: 1,
        autor: "Admin A",
        criadaEm: "2026-07-17T12:00:00Z",
        titulo: "Iluminação pública",
        conteudo: "Solicita manutenção das luminárias.",
        justificativa: "Segurança dos moradores.",
      }) };
    }
    if (path.includes("/comparacao?de=1&para=2")) {
      return { ok: true, json: async () => comparison };
    }
    if (path.endsWith("/versoes/1/restaurar") && options.method === "POST") {
      draft = {
        ...draft,
        titulo: "Iluminação pública",
        conteudo: "Solicita manutenção das luminárias.",
        versaoAtual: 3,
        versoes: [
          { id: "version-3", numero: 3, motivo: "Restauração da versão 1: Retomar redação aprovada", autor: "Admin A", criadaEm: "2026-07-17T14:00:00Z" },
          ...draft.versoes,
        ],
      };
      return { ok: true, json: async () => draft };
    }
    const body = path.includes("/templates")
      ? { content: [] }
      : path.endsWith("/draft-history")
        ? draft
        : { content: [draft] };
    return { ok: true, json: async () => body };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);
  fireEvent.click(await screen.findByText("Iluminação revisada"));

  expect(await screen.findByText("Histórico de versões")).toBeInTheDocument();
  const compareButton = screen.getByRole("button", { name: "Comparar" });
  await waitFor(() => expect(compareButton).toBeEnabled());
  fireEvent.click(compareButton);
  expect(await screen.findByText("Versão 1 → versão 2")).toBeInTheDocument();
  expect(screen.getByText("+ Solicita a troca das luminárias.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /v1 Versão inicial/ }));
  expect(await screen.findByText("Solicita manutenção das luminárias.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restaurar esta versão" }));
  fireEvent.change(screen.getByLabelText("Motivo da restauração"), {
    target: { value: "Retomar redação aprovada" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirmar restauração" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/minutas/draft-history/versoes/1/restaurar",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByText("3 versões")).toBeInTheDocument();
});

it("pesquisa precedentes semanticamente e abre a minuta encontrada", async () => {
  const precedent = {
    id: "precedent-1",
    titulo: "Iluminação e segurança nas praças",
    tipo: "INDICACAO",
    status: "APROVADA",
    protocolo: "CM-2026-SEM-01",
    resumo: "Instala luminárias para permitir o uso seguro dos espaços públicos.",
    similaridade: 0.91,
    justificativas: ["Similaridade semântica de 92%", "Proposição aprovada"],
  };
  const draft = {
    ...precedent,
    statusGeracao: "CONCLUIDA",
    versaoAtual: 1,
    conteudo: precedent.resumo,
    justificativa: "Proteção dos moradores.",
    trechosSemFundamentacao: [],
    fontes: [],
    proposicoesSemelhantes: [],
    solicitacoes: [],
    versoes: [],
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const path = String(url);
    if (path.includes("/precedentes?")) {
      return { ok: true, json: async () => ({
        consulta: "segurança noturna em espaços públicos",
        modelo: "nomic-embed-text",
        fallbackUtilizado: false,
        limiar: 0.60,
        totalCandidatos: 8,
        content: [precedent],
      }) };
    }
    if (path.endsWith("/precedent-1")) return { ok: true, json: async () => draft };
    return {
      ok: true,
      json: async () => path.includes("/templates") ? { content: [] } : { content: [draft] },
    };
  });

  render(<DocumentsHarness user={{ role: "admin" }} initialSection="precedents" />);
  fireEvent.change(screen.getByLabelText("Assunto do precedente"), {
    target: { value: "segurança noturna em espaços públicos" },
  });
  fireEvent.change(screen.getByLabelText("Tipo do precedente"), {
    target: { value: "INDICACAO" },
  });
  fireEvent.change(screen.getByLabelText("Status do precedente"), {
    target: { value: "APROVADA" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Buscar precedentes" }));

  expect(await screen.findByText("91%")).toBeInTheDocument();
  expect(screen.getByText("nomic-embed-text · embeddings locais")).toBeInTheDocument();
  const searchCall = global.fetch.mock.calls.find(([url]) => String(url).includes("/precedentes?"));
  expect(String(searchCall[0])).toContain("tipo=INDICACAO");
  expect(String(searchCall[0])).toContain("status=APROVADA");

  fireEvent.click(screen.getByRole("button", { name: "Abrir minuta" }));
  expect(await screen.findByDisplayValue("Iluminação e segurança nas praças")).toBeInTheDocument();
});

it("cadastra e versiona fontes na base normativa", async () => {
  let sources = [];
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/fontes-normativas") && options.method === "POST") {
      const created = { id: "source-1", ...JSON.parse(options.body), checksum: "abc", ativo: true };
      sources = [created];
      return { ok: true, json: async () => created };
    }
    if (path.includes("/fontes-normativas")) {
      return { ok: true, json: async () => ({ content: sources }) };
    }
    return { ok: true, json: async () => ({ content: [] }) };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} activeSection="sources" />);
  fireEvent.change(await screen.findByLabelText("Título da fonte"), { target: { value: "Lei de iluminação pública" } });
  fireEvent.change(screen.getByLabelText("Referência normativa"), { target: { value: "art. 12" } });
  fireEvent.change(screen.getByLabelText("Trecho normativo"), { target: { value: "O Município manterá iluminadas as praças e vias públicas." } });
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar fonte" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/v1/legislativo/fontes-normativas",
    expect.objectContaining({ method: "POST" }),
  ));
  expect((await screen.findAllByText("Lei de iluminação pública")).length).toBeGreaterThan(0);
  expect(screen.getByText("Ativa")).toBeInTheDocument();
});

it("aplica fundamentação recuperada somente após seleção e justificativa", async () => {
  const suggestion = {
    id: "source-1",
    titulo: "Lei Municipal de Iluminação Pública",
    referencia: "art. 12",
    trecho: "O Município manterá a iluminação das praças e vias públicas.",
    versao: "2026",
    jurisdicao: "Município de Teste",
    pontuacao: 0.91,
    justificativas: ["Similaridade semântica de 93%"],
    url: "https://leis.example.test/iluminacao",
  };
  let draft = {
    id: "draft-foundation",
    tipo: "INDICACAO",
    status: "RASCUNHO",
    statusGeracao: "CONCLUIDA",
    titulo: "Iluminação da praça central",
    versaoAtual: 1,
    conteudo: "Solicita manutenção da iluminação.",
    justificativa: "Segurança dos moradores.",
    trechosSemFundamentacao: [{ trecho: "Fundamentação normativa", motivo: "Pendente" }],
    fontes: [],
    proposicoesSemelhantes: [],
    solicitacoes: [],
    versoes: [],
    fundamentacaoSugerida: { modelo: "local-tfidf-v1", fallbackUtilizado: false, totalCandidatos: 1, limiar: 0.55, fontes: [suggestion] },
  };
  vi.spyOn(global, "fetch").mockImplementation(async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/fundamentacao/aplicar") && options.method === "POST") {
      draft = { ...draft, versaoAtual: 2, fontes: [{ sourceId: "source-1", titulo: suggestion.titulo, referencia: suggestion.referencia }], trechosSemFundamentacao: [] };
      return { ok: true, json: async () => draft };
    }
    if (path.endsWith("/draft-foundation")) return { ok: true, json: async () => draft };
    return { ok: true, json: async () => path.includes("/templates") ? { content: [] } : { content: [draft] } };
  });

  render(<LegislativeDocumentsPage user={{ role: "admin" }} />);
  fireEvent.click(await screen.findByText("Iluminação da praça central"));
  expect(await screen.findByText("Fundamentação sugerida")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Aplicar fontes selecionadas" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.change(screen.getByLabelText("Motivo da fundamentação"), { target: { value: "Dispositivo pertinente" } });
  const applyButton = screen.getByRole("button", { name: "Aplicar fontes selecionadas" });
  await waitFor(() => expect(applyButton).toBeEnabled());
  fireEvent.click(applyButton);

  await waitFor(() => {
    const call = global.fetch.mock.calls.find(([url]) => String(url).endsWith("/fundamentacao/aplicar"));
    expect(call).toBeDefined();
    expect(JSON.parse(call[1].body)).toEqual({ fonteIds: ["source-1"], motivo: "Dispositivo pertinente" });
  });
  expect(await screen.findByText(/Indicação · versão 2/)).toBeInTheDocument();
});
