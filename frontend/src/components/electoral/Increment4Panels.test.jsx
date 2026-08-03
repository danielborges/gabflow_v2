import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "../../api";
import { DelegationPanel } from "./DelegationPanel";
import { ReportJobs } from "./ReportJobs";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

it("solicita exportacao assincrona com finalidade obrigatoria", async () => {
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path === "/api/v1/electoral/report-jobs" && options.method === "POST") {
      return { id: "job-1", format: "PDF", report_type: "candidate", purpose: "Planejamento territorial interno", status: "QUEUED" };
    }
    return { content: [] };
  });
  render(<ReportJobs electionId="election-1" selectedCandidate={{ id: "candidate-1" }} comparisonCandidates={[]} level="municipality" onError={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Finalidade obrigatória"), { target: { value: "Planejamento territorial interno" } });
  fireEvent.click(screen.getByRole("button", { name: "Gerar exportação" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/report-jobs",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByText("Na fila")).toBeInTheDocument();
});

it("concede somente as capacidades selecionadas por prazo e motivo", async () => {
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path === "/api/v1/electoral/delegations" && options.method === "POST") return { id: "delegation-1" };
    return { content: [], eligible_users: [{ id: "staff-1", name: "Assessora Teste", role: "staff" }] };
  });
  render(<DelegationPanel onError={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText("Assessor"), { target: { value: "staff-1" } });
  fireEvent.click(screen.getByLabelText("Exportar relatórios"));
  fireEvent.change(screen.getByLabelText("Motivo obrigatório"), { target: { value: "Preparar relatório para revisão interna" } });
  fireEvent.click(screen.getByRole("button", { name: "Conceder acesso" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/delegations",
    expect.objectContaining({ method: "POST" }),
  ));
  const request = apiRequest.mock.calls.find(([, options]) => options?.method === "POST")[1];
  expect(JSON.parse(request.body).capabilities).toEqual([
    "consultar_dados_publicos",
    "exportar",
  ]);
});
