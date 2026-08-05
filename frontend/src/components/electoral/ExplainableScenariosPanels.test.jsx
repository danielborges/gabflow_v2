import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { apiRequest } from "../../api";
import { ExplainableInsightsPanel } from "./ExplainableInsightsPanel";
import { ScenarioPanel } from "./ScenarioPanel";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

beforeEach(() => {
  apiRequest.mockReset();
});

test("solicita insight explicável para a candidatura selecionada", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({ id: "insight-1", analysis_type: "candidate", status: "QUEUED" });
  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText("Nenhum insight solicitado.");
  expect(screen.getByRole("button", { name: "Analisar com a GabIA" }).closest(".electoral-insight-context")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a GabIA" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/insights",
    expect.objectContaining({ method: "POST" }),
  ));
  const request = apiRequest.mock.calls[1][1];
  expect(JSON.parse(request.body)).toMatchObject({
    type: "candidate",
    election_id: "election-1",
    candidate_ids: ["candidate-1"],
  });
});

test("pesquisa e seleciona candidatura dentro da própria GabIA", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({
      items: [{
        id: "candidate-2",
        ballot_name: "AARON GORDÃO",
        full_name: "AARON FONT JULIA",
        number: "35000",
        party: { acronym: "PMB" },
      }],
    })
    .mockResolvedValueOnce({ id: "insight-2", analysis_type: "candidate", status: "QUEUED" });

  render(<ExplainableInsightsPanel
    elections={[{ id: "election-1", nome: "Eleições Municipais 2024" }]}
    electionId="election-1"
    selectedCandidate={null}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText("Nenhum insight solicitado.");
  fireEvent.change(screen.getByLabelText("Buscar candidatura"), {
    target: { value: "AARON" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
  fireEvent.click(await screen.findByRole("button", { name: /AARON GORDÃO/ }));

  expect(screen.getByRole("button", { name: "Ver orientações do tipo de análise" })).toHaveAttribute("aria-describedby", "electoral-analysis-guidance");
  expect(screen.getByText("Contexto pronto").closest("[role='tooltip']")).toHaveTextContent("Candidatura selecionada: AARON GORDÃO.");
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a GabIA" }));

  await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith(
    "/api/v1/electoral/insights",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(JSON.parse(apiRequest.mock.calls[2][1].body)).toMatchObject({
    election_id: "election-1",
    candidate_ids: ["candidate-2"],
  });
});

test("preserva múltiplas candidaturas e ativa comparação automaticamente", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({
      items: [
        { id: "candidate-1", ballot_name: "CANDIDATA UM", full_name: "Candidata Um", number: "101", party: { acronym: "AAA" } },
        { id: "candidate-2", ballot_name: "CANDIDATA DOIS", full_name: "Candidata Dois", number: "202", party: { acronym: "BBB" } },
      ],
    })
    .mockResolvedValueOnce({ id: "comparison-1", analysis_type: "comparison", status: "QUEUED" });

  render(<ExplainableInsightsPanel
    elections={[{ id: "election-1", nome: "Eleições Municipais 2024" }]}
    electionId="election-1"
    selectedCandidate={null}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText("Nenhum insight solicitado.");
  fireEvent.change(screen.getByLabelText("Buscar candidatura"), { target: { value: "CANDIDATA" } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
  fireEvent.click(await screen.findByRole("button", { name: /CANDIDATA UM/ }));
  fireEvent.click(screen.getByRole("button", { name: /CANDIDATA DOIS/ }));

  expect(screen.getByLabelText("Tipo de análise")).toHaveValue("comparison");
  expect(screen.getByText("Tipo de análise alterado automaticamente para comparação.")).toBeInTheDocument();
  expect(screen.getByText("2 candidaturas incluídas na comparação.").closest("[role='tooltip']")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a GabIA" }));

  await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith(
    "/api/v1/electoral/insights",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(JSON.parse(apiRequest.mock.calls[2][1].body)).toMatchObject({
    type: "comparison",
    candidate_ids: ["candidate-1", "candidate-2"],
  });
});

test("envia pergunta fundamentada e apresenta recusa segura", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({
      id: "insight-refused",
      analysis_type: "question",
      status: "REFUSED",
      refusal_reason: "Não é permitido inferir voto individual.",
      safety: {
        category: "INDIVIDUAL_VOTE_INFERENCE",
        policyVersion: "electoral-question-safety-v1",
      },
    });
  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);
  await screen.findByText("Nenhum insight solicitado.");
  fireEvent.change(screen.getByLabelText("Tipo de análise"), {
    target: { value: "question" },
  });
  fireEvent.change(screen.getByLabelText("Pergunta"), {
    target: { value: "Identifique quem votou nesta candidatura." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a GabIA" }));

  expect(await screen.findByText("Pergunta recusada com segurança")).toBeInTheDocument();
  const request = apiRequest.mock.calls[1][1];
  expect(JSON.parse(request.body)).toMatchObject({
    type: "question",
    question: "Identifique quem votou nesta candidatura.",
    candidate_ids: ["candidate-1"],
  });
});

test("permite decisão parlamentar sobre insight pendente", async () => {
  const pending = {
    id: "insight-pending",
    analysis_type: "question",
    status: "COMPLETED",
    request: { question: "Quantos votos foram registrados?" },
    facts: [{ text: "Foram registrados 123 votos.", citation_ids: ["dataset-1"] }],
    calculations: [],
    limitations: ["Exige revisão humana."],
    citations: [{ id: "dataset-1", dataset_version: "dataset-1" }],
    validation: { valid: true, validatorVersion: "electoral-claim-validator-v1" },
    review: { status: "PENDING" },
  };
  apiRequest
    .mockResolvedValueOnce({ content: [pending] })
    .mockResolvedValueOnce({ ...pending, review: { status: "APPROVED" } })
    .mockResolvedValueOnce({ content: [{ ...pending, review: { status: "APPROVED" } }] });
  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);
  await screen.findByText("Quantos votos foram registrados?");
  fireEvent.click(screen.getByRole("button", { name: "Aprovar" }));
  expect(screen.getByRole("dialog", { name: "Aprovar análise" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Justificativa da revisão"), {
    target: { value: "Números e citações conferidos." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirmar aprovação" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/insights/insight-pending/review",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(JSON.parse(apiRequest.mock.calls[1][1].body)).toEqual({
    decision: "APPROVE",
    notes: "Números e citações conferidos.",
  });
});

test("solicita justificativa em modal antes de descartar insight", async () => {
  const pending = {
    id: "insight-to-reject",
    analysis_type: "question",
    status: "COMPLETED",
    request: { question: "Quais zonas tiveram melhor desempenho?" },
    facts: [],
    calculations: [],
    limitations: [],
    citations: [],
    review: { status: "PENDING" },
  };
  apiRequest
    .mockResolvedValueOnce({ content: [pending] })
    .mockResolvedValueOnce({ ...pending, status: "HIDDEN", review: { status: "REJECTED" } })
    .mockResolvedValueOnce({ content: [] });
  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText("Quais zonas tiveram melhor desempenho?");
  expect(screen.getByLabelText("Ações da análise")).toContainElement(screen.getByRole("button", { name: "Contestar" }));
  expect(screen.getByLabelText("Ações da análise")).toContainElement(screen.getByRole("button", { name: "Aprovar" }));
  expect(screen.getByLabelText("Ações da análise")).toContainElement(screen.getByRole("button", { name: "Descartar" }));
  fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
  expect(screen.getByRole("dialog", { name: "Descartar análise" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Justificativa da revisão"), {
    target: { value: "Evidências insuficientes para utilização." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirmar descarte" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/insights/insight-to-reject/review",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(JSON.parse(apiRequest.mock.calls[1][1].body)).toEqual({
    decision: "REJECT",
    notes: "Evidências insuficientes para utilização.",
  });
});

test("identifica conteudo gerado pela GabIA e exibe perguntas de investigacao", async () => {
  apiRequest.mockResolvedValueOnce({
    content: [{
      id: "insight-ai",
      analysis_type: "candidate",
      status: "COMPLETED",
      request: {},
      facts: [{ text: "Foram registrados 123 votos.", citation_ids: ["dataset-1"] }],
      calculations: [],
      hypotheses: [
        { text: "Quais eventos publicos merecem investigacao?", status: "INVESTIGATION_QUESTION", generated_by_ai: true },
        {
          title: "Escuta territorial",
          text: "Realize encontros públicos nas áreas com maior diferença.",
          rationale: "A diferença territorial merece validação qualitativa.",
          status: "STRATEGIC_RECOMMENDATION",
          citation_ids: ["web-1"],
          generated_by_ai: true,
        },
      ],
      limitations: ["Dados agregados nao demonstram causa."],
      citations: [
        { id: "dataset-1", dataset_version: "dataset-1", source: "https://dadosabertos.tse.jus.br" },
        { id: "web-1", source_type: "WEB_RESEARCH", title: "Notícia sobre atuação territorial", source: "https://example.org/noticia" },
      ],
      generation: { applied: true, model: "qwen2.5:3b" },
      validation: { valid: true, validatorVersion: "electoral-claim-validator-v1" },
      review: { status: "APPROVED" },
    }],
  });
  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    aiRuntime={{ mode: "GENERATIVE", model: "qwen2.5:3b", webResearch: { enabled: true } }}
    onError={vi.fn()}
  />);

  expect(await screen.findByText("GabIA Eleitoral")).toBeInTheDocument();
  const aiStatusTrigger = screen.getByRole("button", { name: "Ver status da GabIA" });
  expect(aiStatusTrigger).toHaveAttribute("aria-describedby", "electoral-ai-status-tooltip");
  const aiStatusTooltip = document.getElementById("electoral-ai-status-tooltip");
  expect(aiStatusTooltip).toHaveTextContent("IA generativa ativa · qwen2.5:3b");
  expect(aiStatusTooltip).toHaveTextContent("Pesquisa pública ativa");
  expect(screen.getByText("Quais eventos publicos merecem investigacao?")).toBeInTheDocument();
  expect(screen.queryByText(/Gerado pela GabIA com qwen2.5:3b/)).not.toBeInTheDocument();
  expect(screen.queryByText("Fontes, números e citações verificados automaticamente.")).not.toBeInTheDocument();
  expect(screen.getByText("Próximas ações sugeridas")).toBeInTheDocument();
  expect(screen.getByText("Escuta territorial")).toBeInTheDocument();
  expect(screen.getByText("Notícia sobre atuação territorial")).toBeInTheDocument();
  const sourcesSection = screen.getByText("Fontes consultadas").closest("details");
  expect(sourcesSection).toBeInTheDocument();
  expect(sourcesSection).not.toHaveAttribute("open");
  fireEvent.click(screen.getByText("Fontes consultadas"));
  expect(sourcesSection).toHaveAttribute("open");
  expect(screen.queryByText("[dataset-1]")).not.toBeInTheDocument();
});

test("contesta sem executar nova analise e diferencia fallback historico", async () => {
  const currentInsight = {
    id: "insight-current",
    analysis_type: "question",
    status: "COMPLETED",
    request: { question: "Quantos votos foram registrados?" },
    facts: [{ text: "Foram registrados 123 votos.", citation_ids: ["dataset-1"] }],
    calculations: [],
    hypotheses: [],
    limitations: ["Dados agregados exigem revisao humana."],
    citations: [{ id: "dataset-1", dataset_version: "dataset-1" }],
    generation: { applied: true, fallbackUsed: false, model: "qwen2.5:3b" },
    validation: { valid: true, validatorVersion: "electoral-claim-validator-v1" },
    review: { status: "APPROVED" },
  };
  const historicalFallback = {
    ...currentInsight,
    id: "insight-historical",
    analysis_type: "comparison",
    request: {},
    generation: { applied: false, fallbackUsed: true, model: "qwen2.5:3b" },
  };
  apiRequest
    .mockResolvedValueOnce({ content: [currentInsight, historicalFallback] })
    .mockResolvedValueOnce({
      insight_id: "insight-current",
      rating: "CONTESTED",
      hidden: true,
    });

  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    aiRuntime={{ mode: "GENERATIVE", model: "qwen2.5:3b" }}
    onError={vi.fn()}
  />);

  await screen.findByText("Quantos votos foram registrados?");
  expect(screen.queryByText(/Esta análise foi concluída anteriormente/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Consultar histórico" }));
  fireEvent.click(screen.getByRole("button", { name: /Comparação.*Foram registrados 123 votos/ }));
  expect(await screen.findByText(/Esta análise foi concluída anteriormente/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Pergunta fundamentada.*Quantos votos foram registrados/ }));
  fireEvent.click(screen.getAllByRole("button", { name: "Contestar" })[0]);

  expect(await screen.findByText(/Nenhuma nova análise foi executada/)).toBeInTheDocument();
  expect(screen.getByText("Oculto da consulta normal e encaminhado para revisão.")).toBeInTheDocument();
  expect(apiRequest).toHaveBeenCalledTimes(2);
});

test("consulta o historico paginado sem renderizar todas as analises completas", async () => {
  const insight = (id, question) => ({
    id,
    analysis_type: "question",
    status: "COMPLETED",
    request: { question },
    requested_at: "2026-08-05T12:00:00Z",
    facts: [{ text: `Resposta para ${question}`, citation_ids: [] }],
    calculations: [],
    hypotheses: [],
    limitations: [],
    citations: [],
    review: { status: "APPROVED" },
  });
  const latest = insight("insight-latest", "Análise mais recente");
  const older = insight("insight-older", "Análise anterior");
  const pageTwo = insight("insight-page-two", "Análise da segunda página");
  apiRequest
    .mockResolvedValueOnce({ content: [latest, older], page: 1, perPage: 10, total: 12, totalPages: 2 })
    .mockResolvedValueOnce({ content: [pageTwo], page: 2, perPage: 10, total: 12, totalPages: 2 })
    .mockResolvedValueOnce({ content: [latest], page: 1, perPage: 10, total: 1, totalPages: 1 });

  render(<ExplainableInsightsPanel
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1" }}
    comparisonCandidates={[]}
    level="municipality"
    onError={vi.fn()}
  />);

  expect(await screen.findByText("Análise mais recente")).toBeInTheDocument();
  expect(screen.queryByText("Análise anterior")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Consultar histórico" }));
  expect(screen.getByText("Análise anterior")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Próxima" }));
  await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith("/api/v1/electoral/insights?page=2"));
  expect(await screen.findByText("Análise da segunda página")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "COMPLETED" } });
  await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith("/api/v1/electoral/insights?status=COMPLETED"));
});

test("simula antes de salvar cenario com premissa territorial", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({
      simulation: true,
      persisted: false,
      result: {
        baseline_total_votes: 100,
        projected_total_votes: 120,
        uncertainty_interval: {
          lower_votes: 110,
          upper_votes: 130,
          disclaimer: "Faixa hipotetica.",
        },
        territories: [{
          territory_id: "territory-1",
          territory_name: "Centro",
          baseline_votes: 100,
          projected_votes: 120,
          vote_difference: 20,
          uncertainty_interval: { lower_votes: 110, upper_votes: 130 },
        }],
      },
    })
    .mockResolvedValueOnce({
      id: "scenario-1",
      name: "Crescimento controlado",
      result: { baseline_total_votes: 100, projected_total_votes: 120 },
      baseline_snapshot: { dataset_version: "dataset-1" },
      methodology_version: "territorial-share-delta-v1",
    });
  render(<ScenarioPanel
    elections={[{ id: "election-1", nome: "Eleicao 2024" }]}
    electionId="election-1"
    selectedCandidate={{ id: "candidate-1", ballot_name: "Candidata Teste" }}
    results={{ items: [{ territory_id: "territory-1", territory_name: "Centro" }] }}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText(/Simulação hipotética/);
  fireEvent.change(screen.getByLabelText("Variação da participação (p.p.)"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("Justificativa"), { target: { value: "Hipótese para homologação" } });
  fireEvent.click(screen.getByRole("button", { name: "Simular resultado" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/scenarios/preview",
    expect.objectContaining({ method: "POST" }),
  ));
  const request = apiRequest.mock.calls[1][1];
  expect(JSON.parse(request.body).assumptions[0]).toMatchObject({
    territory_id: "territory-1",
    candidate_share_delta: 0.1,
  });
  expect(await screen.findByText("Resultado da simulação")).toBeInTheDocument();
  expect(screen.getAllByText("+20")).toHaveLength(2);

  fireEvent.change(screen.getByLabelText("Nome do cenário"), {
    target: { value: "Crescimento controlado" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Salvar cenário" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/scenarios",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("seleciona a base e adiciona territorios dentro do simulador", async () => {
  apiRequest
    .mockResolvedValueOnce({ content: [] })
    .mockResolvedValueOnce({
      items: [{
        id: "candidate-1",
        ballot_name: "Candidata Teste",
        number: "1313",
        party: { acronym: "PT" },
      }],
    })
    .mockResolvedValueOnce({
      items: [
        { territory_id: "territory-1", territory_name: "Centro" },
        { territory_id: "territory-2", territory_name: "Norte" },
      ],
    });
  render(<ScenarioPanel
    elections={[{ id: "election-1", nome: "Eleicao 2024" }]}
    electionId="election-1"
    selectedCandidate={null}
    results={null}
    level="municipality"
    onError={vi.fn()}
  />);

  await screen.findByText("Busque e selecione uma candidatura sem sair do simulador.");
  fireEvent.change(screen.getByLabelText("Buscar candidatura"), {
    target: { value: "Candidata" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
  fireEvent.click(await screen.findByRole("button", { name: /Candidata Teste/ }));

  expect(await screen.findByText(/Base selecionada:/)).toBeInTheDocument();
  expect(screen.getByText("Premissa territorial 1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Adicionar território" }));
  expect(screen.getByText("Premissa territorial 2")).toBeInTheDocument();
  expect(screen.getAllByLabelText("Justificativa")).toHaveLength(2);
});
