import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { NotificationCenter } from "./NotificationCenter";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

describe("NotificationCenter", () => {
  it("permite configurar os tipos de alerta", async () => {
    apiRequest.mockImplementation((path) => {
      if (path.endsWith("/preferencias")) {
        return Promise.resolve({
          content: [
            { tipo: "ATRIBUICAO", habilitada: true },
            { tipo: "TAREFA", habilitada: true },
          ],
        });
      }
      return Promise.resolve({ content: [], naoLidas: 0 });
    });
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole("button", { name: "Notificações" }));
    fireEvent.click(await screen.findByRole("button", { name: "Configurar notificações" }));
    const assignment = await screen.findByRole("checkbox", { name: /Atribuições/ });
    fireEvent.click(assignment);
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/v1/notificacoes/preferencias",
        expect.objectContaining({ method: "PUT" }),
      );
    });
  });
});
