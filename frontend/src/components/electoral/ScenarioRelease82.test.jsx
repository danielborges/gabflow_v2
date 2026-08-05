import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../../api";
import { ScenarioPanel } from "./ScenarioPanel";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

beforeEach(() => { apiRequest.mockReset(); });

test("finaliza cópia, compartilhamento, comparação e sensibilidade", async () => {
  const scenario = (id, name, votes) => ({
    id,
    name,
    assumptions: [{
      territory_id: "territory-1",
      candidate_share_delta: 0.1,
      denominator_delta: 0,
      candidate_share_uncertainty: 0.02,
      denominator_uncertainty: 0.01,
      rationale: "Premissa original",
    }],
    result: {
      baseline_total_votes: 100,
      projected_total_votes: votes,
      uncertainty_interval: { lower_votes: votes - 5, upper_votes: votes + 5 },
    },
    baseline_snapshot: { dataset_version: "dataset-1" },
    methodology_version: "territorial-assumption-range-v2",
  });
  const first = scenario("scenario-1", "Base territorial", 120);
  const second = scenario("scenario-2", "Alternativa", 130);
  apiRequest
    .mockResolvedValueOnce({ content: [first, second] })
    .mockResolvedValueOnce({
      analysis_type: "COMPARISON",
      result: {
        scenarios: [
          { scenario_id: first.id, name: first.name, projected_total_votes: 120, difference_from_baseline: 20, difference_from_anchor: 0, uncertainty_interval: { lower_votes: 115, upper_votes: 125 } },
          { scenario_id: second.id, name: second.name, projected_total_votes: 130, difference_from_baseline: 30, difference_from_anchor: 10, uncertainty_interval: { lower_votes: 125, upper_votes: 135 } },
        ],
        territories: [{
          territory_id: "territory-1",
          territory_name: "Centro",
          scenarios: [
            { scenario_id: first.id, projected_votes: 120, projected_share: 0.4 },
            { scenario_id: second.id, projected_votes: 130, projected_share: 0.43 },
          ],
        }],
      },
    })
    .mockResolvedValueOnce({ ...first, id: "scenario-copy", name: "Base territorial - cópia" })
    .mockResolvedValueOnce({
      id: "share-1",
      scenario_id: first.id,
      url: "http://localhost/inteligencia-eleitoral/cenarios/compartilhado/token",
    })
    .mockResolvedValueOnce({ content: [{ id: "share-1", status: "ACTIVE", expires_at: "2026-08-11T12:00:00Z", access_count: 0 }] })
    .mockResolvedValueOnce({
      analysis_type: "SENSITIVITY",
      result: {
        minimum_projected_total_votes: 110,
        baseline_projected_total_votes: 120,
        maximum_projected_total_votes: 140,
        disclaimer: "Faixa determinística sem confiança estatística.",
        samples: [{ candidate_share_offset: -0.02, denominator_offset: 0.03, projected_total_votes: 110 }],
      },
    });
  render(<ScenarioPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    results={{ items: [{ territory_id: "territory-1", territory_name: "Centro" }] }}
    level="municipality"
    onError={vi.fn()}
  />);

  const cards = await screen.findAllByRole("article");
  fireEvent.click(within(cards[0]).getByLabelText("Selecionar para comparar"));
  fireEvent.click(within(cards[1]).getByLabelText("Selecionar para comparar"));
  fireEvent.click(screen.getByRole("button", { name: "Comparar 2 cenários" }));
  await screen.findByText("Detalhamento territorial");

  fireEvent.click(within(cards[0]).getByRole("button", { name: "Copiar e editar" }));
  fireEvent.change(screen.getByLabelText("Participação da premissa 1 (p.p.)"), { target: { value: "15" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar cópia" }));
  await screen.findByText("Base territorial - cópia");
  expect(JSON.parse(apiRequest.mock.calls[2][1].body).assumptions[0].candidate_share_delta).toBe(0.15);

  fireEvent.click(within(cards[0]).getByRole("button", { name: "Criar link" }));
  fireEvent.change(screen.getByLabelText("Validade do link (dias)"), { target: { value: "14" } });
  fireEvent.click(screen.getByRole("button", { name: "Gerar link somente leitura" }));
  await screen.findByLabelText("URL compartilhada");
  expect(JSON.parse(apiRequest.mock.calls[3][1].body)).toEqual({ expires_in_days: 14 });

  fireEvent.click(within(cards[0]).getByRole("button", { name: /Configurar sensibilidade/ }));
  fireEvent.change(screen.getByLabelText("Amplitude de participação (p.p.)"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Passos da grade"), { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Executar sensibilidade" }));
  await screen.findByText("Resultado da sensibilidade");
  expect(JSON.parse(apiRequest.mock.calls[5][1].body)).toMatchObject({
    candidate_share_range_pp: 2,
    steps: 3,
  });
});
