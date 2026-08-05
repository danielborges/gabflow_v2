import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "../../api";
import { MandateIntelligencePanel } from "./MandateIntelligencePanel";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

it("gera snapshot integrado sem usar votos no ICT", async () => {
  const snapshot = {
    id: "snapshot-1", period_start: "2026-01-01", period_end: "2026-01-31",
    source_cutoff_at: "2026-02-01T12:00:00Z", privacy_threshold: 10,
    config_hash: "1234567890abcdef",
    electoral_context: { available: true, candidate_name: "Maurício Delgado", party: "REDE", votes: 4321, year: 2024, warning: "Não integra o ICT." },
    payload: { territories: [{ scope: "mandate", territory_id: null, territory_name: "Mandato inteiro", demand_count: 12, suppressed: false, ict: { score: 72.5 }, metrics: { resolved: 8, sla_rate: 0.9, agenda_realized: 2, deliveries_with_evidence: 3 }, alerts: [] }] },
  };
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path.endsWith("coverage-profile")) return { formula_code: "ICT-1.0", version: 1 };
    if (path.endsWith("mandate-snapshots") && options.method === "POST") return snapshot;
    return { content: [] };
  });
  render(<MandateIntelligencePanel electionId="election-1" selectedCandidate={{ id: "candidate-1" }} onError={vi.fn()} />);
  await screen.findByText(/ICT-1.0/);
  fireEvent.click(screen.getByRole("button", { name: "Gerar snapshot" }));

  expect(await screen.findByText("Maurício Delgado · REDE")).toBeInTheDocument();
  expect(screen.getByText("72.5")).toBeInTheDocument();
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/mandate-snapshots",
    expect.objectContaining({ method: "POST" }),
  ));
  const request = apiRequest.mock.calls.find(([, options]) => options?.method === "POST")[1];
  expect(JSON.parse(request.body)).toMatchObject({ election_id: "election-1", candidate_id: "candidate-1" });
});

it("exibe supressão quando o grupo não alcança o limiar", async () => {
  apiRequest.mockImplementation(async (path) => path.endsWith("coverage-profile")
    ? { formula_code: "ICT-1.0", version: 1 }
    : { content: [{ id: "snapshot-2", period_start: "2026-01-01", period_end: "2026-01-31", source_cutoff_at: "2026-02-01T12:00:00Z", privacy_threshold: 10, config_hash: "abcdef1234567890", electoral_context: { available: false }, payload: { territories: [{ scope: "mandate", suppressed: true, alerts: ["Dados ocultos"] }] } }] });
  render(<MandateIntelligencePanel onError={vi.fn()} />);
  expect(await screen.findByText("Indicadores do mandato suprimidos pelo limiar de privacidade.")).toBeInTheDocument();
});

it("abre briefing agregado e salva preferências individuais de alerta", async () => {
  const preference = {
    enabled: true,
    channels: ["IN_APP"],
    frequency: "DAILY",
    alert_types: ["SLA_OVERDUE"],
  };
  const snapshot = {
    id: "snapshot-3",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    source_cutoff_at: "2026-02-01T12:00:00Z",
    privacy_threshold: 10,
    config_hash: "abcdef1234567890",
    electoral_context: { available: false },
    payload: {
      territories: [{
        scope: "territory", territory_id: "territory-1", territory_name: "Centro",
        suppressed: false, demand_count: 14, ict: { score: 68 },
        metrics: { sla_rate: 0.75, agenda_realized: 1, oversight_completed: 1, deliveries_with_evidence: 4 },
        public_commitments: { total: 2, overdue: 1 },
      }],
    },
  };
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path.endsWith("coverage-profile")) return { formula_code: "ICT-1.0", version: 1 };
    if (path.endsWith("mandate-snapshots")) return { content: [snapshot] };
    if (path.endsWith("alert-preferences") && options.method === "PUT") return {
      ...preference, channels: ["IN_APP", "EMAIL"], frequency: "WEEKLY",
    };
    if (path.endsWith("alert-preferences")) return preference;
    if (path.endsWith("/alerts")) return { content: [{ type: "SLA_OVERDUE" }] };
    if (path.includes("/briefing?")) return {
      title: "Briefing territorial — Centro",
      privacy: { suppressed: false },
      facts: [{ label: "Demandas agregadas", value: 14 }],
      alerts: [{ type: "SLA_OVERDUE", message: "4 demandas com SLA vencido." }],
      methodology_notice: "Rascunho agregado que não usa desempenho eleitoral.",
    };
    return { content: [] };
  });
  render(<MandateIntelligencePanel onError={vi.fn()} />);

  fireEvent.click(await screen.findByRole("button", { name: "Abrir briefing" }));
  expect(await screen.findByRole("heading", { name: "Briefing territorial — Centro" })).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("E-mail"));
  fireEvent.change(screen.getByLabelText("Frequência dos alertas"), { target: { value: "WEEKLY" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar alertas" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/alert-preferences",
    expect.objectContaining({ method: "PUT" }),
  ));
  const request = apiRequest.mock.calls.find(([, options]) => options?.method === "PUT")[1];
  expect(JSON.parse(request.body)).toMatchObject({
    channels: ["IN_APP", "EMAIL"],
    frequency: "WEEKLY",
  });
});
