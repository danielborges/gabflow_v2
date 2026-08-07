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

  it("abre o formulário de nova solicitação", () => {
    render(<RequestsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.getByRole("dialog", { name: "Registrar solicitação" })).toBeInTheDocument();
    expect(screen.getByLabelText("Descrição")).toBeRequired();
  });

  it("permite pesquisar e selecionar o cidadão na nova solicitação", async () => {
    apiRequest.mockImplementation((url) => {
      if (String(url).includes("/api/v1/cidadaos")) {
        return Promise.resolve({
          content: [{
            id: "cid-1",
            nome: "Bruno Silva",
            cpf: "123.456.789-00",
            canalPreferencial: "WHATSAPP",
            contatos: [{ tipo: "WHATSAPP", valor: "(32) 99999-0000" }],
          }],
        });
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
    fireEvent.change(citizenField, { target: { value: "bruno" } });
    fireEvent.click(await screen.findByText("Bruno Silva"));

    expect(citizenField).toHaveValue("Bruno Silva");
  });

  it("abre nova solicitação com o cidadão recebido do diretório pré-selecionado", async () => {
    apiRequest.mockImplementation((url) => Promise.resolve({
      content: String(url).includes("/api/v1/cidadaos")
        ? [{ id: "cid-1", nome: "Bruno Silva", contatos: [] }]
        : [],
    }));

    render(<RequestsPage initialCitizenId="cid-1" onInitialContextConsumed={vi.fn()} />);

    expect(await screen.findByRole("dialog", { name: "Registrar solicitação" })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: "Cidadão" })).toHaveValue("Bruno Silva");
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
});
