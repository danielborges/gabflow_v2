import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail } from "../contactValidation";
import { DirectoryPage } from "./DirectoryPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("cadastro de cidadão", () => {
  beforeEach(() => {
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

  it("aplica a máscara e impede o envio de contatos inválidos", async () => {
    render(<DirectoryPage />);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: /novo cidadão/i }));

    const phone = screen.getByLabelText("Telefone");
    fireEvent.change(phone, { target: { value: "32987001487" } });
    expect(phone).toHaveValue("(32) 98700-1487");

    fireEvent.change(phone, { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "email-invalido" } });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Daniel Borges" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));

    expect(await screen.findByText(/telefone válido com DDD/i)).toBeInTheDocument();
    expect(screen.getByText(/e-mail válido/i)).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it("abre o cidadão pelo card e salva as alterações", async () => {
    const citizen = {
      id: "cid-1",
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
      return Promise.resolve({ content: url.includes("cidadaos") ? [citizen] : [] });
    });

    render(<DirectoryPage />);
    const card = await screen.findByRole("button", { name: "Editar cidadão Daniel Borges" });
    fireEvent.click(card);

    expect(screen.getByRole("dialog", { name: "Editar cidadão" })).toBeInTheDocument();
    expect(screen.getByLabelText("Telefone")).toHaveValue("(32) 98700-1487");
    expect(screen.getByLabelText("E-mail")).toHaveValue("daniel@exemplo.com");
    expect(screen.getByLabelText("Endereço")).toHaveValue("Rua Central, 10");

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Daniel Borges da Silva" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/cidadaos/cid-1",
      expect.objectContaining({ method: "PATCH" }),
    ));
    const updateCall = apiRequest.mock.calls.find(([, options]) => options?.method === "PATCH");
    const payload = JSON.parse(updateCall[1].body);
    expect(payload).toMatchObject({
      nome: "Daniel Borges da Silva",
      nomeSocial: "Daniel",
      enderecos: [{ endereco: "Rua Central, 10", referencia: "Centro" }],
      consentimentoContato: true,
    });
  });
});
