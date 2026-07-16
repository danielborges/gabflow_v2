import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Login } from "./Login";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("Login", () => {
  it("exibe os campos obrigatórios de acesso", () => {
    render(<Login onLogin={() => {}} />);
    expect(screen.getByRole("img", { name: "GabFlow - Gestão que move resultados" }))
      .toHaveAttribute("src", "/images/logo_01.png");
    expect(screen.getByLabelText("Ambiente")).toBeRequired();
    expect(screen.getByLabelText("E-mail")).toBeRequired();
    expect(screen.getByLabelText("Senha")).toBeRequired();
  });

  it("permite alternar a visibilidade da senha", () => {
    render(<Login onLogin={() => {}} />);
    const password = screen.getByLabelText("Senha");
    fireEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(password).toHaveAttribute("type", "text");
  });
});
