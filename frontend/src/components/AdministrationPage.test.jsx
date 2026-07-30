import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AdministrationPage } from "./AdministrationPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const emptyCollection = { content: [] };

function mockAdminApi(path, options = {}) {
  if (options.method === "PATCH" && path === "/api/v1/admin/perfil-gabinete") {
    return Promise.resolve({});
  }

  const responses = {
    "/api/v1/admin/categorias": emptyCollection,
    "/api/v1/admin/territorios": emptyCollection,
    "/api/v1/admin/orgaos": emptyCollection,
    "/api/v1/admin/templates-resposta": emptyCollection,
    "/api/v1/admin/jurisdicao": null,
    "/api/v1/admin/integracoes": emptyCollection,
    "/api/v1/admin/perfil-gabinete": {
      dadosInstitucionais: {
        nomeGabinete: "Gabinete Teste",
        estado: "MG",
        municipio: "Juiz de Fora",
      },
      redesSociais: {},
      identidadeVisual: {},
      chefeGabineteId: "",
      contrato: { plano: "professional", limiteUsuarios: 15, usuariosAtivos: 3 },
    },
    "/api/v1/admin/parlamentar": null,
    "/api/v1/admin/usuarios": emptyCollection,
    "/api/v1/admin/partidos": emptyCollection,
    "/api/v1/admin/auditoria?page=1&perPage=10": {
      content: [],
      page: 1,
      perPage: 10,
      total: 0,
      totalPages: 1,
    },
  };

  return Promise.resolve(responses[path] ?? emptyCollection);
}

describe("AdministrationPage office settings", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation(mockAdminApi);
  });

  it("exibe jurisdição como informação bloqueada da contratação", async () => {
    render(<AdministrationPage />);

    expect(await screen.findByText("Câmara Municipal")).toBeInTheDocument();
    expect(screen.getByText("Minas Gerais - MG")).toBeInTheDocument();
    expect(screen.getByText("Juiz de Fora")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Estado" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Município" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Salvar gabinete/ }));

    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/v1/admin/perfil-gabinete",
        expect.objectContaining({
          method: "PATCH",
          body: expect.any(String),
        }),
      );
    });
    expect(apiRequest).not.toHaveBeenCalledWith(
      "/api/v1/admin/jurisdicao",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("mostra plano contratado e restringe perfis disponiveis para usuarios", async () => {
    render(<AdministrationPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Usuários" }));

    expect(await screen.findByText("Plano contratado: Professional")).toBeInTheDocument();
    expect(screen.getByText("3 de 15 usuário(s) ativo(s)")).toBeInTheDocument();

    const profile = screen.getByLabelText("Perfil");
    expect(within(profile).getByRole("option", { name: "Administrador" })).toBeInTheDocument();
    expect(within(profile).getByRole("option", { name: "Parlamentar" })).toBeInTheDocument();
    expect(within(profile).getByRole("option", { name: "Operacional" })).toBeInTheDocument();
    expect(within(profile).queryByRole("option", { name: "Gestor" })).not.toBeInTheDocument();
    expect(
      within(profile).queryByRole("option", { name: "Vereador / Deputado Estadual" }),
    ).not.toBeInTheDocument();

    const email = screen.getByLabelText("E-mail");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("placeholder", "nome@dominio.com.br");

    const cpf = screen.getByLabelText("CPF");
    fireEvent.change(cpf, { target: { value: "52998224725" } });
    expect(cpf).toHaveValue("529.982.247-25");

    const phone = screen.getByLabelText("Telefone");
    fireEvent.change(phone, { target: { value: "32999990000" } });
    expect(phone).toHaveValue("(32) 99999-0000");
  });

  it("acompanha o rollout progressivo do perfil RAG", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/assistente/calibracoes") {
        const profile = {
          id: "quality-profile-1",
          versao: 3,
          estado: "ATIVO",
          percentualCanario: 20,
          metricasOnline: { latencyBudgetExceededRate: 0.08 },
          rollout: {
            estado: "MONITORANDO",
            etapaAtual: 1,
            proximaAvaliacaoEm: "2026-07-30T18:00:00Z",
            historico: [{
              estado: "APROVADA",
              motivos: ["GATES_ONLINE_ATENDIDOS"],
            }],
          },
        };
        return Promise.resolve({ content: [profile], perfilAtivo: profile });
      }
      return mockAdminApi(path, options);
    });

    render(<AdministrationPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Qualidade RAG" }));

    expect(await screen.findByText("Calibração e rollout do RAG")).toBeInTheDocument();
    expect(screen.getAllByText("v3")).toHaveLength(2);
    expect(screen.getAllByText("20%")).toHaveLength(2);
    expect(screen.getAllByText("MONITORANDO")).toHaveLength(2);
    expect(screen.getByText("8%")).toBeInTheDocument();
    expect(screen.getByText(/GATES_ONLINE_ATENDIDOS/)).toBeInTheDocument();
  });

  it("edita usuario selecionado na tabela usando o mesmo formulario", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/admin/usuarios") {
        return Promise.resolve({
          content: [{
            id: "user-1",
            nome: "Ana Operacional",
            email: "ana@gabinete.com.br",
            cpf: "529.982.247-25",
            telefone: "(32) 99999-0000",
            perfil: "staff",
            status: "active",
          }],
        });
      }
      return mockAdminApi(path, options);
    });

    render(<AdministrationPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Usuários" }));

    expect(await screen.findByRole("columnheader", { name: "Nome" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Acesso" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("row", { name: /Ana Operacional/ }));

    expect(screen.getByText("Editar usuário")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveValue("Ana Operacional");
    expect(screen.getByLabelText("E-mail")).toHaveValue("ana@gabinete.com.br");
    expect(screen.getByRole("button", { name: /Salvar usuário/ })).toBeInTheDocument();
  });
});
