import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  });

  it("abre o formulário de nova solicitação", () => {
    render(<RequestsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.getByRole("dialog", { name: "Registrar solicitação" })).toBeInTheDocument();
    expect(screen.getByLabelText("Descrição")).toBeRequired();
  });
});

