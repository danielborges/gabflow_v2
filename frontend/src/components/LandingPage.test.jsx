import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { LandingPage } from "./LandingPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("LandingPage", () => {
  it("apresenta planos e cadastra interesse comercial", async () => {
    apiRequest.mockResolvedValueOnce({ id: "lead-1", status: "new", plano: "premium" });

    render(<LandingPage />);

    expect(screen.getByText("Sistema Operacional para Mandatos")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Multiplique a capacidade do gabinete/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Professional" })).toBeInTheDocument();
    expect(screen.getByText("R$ 1.997/mês")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Enterprise" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Todas as funcionalidades incluídas")).toHaveLength(3);
    expect(screen.queryByText("Clientes GabFlow")).not.toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Quem somos");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Versão 0.1.0");

    const leadForm = screen.getByRole("button", { name: "Cadastrar interesse" }).closest("form");
    fireEvent.change(within(leadForm).getByLabelText("Plano"), { target: { value: "premium" } });
    fireEvent.change(within(leadForm).getByLabelText("Estado"), { target: { value: "SP" } });
    fireEvent.change(within(leadForm).getByLabelText("Município"), { target: { value: "3550308" } });
    fireEvent.change(within(leadForm).getByLabelText("Nome do Gabinete"), { target: { value: "Camara Modelo" } });
    fireEvent.change(within(leadForm).getByLabelText("Administrador do gabinete"), { target: { value: "Ana Costa" } });
    fireEvent.change(within(leadForm).getByLabelText("Telefone"), { target: { value: "1133330000" } });
    fireEvent.change(within(leadForm).getByLabelText("WhatsApp"), { target: { value: "11999990000" } });
    fireEvent.change(within(leadForm).getByLabelText("Email"), { target: { value: "ana@camara.local" } });
    fireEvent.change(within(leadForm).getByLabelText("Forma Preferencial de contato"), { target: { value: "whatsapp" } });
    fireEvent.change(within(leadForm).getByLabelText("Como encontrou o GabFlow"), { target: { value: "instagram" } });
    fireEvent.submit(leadForm);

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/public/leads", {
      credentials: "omit",
      method: "POST",
      skipCsrf: true,
      body: expect.stringContaining('"plano":"premium"'),
    });
    expect(apiRequest.mock.calls[0][1].body).toContain('"municipioIbgeId":"3550308"');
    expect(await screen.findByText(/Cadastro recebido/)).toBeInTheDocument();
  });
});
