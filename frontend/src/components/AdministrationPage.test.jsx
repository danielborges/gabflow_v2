import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AdministrationPage, WhatsAppFlowsManager, WhatsAppPilotOperations, WhatsAppTemplatesManager } from "./AdministrationPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("WhatsApp pilot operations", () => {
  it("apresenta SLOs, gates e permite pausar a saída com motivo", async () => {
    const pilot = {
      status: "RUNNING", prontoExterno: true, prontoInterno: true, prontoOperacional: true, podeIniciar: true,
      gates: [{ key: "RUNBOOKS_INCIDENTS", titulo: "Runbooks e incidentes", status: "PASSED", evidenciaReferencia: "ticket:42", observacao: "" }],
      operacao: {
        status: "GOOD", windowHours: 24,
        inbound: { received: 18, ackP95Ms: 120, processingStartWithinTargetRate: 1 },
        outbox: { pending: 0, oldestAgeSeconds: 0 },
        slo: { ackP95TargetMs: 500, processingStartTargetRate: .99 },
        alerts: [{ nivel: "GOOD", codigo: "PIPELINE_HEALTHY", titulo: "Pipeline saudável", valor: 18 }],
      },
    };
    apiRequest.mockReset();
    apiRequest.mockResolvedValue(pilot);

    render(<WhatsAppPilotOperations tenantId="tenant-a" canManage />);
    expect(await screen.findByText("Cockpit do piloto")).toBeInTheDocument();
    expect(screen.getByText("120 ms")).toBeInTheDocument();
    expect(screen.getByText("Runbooks e incidentes")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Motivo para pausa"), { target: { value: "Falhas de entrega" } });
    fireEvent.click(screen.getByRole("button", { name: "Pausar saídas" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/tenants/tenant-a/whatsapp/pilot/actions",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "PAUSE", reason: "Falhas de entrega" }) }),
    ));
  });
});

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

  it("cadastra aliases e polígono GeoJSON para resolução territorial", async () => {
    render(<AdministrationPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Territórios" }));

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "São Pedro" } });
    fireEvent.change(screen.getByLabelText("Aliases de bairros"), {
      target: { value: "Jardim SP\nS. Pedro" },
    });
    fireEvent.change(screen.getByLabelText("Polígono GeoJSON"), {
      target: {
        value: JSON.stringify({
          type: "Polygon",
          coordinates: [[[-43.4, -21.8], [-43.3, -21.8], [-43.3, -21.7], [-43.4, -21.7], [-43.4, -21.8]]],
        }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /Adicionar território/ }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/admin/territorios",
      expect.objectContaining({ method: "POST" }),
    ));
    const call = apiRequest.mock.calls.find(([path, options]) => (
      path === "/api/v1/admin/territorios" && options?.method === "POST"
    ));
    expect(JSON.parse(call[1].body)).toMatchObject({
      nome: "São Pedro",
      aliases: ["Jardim SP", "S. Pedro"],
      geometria: { type: "Polygon" },
    });
  });

  it("desenha e edita um polígono diretamente no mapa territorial", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path === "/api/v1/admin/jurisdicao") {
        return Promise.resolve({
          nome: "Juiz de Fora / MG",
          geojson: {
            type: "Polygon",
            coordinates: [[[-43.5, -21.9], [-43.2, -21.9], [-43.2, -21.6], [-43.5, -21.6], [-43.5, -21.9]]],
          },
        });
      }
      return mockAdminApi(path, options);
    });

    render(<AdministrationPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Territórios" }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Zona Leste" } });
    fireEvent.change(screen.getByLabelText("Aliases de bairros"), { target: { value: "Leste\nZL" } });
    fireEvent.click(screen.getByRole("button", { name: /Desenhar polígono/ }));

    const map = screen.getByRole("application", { name: /Mapa para visualizar/ });
    vi.spyOn(map, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 500, width: 900, height: 500,
      toJSON: () => ({}),
    });
    fireEvent.click(map, { clientX: 250, clientY: 350 });
    fireEvent.click(map, { clientX: 600, clientY: 350 });
    fireEvent.click(map, { clientX: 420, clientY: 140 });
    fireEvent.click(screen.getByRole("button", { name: /Concluir desenho/ }));

    expect(screen.getByText("Leste")).toBeInTheDocument();
    expect(screen.getByText("ZL")).toBeInTheDocument();
    const geometry = JSON.parse(screen.getByLabelText("Polígono GeoJSON").value);
    expect(geometry.type).toBe("Polygon");
    expect(geometry.coordinates[0]).toHaveLength(4);
    expect(geometry.coordinates[0][0]).toEqual(geometry.coordinates[0][3]);

    fireEvent.click(screen.getByRole("button", { name: /Adicionar território/ }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/admin/territorios",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("exibe o onboarding oficial da Meta quando o sandbox esta pronto", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path.endsWith("/whatsapp/readiness")) {
        return Promise.resolve({
          prontoSandbox: true,
          embeddedSignupHabilitado: true,
          pendencias: [],
        });
      }
      if (path.endsWith("/whatsapp/integration")) {
        return Promise.reject(
          Object.assign(new Error("Integração não encontrada."), { status: 404 }),
        );
      }
      return mockAdminApi(path, options);
    });

    render(<AdministrationPage user={{ tenant: { id: "tenant-a" } }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrações" }));

    expect(
      await screen.findByRole("heading", { name: "WhatsApp Business Platform" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ambiente técnico pronto")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Conectar com a Meta/ })).toBeEnabled();
  });

  it("permite ao administrador ativar uma versão de WhatsApp Flow", async () => {
    apiRequest.mockImplementation((path, options = {}) => {
      if (path.endsWith("/whatsapp/flows") && !options.method) return Promise.resolve({ content: [{
        id: "flow-1", chave: "new_service_request", nome: "Nova solicitação", versao: 1,
        ambiente: "SANDBOX", status: "DRAFT", metaFlowId: null, schemaHash: "1234567890abcdef",
        telas: ["CATEGORY", "DETAILS", "REVIEW"],
      }] });
      if (path.endsWith("/whatsapp/flows/flow-1/activate")) return Promise.resolve({});
      return mockAdminApi(path, options);
    });

    render(<WhatsAppFlowsManager tenantId="tenant-a" canManage />);
    fireEvent.change(await screen.findByLabelText("ID do Flow na Meta"), { target: { value: "meta-flow-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Ativar versão" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/tenants/tenant-a/whatsapp/flows/flow-1/activate",
      { method: "POST", body: JSON.stringify({ metaFlowId: "meta-flow-123" }) },
    ));
  });
});

it("cria e acompanha templates oficiais do WhatsApp", async () => {
  apiRequest.mockImplementation((path, options = {}) => {
    if (path === "/api/v1/tenants/tenant-a/whatsapp/templates" && options.method === "POST") {
      return Promise.resolve({ id: "template-1", status: "PENDING" });
    }
    if (path === "/api/v1/tenants/tenant-a/whatsapp/templates") return Promise.resolve({ content: [] });
    return Promise.resolve({});
  });
  render(<WhatsAppTemplatesManager tenantId="tenant-a" canCreate />);
  fireEvent.change(await screen.findByPlaceholderText("atualizacao_protocolo"), { target: { value: "retorno_protocolo" } });
  fireEvent.change(screen.getByPlaceholderText("A solicitação {{1}} foi atualizada."), { target: { value: "O protocolo {{1}} foi atualizado." } });
  fireEvent.change(screen.getByPlaceholderText("protocolo"), { target: { value: "protocolo" } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar para aprovação" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/tenants/tenant-a/whatsapp/templates",
    expect.objectContaining({ method: "POST" }),
  ));
});
