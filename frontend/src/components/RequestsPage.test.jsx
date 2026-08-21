import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { RequestsPage } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("RequestsPage", () => {
  beforeEach(() => {
    apiRequest.mockResolvedValue({
      content: [],
      page: 0,
      size: 50,
      totalElements: 0,
      totalPages: 0,
    });
  });

  it("exibe o estado vazio após consultar a API", async () => {
    render(<RequestsPage />);
    await waitFor(() => {
      expect(screen.getByText("Nenhuma solicitação encontrada")).toBeInTheDocument();
    });
    expect(screen.queryByRole("textbox", { name: "Buscar solicitações" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Filtrar por status" })).not.toBeInTheDocument();
  });

  it("leva a busca global por solicitação para o filtro visível de protocolo", async () => {
    apiRequest.mockResolvedValue({
      content: [{
        id: "req-search",
        protocolo: "GF-2026-000321",
        titulo: "Solicitação localizada",
        categoria: "Atendimento",
        origem: "PRESENCIAL",
        prioridade: "MEDIA",
        status: "NOVA",
        criadaEm: "2026-08-07T12:00:00Z",
      }],
      page: 0,
      size: 25,
      totalElements: 1,
      totalPages: 1,
    });
    render(<RequestsPage initialSearch="GF-2026-000321" />);
    expect(await screen.findByRole("textbox", { name: "Filtrar protocolo" })).toHaveValue("GF-2026-000321");
    await waitFor(() => {
      expect(apiRequest.mock.calls.some(([url]) => String(url).includes("protocolo=GF-2026-000321"))).toBe(true);
    });
  });

  it("preserva o recorte recebido da inteligência territorial", async () => {
    const consumed = vi.fn();
    render(<RequestsPage
      initialFilters={{
        inicio: "2026-07-09",
        fim: "2026-08-07",
        territorioId: "territory-1",
        canal: "WHATSAPP",
      }}
      onInitialFiltersConsumed={consumed}
    />);
    expect(await screen.findByText("Recorte territorial aplicado")).toBeInTheDocument();
    await waitFor(() => {
      expect(apiRequest.mock.calls.some(([url]) => {
        const value = String(url);
        return value.includes("territorioId=territory-1")
          && value.includes("inicio=2026-07-09")
          && value.includes("origem=WHATSAPP");
      })).toBe(true);
    });
    expect(consumed).toHaveBeenCalled();
  });

  it("abre o formulário de nova solicitação", () => {
    render(<RequestsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.getByRole("dialog", { name: "Registrar solicitação" })).toBeInTheDocument();
    expect(screen.getByLabelText("Descrição")).toBeRequired();
    const fields = ["Cidadão", "Organização", "Título", "Descrição", "Endereço"]
      .map((label) => screen.getByLabelText(label));
    fields.slice(1).forEach((field, index) => {
      expect(fields[index].compareDocumentPosition(field) & Node.DOCUMENT_POSITION_FOLLOWING)
        .toBeTruthy();
    });
    expect(fields[0]).toBeEnabled();
  });

  it("permite pesquisar e selecionar o cidadão na nova solicitação", async () => {
    apiRequest.mockImplementation((url) => {
      if (String(url).includes("/api/v1/cidadaos?limite=12&q=Paulo")) {
        return Promise.resolve({
          content: [{
            id: "cid-1",
            nome: "Paulo Silva",
            cpf: "123.456.789-00",
            canalPreferencial: "WHATSAPP",
            contatos: [{ tipo: "WHATSAPP", valor: "(32) 99999-0000" }],
          }],
        });
      }
      if (String(url).includes("/api/v1/cidadaos")) {
        return Promise.resolve({ content: [] });
      }
      return Promise.resolve({
        content: [],
        page: 0,
        size: 50,
        totalElements: 0,
        totalPages: 0,
      });
    });

    render(<RequestsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    const citizenField = screen.getByRole("combobox", { name: "Cidadão" });

    fireEvent.focus(citizenField);
    fireEvent.change(citizenField, { target: { value: "Paulo" } });
    fireEvent.click(await screen.findByText("Paulo Silva"));

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/cidadaos?limite=12&q=Paulo");
    expect(citizenField).toHaveValue("Paulo Silva");
  });

  it("abre nova solicitação com o cidadão recebido do diretório pré-selecionado", async () => {
    apiRequest.mockImplementation((url) => Promise.resolve({
      content: String(url).includes("/api/v1/cidadaos")
        ? [{ id: "cid-1", nome: "Bruno Silva", contatos: [] }]
        : [],
    }));

    render(<RequestsPage initialCitizenId="cid-1" onInitialContextConsumed={vi.fn()} />);

    expect(await screen.findByRole("dialog", { name: "Registrar solicitação" })).toBeInTheDocument();
    const citizenField = await screen.findByRole("combobox", { name: "Cidadão" });
    expect(citizenField).toHaveValue("Bruno Silva");
    expect(citizenField).toBeDisabled();
  });

  it("exibe o responsável na grid apenas para usuários que distribuem solicitações", async () => {
    apiRequest.mockImplementation((url) => Promise.resolve(
      String(url).startsWith("/api/v1/solicitacoes?")
        ? {
            content: [{
              id: "req-1",
              protocolo: "GF-2026-000001",
              titulo: "Iluminação pública",
              categoria: "Infraestrutura",
              origem: "EMAIL",
              prioridade: "MEDIA",
              status: "NOVA",
              responsavel: "Maria Operacional",
              criadaEm: "2026-08-07T12:00:00Z",
            }],
          }
        : { content: [] },
    ));

    const { unmount } = render(<RequestsPage user={{ role: "admin" }} />);
    expect(await screen.findByRole("columnheader", { name: "Responsável" })).toBeInTheDocument();
    expect(screen.getByText("Maria Operacional")).toBeInTheDocument();
    unmount();

    render(<RequestsPage user={{ role: "staff", chefeGabinete: false }} />);
    await screen.findByText("Iluminação pública");
    expect(screen.queryByRole("columnheader", { name: "Responsável" })).not.toBeInTheDocument();
  });

  it("pagina, ordena, filtra colunas e altera a quantidade de registros", async () => {
    apiRequest.mockImplementation((url) => {
      if (String(url).startsWith("/api/v1/solicitacoes?")) {
        return Promise.resolve({
          content: [{
            id: "req-grid",
            protocolo: "GF-2026-000321",
            titulo: "Reparo de iluminação",
            categoria: "Iluminação pública",
            origem: "WHATSAPP",
            prioridade: "ALTA",
            status: "TRIAGEM",
            responsavel: "Maria Operacional",
            criadaEm: "2026-08-07T12:00:00Z",
          }],
          page: new URL(`http://local${url}`).searchParams.get("page") === "1" ? 1 : 0,
          size: Number(new URL(`http://local${url}`).searchParams.get("size")),
          totalElements: 51,
          totalPages: 3,
        });
      }
      return Promise.resolve({ content: [] });
    });

    render(<RequestsPage user={{ role: "admin" }} />);

    expect(await screen.findByText("51 registros")).toBeInTheDocument();
    const requestCalls = () => apiRequest.mock.calls.filter(([url]) => String(url).startsWith("/api/v1/solicitacoes?"));
    expect(requestCalls().at(-1)[0]).toContain("size=25");

    fireEvent.change(screen.getByRole("combobox", { name: "Registros por página" }), { target: { value: "10" } });
    await waitFor(() => expect(requestCalls().at(-1)[0]).toContain("size=10"));

    fireEvent.click(screen.getByRole("button", { name: "Protocolo" }));
    await waitFor(() => {
      expect(requestCalls().at(-1)[0]).toContain("sort=protocolo");
      expect(requestCalls().at(-1)[0]).toContain("direction=asc");
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Filtrar protocolo" }), { target: { value: "000321" } });
    await waitFor(() => expect(requestCalls().at(-1)[0]).toContain("protocolo=000321"));

    fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
    await waitFor(() => expect(requestCalls().at(-1)[0]).toContain("page=1"));
    expect(screen.getByText("Página 2 de 3")).toBeInTheDocument();
  });

  it("permite distribuir no formulário somente para administrador, parlamentar ou chefe", () => {
    const { unmount } = render(<RequestsPage user={{ role: "staff", chefeGabinete: false }} />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.queryByRole("combobox", { name: "Responsável" })).not.toBeInTheDocument();
    unmount();

    render(<RequestsPage user={{ role: "staff", chefeGabinete: true }} />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.getByRole("combobox", { name: "Responsável" })).toBeInTheDocument();
  });

  it("oferece ao parlamentar somente a distribuição no detalhe da solicitação", async () => {
    const request = {
      id: "req-1",
      protocolo: "GF-2026-000001",
      titulo: "Iluminação pública",
      descricao: "Poste apagado",
      categoria: "Infraestrutura",
      origem: "EMAIL",
      prioridade: "MEDIA",
      status: "NOVA",
      criadaEm: "2026-08-07T12:00:00Z",
      interacoes: [],
      historico: [],
      tarefas: [],
      anexos: [],
      duplicidades: [],
      encaminhamentos: [],
      tentativasContato: [],
      retornos: [],
    };
    apiRequest.mockImplementation((url) => {
      if (url === "/api/v1/usuarios") return Promise.resolve({ content: [{ id: "user-1", nome: "Maria Operacional" }] });
      if (url === "/api/v1/solicitacoes/req-1") return Promise.resolve(request);
      if (String(url).startsWith("/api/v1/solicitacoes?")) return Promise.resolve({ content: [request] });
      return Promise.resolve({ content: [] });
    });

    render(<RequestsPage user={{ role: "representative" }} />);
    fireEvent.click(await screen.findByText("Iluminação pública"));

    const distribution = (await screen.findByRole("heading", { name: "Distribuição" })).closest("section");
    expect(within(distribution).getByRole("combobox", { name: "Responsável" })).toBeInTheDocument();
    expect(within(distribution).getByRole("button", { name: "Atualizar responsável" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Acompanhamento" })).not.toBeInTheDocument();
  });

  it("consulta o Geoapify em homologação e exige revisão humana", async () => {
    const request = {
      id: "req-geo",
      protocolo: "GF-2026-000777",
      titulo: "Localização de homologação",
      descricao: "Registro sintético",
      endereco: "Rua Halfeld, 10, Centro",
      origem: "PRESENCIAL",
      prioridade: "MEDIA",
      status: "NOVA",
      criadaEm: "2026-08-10T12:00:00Z",
      latitude: -21.76,
      longitude: -43.35,
      qualidadeGeografica: {
        origem: "GEOAPIFY",
        metodo: "HOMOLOGATION_EXTERNAL",
        confianca: 0.98,
        verificada: false,
        status: "APPROXIMATE",
        atribuicoes: ["Geoapify", "OpenStreetMap contributors"],
        revisaoPendente: true,
      },
      geocodificacaoHomologacao: {
        habilitada: true,
        podeOperar: true,
        limiteDiario: 100,
        utilizadasHoje: 1,
        restantesHoje: 99,
      },
      interacoes: [], historico: [], tarefas: [], anexos: [], duplicidades: [],
      encaminhamentos: [], tentativasContato: [], retornos: [],
    };
    apiRequest.mockImplementation((url, options) => {
      if (url === "/api/v1/solicitacoes/req-geo" && !options) return Promise.resolve(request);
      if (String(url).startsWith("/api/v1/solicitacoes?")) {
        return Promise.resolve({ content: [request], totalElements: 1, totalPages: 1 });
      }
      if (url === "/api/v1/solicitacoes/req-geo/geocodificacao/geoapify") {
        return Promise.resolve(request);
      }
      return Promise.resolve({ content: [] });
    });

    render(<RequestsPage user={{ role: "admin" }} />);
    fireEvent.click(await screen.findByText("Localização de homologação"));

    expect(await screen.findByRole("heading", { name: "Localização com Geoapify" })).toBeInTheDocument();
    expect(screen.getByText("Dados: Geoapify · OpenStreetMap contributors")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Consultar Geoapify" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Aprovar localização" })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /Confirmo que este endereço/ }));
    fireEvent.click(screen.getByRole("button", { name: "Consultar Geoapify" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/solicitacoes/req-geo/geocodificacao/geoapify",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ confirmacaoDadosTeste: true }),
      }),
    ));
    expect(await screen.findByText("Resultado recebido. Revise a localização antes de aprová-la.")).toBeInTheDocument();
  });
});
