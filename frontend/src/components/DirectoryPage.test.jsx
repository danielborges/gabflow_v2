import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail } from "../contactValidation";
import { DirectoryPage } from "./DirectoryPage";

vi.mock("../api", () => ({ apiDownload: vi.fn(), apiRequest: vi.fn() }));

describe("cadastro de cidadão", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ content: [] });
  });

  it("formata telefones brasileiros fixos e celulares", () => {
    expect(formatBrazilianPhone("32987001487")).toBe("(32) 98700-1487");
    expect(formatBrazilianPhone("3232211234")).toBe("(32) 3221-1234");
  });

  it("valida telefone e e-mail", () => {
    expect(isValidBrazilianPhone("(32) 98700-1487")).toBe(true);
    expect(isValidBrazilianPhone("329870014")).toBe(false);
    expect(isValidEmail("pessoa@exemplo.com.br")).toBe(true);
    expect(isValidEmail("pessoa@exemplo")).toBe(false);
  });

  it("habilita apenas iniciais existentes e apresenta cards completos da agenda", async () => {
    const citizen = {
      id: "cid-card",
      nome: "Carla Menezes",
      contatos: [
        { tipo: "TELEFONE", valor: "31984141102" },
        { tipo: "EMAIL", valor: "carla.m@exemplo.com" },
      ],
      enderecos: [{ cidade: "Belo Horizonte", bairro: "Centro" }],
      canalPreferencial: "EMAIL",
      profissao: "Arquiteta",
      vip: true,
    };
    apiRequest.mockImplementation((url) => Promise.resolve(
      url.startsWith("/api/v1/cidadaos?")
        ? { content: [citizen], letrasDisponiveis: ["C", "M"], proximoCursor: null }
        : { content: [] },
    ));

    render(<DirectoryPage />);

    const enabledLetter = await screen.findByRole("button", { name: "Filtrar pela letra C" });
    const disabledLetter = screen.getByRole("button", { name: "Letra J sem cadastros" });
    const clearLetter = screen.getByRole("button", { name: "Limpar filtro por letra" });
    expect(enabledLetter).toBeEnabled();
    expect(disabledLetter).toBeDisabled();
    expect(clearLetter).toBeDisabled();
    expect(screen.getByText("(31) 98414-1102")).toBeInTheDocument();
    expect(screen.getByText(/carla\.m@exemplo\.com · Centro · Arquiteta · Prefere contato por e-mail/)).toBeInTheDocument();
    expect(screen.getByLabelText("Cidadão VIP")).toBeInTheDocument();

    fireEvent.click(enabledLetter);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining("letra=C")));
    expect(enabledLetter).toHaveAttribute("aria-pressed", "true");
    expect(clearLetter).toBeEnabled();
    expect(window.location.search).toContain("letraCidadao=C");

    const citizenRequestsBeforeClear = apiRequest.mock.calls.filter(([url]) => url.startsWith("/api/v1/cidadaos?")).length;
    fireEvent.click(clearLetter);

    await waitFor(() => {
      const citizenRequests = apiRequest.mock.calls.filter(([url]) => url.startsWith("/api/v1/cidadaos?"));
      expect(citizenRequests).toHaveLength(citizenRequestsBeforeClear + 1);
      expect(citizenRequests.at(-1)[0]).not.toContain("letra=");
    });
    expect(enabledLetter).toHaveAttribute("aria-pressed", "false");
    expect(clearLetter).toBeDisabled();
    expect(window.location.search).not.toContain("letraCidadao");
  });

  it("mantém organizações no mesmo padrão de aba, busca, agenda e formulário embutido", async () => {
    const organization = {
      id: "org-1",
      nome: "Associação Bairro Vivo",
      tipo: "ASSOCIACAO",
      contatos: [
        { tipo: "TELEFONE", valor: "31988776655" },
        { tipo: "EMAIL", valor: "contato@bairrovivo.org" },
      ],
      enderecos: [{ endereco: "Rua das Flores, 10" }],
      territorio: "Centro",
      observacoes: "Atendimento comunitário",
      criadaEm: "2026-08-01T10:00:00Z",
      atualizadaEm: "2026-08-02T11:00:00Z",
    };
    apiRequest.mockImplementation((url) => {
      if (url === "/api/v1/organizacoes") return Promise.resolve({ content: [organization] });
      if (url === "/api/v1/organizacoes/org-1") return Promise.resolve(organization);
      if (url.startsWith("/api/v1/cidadaos?")) return Promise.resolve({ content: [], letrasDisponiveis: [], proximoCursor: null });
      return Promise.resolve({ content: [] });
    });

    render(<DirectoryPage />);

    const organizationsTab = screen.getByRole("tab", { name: "Organizações" });
    expect(organizationsTab).toHaveAttribute("aria-selected", "false");
    fireEvent.click(organizationsTab);

    expect(organizationsTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Cadastros de organizações" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Buscar organizações" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Editar organização Associação Bairro Vivo" })).toBeInTheDocument();
    expect(screen.getByText("contato@bairrovivo.org · Associação · Centro")).toBeInTheDocument();
    expect(screen.getByText("(31) 98877-6655")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Editar organização Associação Bairro Vivo" }));
    expect(await screen.findByRole("region", { name: "Editar organização" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Editar organização" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Nova organização" }));
    expect(screen.getByRole("region", { name: "Cadastrar organização" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Cadastrar organização" })).not.toBeInTheDocument();
  });

  it("aplica a máscara e impede o envio de contatos inválidos", async () => {
    render(<DirectoryPage />);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole("button", { name: /novo cidadão/i }));
    expect(screen.getByRole("region", { name: "Cadastrar cidadão" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Cadastrar cidadão" })).not.toBeInTheDocument();

    const phone = screen.getByLabelText("Telefone");
    fireEvent.change(phone, { target: { value: "32987001487" } });
    expect(phone).toHaveValue("(32) 98700-1487");

    fireEvent.change(phone, { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "email-invalido" } });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Daniel Borges" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));

    expect(await screen.findByText(/telefone válido com DDD/i)).toBeInTheDocument();
    expect(screen.getByText(/e-mail válido/i)).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledTimes(3);
  });

  it("abre o cidadão pelo card e salva as alterações", async () => {
    const citizen = {
      id: "cid-1",
      versao: 1,
      nome: "Daniel Borges",
      nomeSocial: "Daniel",
      contatos: [
        { tipo: "TELEFONE", valor: "32987001487" },
        { tipo: "EMAIL", valor: "daniel@exemplo.com" },
      ],
      enderecos: [{ endereco: "Rua Central, 10", referencia: "Centro" }],
      canalPreferencial: "WHATSAPP",
      baseLegal: "EXECUCAO_POLITICA_PUBLICA",
      consentimentoContato: true,
      consentimentoDivulgacao: false,
    };
    apiRequest.mockImplementation((url, options) => {
      if (options?.method === "PATCH") return Promise.resolve(citizen);
      if (url === "/api/v1/cidadaos/cid-1") return Promise.resolve(citizen);
      return Promise.resolve({ content: url.includes("cidadaos") ? [citizen] : [] });
    });

    render(<DirectoryPage />);
    const card = await screen.findByRole("button", { name: "Editar cidadão Daniel Borges" });
    fireEvent.click(card);

    expect(await screen.findByRole("region", { name: "Editar cidadão" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Editar cidadão" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Telefone")).toHaveValue("(32) 98700-1487");
    expect(screen.getByLabelText("E-mail")).toHaveValue("daniel@exemplo.com");
    expect(screen.getByLabelText("Endereço")).toHaveValue("Rua Central, 10");

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Daniel Borges da Silva" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/cidadaos/cid-1",
      expect.objectContaining({ method: "PATCH", headers: { "If-Match": '"1"' } }),
    ));
    const updateCall = apiRequest.mock.calls.find(([, options]) => options?.method === "PATCH");
    const payload = JSON.parse(updateCall[1].body);
    expect(payload).toMatchObject({
      nome: "Daniel Borges da Silva",
      nomeSocial: "Daniel",
      profissao: "",
      dataNascimento: null,
      cpf: null,
      tituloEleitor: null,
      vip: false,
      organizacaoIds: [],
      endereco: { endereco: "Rua Central, 10", referencia: "Centro" },
      consentimentoContato: true,
    });
  });

  it("alerta sobre homônimo e exige confirmação para criar outro cadastro", async () => {
    const homonym = { id: "cid-existing", nome: "Ana Souza", contatos: [] };
    apiRequest.mockImplementation((url, options) => {
      if (url === "/api/v1/cidadaos/verificar-duplicidade") {
        return Promise.resolve({ cpfDuplicado: null, homonimos: [homonym] });
      }
      if (options?.method === "POST" && url === "/api/v1/cidadaos") {
        return Promise.resolve({ id: "cid-new", nome: "Ana Souza" });
      }
      return Promise.resolve({ content: [] });
    });

    render(<DirectoryPage />);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole("button", { name: /novo cidadão/i }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ana Souza" } });
    fireEvent.click(screen.getByRole("button", { name: /^salvar$/i }));

    expect(await screen.findByText("Encontramos possíveis homônimos")).toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalledWith("/api/v1/cidadaos", expect.objectContaining({ method: "POST" }));

    fireEvent.click(screen.getByRole("button", { name: "Criar mesmo assim" }));
    fireEvent.click(screen.getByRole("button", { name: /^salvar$/i }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/cidadaos",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("impede sobrescrita silenciosa quando a versão do cadastro mudou", async () => {
    const citizen = {
      id: "cid-conflict", nome: "Ana Concorrente", versao: 3, contatos: [], enderecos: [],
      baseLegal: "EXECUCAO_POLITICA_PUBLICA",
    };
    apiRequest.mockImplementation((url, options) => {
      if (url.includes("/solicitacoes") || url.includes("/historico")) {
        return Promise.resolve({ content: [], proximoCursor: null });
      }
      if (options?.method === "PATCH") {
        const error = new Error("Este cadastro foi alterado por outro usuário.");
        error.status = 412;
        return Promise.reject(error);
      }
      if (url === "/api/v1/cidadaos/cid-conflict") return Promise.resolve(citizen);
      return Promise.resolve({ content: url.includes("cidadaos") ? [citizen] : [] });
    });

    render(<DirectoryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Editar cidadão Ana Concorrente" }));
    await screen.findByRole("region", { name: "Editar cidadão" });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ana Editada" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByText(/alterado por outro usuário/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Recarregar cadastro/ })).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/cidadaos/cid-conflict",
      expect.objectContaining({ headers: { "If-Match": '"3"' } }),
    );
  });
});
