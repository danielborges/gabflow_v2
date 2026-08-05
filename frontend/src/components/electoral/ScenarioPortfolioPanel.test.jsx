import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../../api";
import { ScenarioPortfolioPanel } from "./ScenarioPortfolioPanel";

vi.mock("../../api", () => ({ apiRequest: vi.fn(), apiDownload: vi.fn() }));

beforeEach(() => { apiRequest.mockReset(); });

test("cria portfólio, registra meta, referência e histórico", async () => {
  const scenarios = [
    { id: "scenario-1", name: "Cenário A", result: { territories: [{ territory_id: "territory-1", territory_name: "Centro" }] } },
    { id: "scenario-2", name: "Cenário B", result: { territories: [{ territory_id: "territory-1", territory_name: "Centro" }] } },
  ];
  const portfolio = {
    id: "portfolio-1",
    name: "Alternativas 2026",
    description: "Portfólio de homologação",
    status: "ACTIVE",
    reference_scenario_id: "scenario-1",
    goals: [],
    scenarios: [
      { id: "scenario-1", name: "Cenário A", projected_total_votes: 120, uncertainty_interval: { lower_votes: 110, upper_votes: 130 }, is_reference: true },
      { id: "scenario-2", name: "Cenário B", projected_total_votes: 140, uncertainty_interval: { lower_votes: 130, upper_votes: 150 }, is_reference: false },
    ],
    evaluation: { scenarios: [] },
  };
  const goal = { id: "goal-1", scope: "TOTAL", metric: "VOTES", target_value: 130, rationale: "Meta agregada" };
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce(portfolio)
    .mockResolvedValueOnce({
      ...portfolio,
      goals: [goal],
      evaluation: { scenarios: [{ scenario_id: "scenario-1", name: "Cenário A", is_reference: true, goals: [{ ...goal, actual_value: 120, difference: -10, attainment_percent: 92.31 }] }] },
    })
    .mockResolvedValueOnce({
      ...portfolio,
      reference_scenario_id: "scenario-2",
      scenarios: portfolio.scenarios.map((item) => ({ ...item, is_reference: item.id === "scenario-2" })),
      goals: [goal],
      evaluation: { scenarios: [] },
    })
    .mockResolvedValueOnce({ content: [{ id: "event-1", event_type: "REFERENCE_SET", created_at: "2026-08-04T12:00:00Z" }] });

  render(<ScenarioPortfolioPanel scenarios={scenarios} onError={vi.fn()} />);
  await screen.findByText(/O cenário de referência/);
  fireEvent.change(screen.getByLabelText("Nome do portfólio"), { target: { value: "Alternativas 2026" } });
  fireEvent.click(screen.getByLabelText("Cenário A"));
  fireEvent.click(screen.getByLabelText("Cenário B"));
  fireEvent.click(screen.getByRole("button", { name: "Criar portfólio" }));
  await screen.findByRole("heading", { name: "Alternativas 2026" });

  fireEvent.change(screen.getByLabelText("Valor da meta"), { target: { value: "130" } });
  fireEvent.change(screen.getByLabelText("Justificativa"), { target: { value: "Meta agregada" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar meta" }));
  await screen.findByText("92,31%");
  expect(JSON.parse(apiRequest.mock.calls[2][1].body).goals[0]).toMatchObject({
    scope: "TOTAL",
    target_value: 130,
  });

  fireEvent.click(screen.getAllByRole("button", { name: "Definir referência" })[1]);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/scenario-portfolios/portfolio-1/reference",
    expect.objectContaining({ method: "PUT" }),
  ));
  fireEvent.click(screen.getByRole("button", { name: "Ver histórico" }));
  expect(await screen.findByText("REFERENCE_SET")).toBeInTheDocument();
});
