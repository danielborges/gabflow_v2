import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../../api";
import { CandidateComparison } from "./CandidateComparison";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

const candidates = [
  { id: "candidate-1", ballot_name: "ANA SILVA", full_name: "ANA MARIA SILVA", number: "10100", party: { acronym: "PARTIDO A" } },
  { id: "candidate-2", ballot_name: "BRUNO LIMA", full_name: "BRUNO SOUZA LIMA", number: "20200", party: { acronym: "PARTIDO B" } },
];

function ComparisonHarness({ onCompare = vi.fn() }) {
  const [selected, setSelected] = useState([]);
  return <CandidateComparison
    elections={[{ id: "election-1", nome: "Eleições Municipais 2024" }]}
    electionId="election-1"
    onElectionChange={vi.fn()}
    selected={selected}
    response={null}
    loading={false}
    onCompare={onCompare}
    onToggle={(candidate) => setSelected((current) => current.some((item) => item.id === candidate.id)
      ? current.filter((item) => item.id !== candidate.id)
      : [...current, candidate])}
    onRemove={(candidateId) => setSelected((current) => current.filter((item) => item.id !== candidateId))}
    onSave={vi.fn()}
    onLoadSaved={vi.fn()}
    onDeleteSaved={vi.fn()}
  />;
}

beforeEach(() => {
  vi.clearAllMocks();
  apiRequest.mockResolvedValue({ items: candidates, total: 2, page: 1, perPage: 20 });
});

test("pesquisa e seleciona candidaturas sem depender da tela de resultados", async () => {
  const onCompare = vi.fn();
  render(<ComparisonHarness onCompare={onCompare} />);

  expect(screen.queryByText(/Abra Resultados eleitorais/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Comparar 0 candidaturas" })).toBeDisabled();

  fireEvent.change(screen.getByLabelText("Buscar candidatura"), { target: { value: "Silva" } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

  const selectionLabels = await screen.findAllByText("Selecionar");
  fireEvent.click(selectionLabels[0].closest("button"));
  fireEvent.click(screen.getByText("Selecionar").closest("button"));

  expect(screen.getByText("2/5 selecionadas")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Comparar 2 candidaturas" }));
  expect(onCompare).toHaveBeenCalledOnce();
});

test("usa o seletor padronizado do GabFlow para a métrica", () => {
  render(<ComparisonHarness />);

  const metric = screen.getByLabelText("Métrica");
  expect(metric.closest(".electoral-select-control")).not.toBeNull();
  fireEvent.change(metric, { target: { value: "share" } });
  expect(metric).toHaveValue("share");
});
