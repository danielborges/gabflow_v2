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
    expect(screen.getByText("R$ 1.990 a R$ 2.990/mes")).toBeInTheDocument();

    const leadForm = screen.getByRole("button", { name: "Cadastrar interesse" }).closest("form");
    fireEvent.change(within(leadForm).getByLabelText("Plano"), { target: { value: "premium" } });
    fireEvent.change(within(leadForm).getByLabelText("Nome"), { target: { value: "Ana Costa" } });
    fireEvent.change(within(leadForm).getByLabelText("Instituicao"), { target: { value: "Camara Modelo" } });
    fireEvent.change(within(leadForm).getByLabelText("E-mail"), { target: { value: "ana@camara.local" } });
    fireEvent.submit(leadForm);

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/public/leads", {
      method: "POST",
      body: expect.stringContaining('"plano":"premium"'),
    });
    expect(await screen.findByText(/Cadastro recebido/)).toBeInTheDocument();
  });
});
