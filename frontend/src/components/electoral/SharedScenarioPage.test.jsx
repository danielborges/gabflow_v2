import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../../api";
import { SharedScenarioPage } from "./SharedScenarioPage";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

beforeEach(() => { apiRequest.mockReset(); });

test("renderiza o cenário compartilhado sem ações de escrita", async () => {
  apiRequest.mockResolvedValueOnce({
    id: "scenario-1",
    name: "Cenário compartilhado",
    read_only: true,
    disclaimer: "SIMULAÇÃO HIPOTÉTICA.",
    methodology_version: "territorial-assumption-range-v2",
    assumptions: [{
      territory_id: "territory-1",
      candidate_share_delta: 0.1,
      denominator_delta: 0,
      candidate_share_uncertainty: 0.02,
      denominator_uncertainty: 0.01,
      rationale: "Premissa pública",
    }],
    baseline_snapshot: { dataset_version: "dataset-1", candidate: { name: "Candidata A" } },
    result: {
      baseline_total_votes: 100,
      projected_total_votes: 120,
      uncertainty_interval: { lower_votes: 110, projected_votes: 120, upper_votes: 130, disclaimer: "Faixa determinística." },
      territories: [{
        territory_id: "territory-1",
        territory_name: "Centro",
        baseline_votes: 100,
        projected_votes: 120,
        vote_difference: 20,
        uncertainty_interval: { lower_votes: 110, upper_votes: 130 },
      }],
    },
  });
  render(<SharedScenarioPage token="safe-token" />);

  expect(await screen.findByRole("heading", { name: "Cenário compartilhado" })).toBeInTheDocument();
  expect(screen.getByText("Somente leitura")).toBeInTheDocument();
  expect(screen.getByText("Premissa pública")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(apiRequest).toHaveBeenCalledWith("/api/v1/electoral/scenarios/shared/safe-token");
});
