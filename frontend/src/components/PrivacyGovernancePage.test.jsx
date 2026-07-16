import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../api";
import { PrivacyGovernancePage } from "./PrivacyGovernancePage";

vi.mock("../api", () => ({
  apiRequest: vi.fn(),
  apiDownload: vi.fn(),
}));

beforeEach(() => {
  apiRequest.mockImplementation((path) => {
    if (path.includes("/resumo")) {
      return Promise.resolve({
        solicitacoesAbertas: 1,
        solicitacoesVencidas: 0,
        cidadaosAtivos: 3,
        politicasAtivas: 1,
      });
    }
    return Promise.resolve({ content: [] });
  });
});

test("exibe a central de privacidade e seus indicadores", async () => {
  render(<PrivacyGovernancePage />);

  expect(await screen.findByRole("heading", { name: "Privacidade" })).toBeInTheDocument();
  expect(screen.getByText("Solicitações abertas")).toBeInTheDocument();
  expect(screen.getByText("Direitos do titular")).toBeInTheDocument();
});
