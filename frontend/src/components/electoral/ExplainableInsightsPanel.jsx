import { BrainCircuit, Check, CircleHelp, History, MessageSquareWarning, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api";

const statusLabels = {
  QUEUED: "Na fila",
  PROCESSING: "Analisando",
  COMPLETED: "Concluído",
  FAILED: "Falhou",
  REFUSED: "Recusado",
  HIDDEN: "Em revisão",
};

const recommendationCategoryLabels = {
  AGENDA: "Agenda territorial",
  ATUACAO_PARLAMENTAR: "Atuação parlamentar",
  COMUNICACAO: "Comunicação pública",
  DADOS: "Aprofundar dados",
};

const recommendationHorizonLabels = {
  IMEDIATO: "Imediato",
  "30_DIAS": "30 dias",
  "60_DIAS": "60 dias",
  "90_DIAS": "90 dias",
};

function sourceTitle(source) {
  if (source.title) return source.title;
  if (source.source_type === "WEB_RESEARCH") return "Fonte pública consultada na internet";
  if (source.source_type === "AUTHORIZED_DOCUMENT") return "Documento autorizado do gabinete";
  if (source.source_type === "MANDATE_AGGREGATE") return "Indicadores agregados do mandato";
  return "Resultados eleitorais oficiais do TSE";
}

function safeExternalUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : null;
}

function CitationLinks({ ids = [], citations = [], insightId }) {
  const numbers = ids.map((id) => citations.findIndex((source) => source.id === id) + 1).filter(Boolean);
  if (!numbers.length) return null;
  return <small className="electoral-citation-links">
    {numbers.map((number) => <a key={number} href={`#source-${insightId}-${number}`}>Fonte {number}</a>)}
  </small>;
}

function calculationValue(calculation) {
  if (/participa/i.test(calculation.label || "") && Number(calculation.value) <= 1) {
    return new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 2 }).format(calculation.value);
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(calculation.value);
}

function analysisTypeLabel(value) {
  if (value === "candidate") return "Análise individual";
  if (value === "question") return "Pergunta fundamentada";
  return "Comparação";
}

function insightSummary(item) {
  return item.request?.question || item.facts?.[0]?.text || "Análise eleitoral fundamentada";
}

function insightDate(value) {
  if (!value) return "Data não informada";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function ExplainableInsightsPanel({
  elections = [],
  electionId,
  selectedCandidate,
  comparisonCandidates,
  level,
  aiRuntime,
  onError,
}) {
  const [items, setItems] = useState([]);
  const [activeItem, setActiveItem] = useState(null);
  const [activeTab, setActiveTab] = useState("analysis");
  const [historyPage, setHistoryPage] = useState(1);
  const [historyType, setHistoryType] = useState("");
  const [historyStatus, setHistoryStatus] = useState("");
  const [historySearch, setHistorySearch] = useState("");
  const [historySearchDraft, setHistorySearchDraft] = useState("");
  const [historyMeta, setHistoryMeta] = useState({ page: 1, perPage: 10, total: 0, totalPages: 1 });
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [analysisType, setAnalysisType] = useState("candidate");
  const [question, setQuestion] = useState("");
  const [reviewDialog, setReviewDialog] = useState(null);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [contestingId, setContestingId] = useState(null);
  const [feedbackNotice, setFeedbackNotice] = useState("");
  const [contextElectionId, setContextElectionId] = useState(electionId || elections[0]?.id || "");
  const [candidateQuery, setCandidateQuery] = useState("");
  const [candidateOptions, setCandidateOptions] = useState([]);
  const [searchingCandidates, setSearchingCandidates] = useState(false);
  const [selectionNotice, setSelectionNotice] = useState("");
  const [analysisLevel, setAnalysisLevel] = useState(level || "municipality");
  const [referenceCandidateId, setReferenceCandidateId] = useState(selectedCandidate?.id || "");
  const [contextCandidates, setContextCandidates] = useState(() => {
    const candidates = [selectedCandidate, ...comparisonCandidates].filter(Boolean);
    return candidates.filter((candidate, index) => (
      candidates.findIndex((item) => item.id === candidate.id) === index
    ));
  });

  const load = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const params = new URLSearchParams();
      if (historyPage > 1) params.set("page", String(historyPage));
      if (historyType) params.set("type", historyType);
      if (historyStatus) params.set("status", historyStatus);
      if (historySearch) params.set("q", historySearch);
      const response = await apiRequest(`/api/v1/electoral/insights${params.size ? `?${params}` : ""}`);
      const content = response.content || [];
      setItems(content);
      setHistoryMeta({
        page: response.page || historyPage,
        perPage: response.perPage || 10,
        total: response.total ?? content.length,
        totalPages: response.totalPages || 1,
      });
      setActiveItem((current) => {
        if (!current) return content[0] || null;
        return content.find((item) => item.id === current.id) || current;
      });
    } catch (error) {
      onError(error.message);
    } finally {
      setLoadingHistory(false);
    }
  }, [historyPage, historySearch, historyStatus, historyType, onError]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!contextCandidates.some((candidate) => candidate.id === referenceCandidateId)) {
      setReferenceCandidateId(contextCandidates[0]?.id || "");
    }
  }, [contextCandidates, referenceCandidateId]);
  useEffect(() => {
    if (!items.some((item) => ["QUEUED", "PROCESSING"].includes(item.status))) {
      return undefined;
    }
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [items, load]);
  useEffect(() => {
    if (!reviewDialog) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape" && !reviewing) {
        setReviewDialog(null);
        setReviewNote("");
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [reviewDialog, reviewing]);

  const candidateIds = analysisType === "candidate"
    ? contextCandidates[0] ? [contextCandidates[0].id] : []
    : contextCandidates.map((candidate) => candidate.id);
  const validSelection = analysisType === "candidate"
    ? candidateIds.length === 1
    : analysisType === "comparison"
      ? candidateIds.length >= 2
      : candidateIds.length >= 1 && question.trim().length >= 10;

  async function requestInsight(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const created = await apiRequest("/api/v1/electoral/insights", {
        method: "POST",
        body: JSON.stringify({
          type: analysisType,
          question: analysisType === "question" ? question : undefined,
          election_id: contextElectionId,
          candidate_ids: candidateIds,
          level: analysisLevel,
          reference_candidate_id: analysisType === "question" ? referenceCandidateId : undefined,
        }),
      });
      setActiveItem(created);
      setItems((current) => [created, ...current]);
      setHistoryMeta((current) => ({ ...current, total: current.total + 1 }));
      if (analysisType === "question" && created.status !== "REFUSED") setQuestion("");
    } catch (error) {
      onError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function searchCandidates(event) {
    event.preventDefault();
    if (!contextElectionId || candidateQuery.trim().length < 2) return;
    setSearchingCandidates(true);
    try {
      const params = new URLSearchParams({
        election_id: contextElectionId,
        q: candidateQuery.trim(),
      });
      const response = await apiRequest(`/api/v1/electoral/candidates?${params}`);
      setCandidateOptions(response.items || []);
    } catch (error) {
      onError(error.message);
    } finally {
      setSearchingCandidates(false);
    }
  }

  function chooseCandidate(candidate) {
    if (contextCandidates.some((item) => item.id === candidate.id)) {
      setContextCandidates((current) => current.filter((item) => item.id !== candidate.id));
      setSelectionNotice("");
      return;
    }
    if (contextCandidates.length >= 5) return;
    const nextCandidates = [...contextCandidates, candidate];
    setContextCandidates(nextCandidates);
    if (analysisType === "candidate" && nextCandidates.length > 1) {
      setAnalysisType("comparison");
      setSelectionNotice("Tipo de análise alterado automaticamente para comparação.");
    } else {
      setSelectionNotice("");
    }
  }

  function changeAnalysisType(value) {
    setAnalysisType(value);
    if (value === "question" && contextCandidates.length > 1) {
      setAnalysisLevel("electoral_zone");
    }
    if (value === "candidate") {
      if (contextCandidates.length > 1) {
        setSelectionNotice("Para a análise individual, mantivemos apenas a primeira candidatura selecionada.");
      } else {
        setSelectionNotice("");
      }
      setContextCandidates((current) => current.slice(0, 1));
    } else {
      setSelectionNotice("");
    }
  }

  function changeContextElection(value) {
    setContextElectionId(value);
    setContextCandidates([]);
    setCandidateOptions([]);
    setCandidateQuery("");
    setSelectionNotice("");
    setReferenceCandidateId("");
  }

  async function contest(item) {
    setContestingId(item.id);
    setFeedbackNotice("");
    try {
      await apiRequest(`/api/v1/electoral/insights/${item.id}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          rating: "CONTESTED",
          reason: "human_review_requested",
          comment: "Conteúdo marcado para revisão pelo parlamentar.",
        }),
      });
      setItems((current) => current.map((currentItem) => (
        currentItem.id === item.id
          ? {
            ...currentItem,
            status: "HIDDEN",
            review: { ...currentItem.review, status: "PENDING" },
          }
          : currentItem
      )));
      setActiveItem((current) => current?.id === item.id
        ? { ...current, status: "HIDDEN", review: { ...current.review, status: "PENDING" } }
        : current);
      setFeedbackNotice(
        "Contestação registrada e encaminhada para revisão. Nenhuma nova análise foi executada.",
      );
    } catch (error) {
      onError(error.message);
    } finally {
      setContestingId(null);
    }
  }

  function openReviewDialog(item, decision) {
    setReviewDialog({
      item,
      decision: decision === "APPROVE" && item.status === "HIDDEN" ? "RESTORE" : decision,
    });
    setReviewNote("");
  }

  function closeReviewDialog() {
    if (reviewing) return;
    setReviewDialog(null);
    setReviewNote("");
  }

  async function confirmReview(event) {
    event.preventDefault();
    if (!reviewDialog || reviewNote.trim().length < 5) return;
    setReviewing(true);
    try {
      await apiRequest(`/api/v1/electoral/insights/${reviewDialog.item.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          decision: reviewDialog.decision,
          notes: reviewNote.trim(),
        }),
      });
      await load();
      setActiveItem((current) => current?.id === reviewDialog.item.id
        ? { ...current, review: { ...current.review, status: reviewDialog.decision === "REJECT" ? "REJECTED" : "APPROVED" } }
        : current);
      setReviewDialog(null);
      setReviewNote("");
    } catch (error) {
      onError(error.message);
    } finally {
      setReviewing(false);
    }
  }

  const selectionGuidance = !contextElectionId
    ? "Selecione uma eleição para habilitar a análise."
    : analysisType === "candidate"
      ? contextCandidates[0]
        ? `Candidatura selecionada: ${contextCandidates[0].ballot_name || contextCandidates[0].name || "contexto atual"}.`
        : "Pesquise e selecione uma candidatura."
      : analysisType === "comparison"
        ? contextCandidates.length >= 2
          ? `${contextCandidates.length} candidaturas incluídas na comparação.`
          : "Inclua pelo menos duas candidaturas na comparação."
        : candidateIds.length === 0
          ? "Selecione uma candidatura ou monte uma comparação antes de formular a pergunta."
          : question.trim().length < 10
            ? "Escreva uma pergunta com pelo menos 10 caracteres."
            : `Pergunta pronta para análise com ${candidateIds.length} candidatura(s) no contexto.`;

  return <section className="electoral-analysis-card electoral-insights-workspace" aria-labelledby="insights-title">
    <header className="electoral-results-header electoral-insights-header">
      <div><p className="eyebrow">Análise assistida e auditável</p><h2 id="insights-title">GabIA Eleitoral</h2></div>
      <div className="electoral-ai-status">
        <button type="button" className="electoral-ai-status-trigger" aria-label="Ver status da GabIA" aria-describedby="electoral-ai-status-tooltip">
          <BrainCircuit size={28} aria-hidden="true" />
        </button>
        <div id="electoral-ai-status-tooltip" className="electoral-ai-status-tooltip" role="tooltip">
          <strong>Status da GabIA</strong>
          <span className={aiRuntime?.mode === "GENERATIVE" ? "active" : "inactive"}>
            {aiRuntime?.mode === "GENERATIVE"
              ? `IA generativa ativa · ${aiRuntime.model}`
              : "Camada generativa inativa · análise determinística"}
          </span>
          <span className={aiRuntime?.webResearch?.enabled ? "active" : "inactive"}>
            {aiRuntime?.webResearch?.enabled
              ? "Pesquisa pública ativa · fontes externas serão citadas na resposta"
              : "Pesquisa pública inativa"}
          </span>
        </div>
      </div>
    </header>
    <p className="electoral-insight-intro">
      A GabIA combina resultados oficiais, documentos autorizados e fontes públicas da internet.
      Fatos permanecem verificáveis; leituras estratégicas são hipóteses, nunca causas presumidas.
    </p>
    <div className="electoral-insight-tabs" role="tablist" aria-label="Áreas da GabIA Eleitoral">
      <button
        type="button"
        role="tab"
        id="electoral-insight-analysis-tab"
        aria-selected={activeTab === "analysis"}
        aria-controls="electoral-insight-analysis-panel"
        className={activeTab === "analysis" ? "active" : ""}
        onClick={() => setActiveTab("analysis")}
      >
        <BrainCircuit size={17} aria-hidden="true" /> Análise
      </button>
      <button
        type="button"
        role="tab"
        id="electoral-insight-history-tab"
        aria-selected={activeTab === "history"}
        aria-controls="electoral-insight-history-panel"
        className={activeTab === "history" ? "active" : ""}
        onClick={() => setActiveTab("history")}
      >
        <History size={17} aria-hidden="true" /> Histórico
        {historyMeta.total > 0 && <small>{historyMeta.total}</small>}
      </button>
    </div>
    {activeTab === "analysis" && <div
      id="electoral-insight-analysis-panel"
      className="electoral-insight-tab-panel"
      role="tabpanel"
      aria-labelledby="electoral-insight-analysis-tab"
    >
    <section className="electoral-insight-context" aria-labelledby="electoral-insight-context-title">
      <header>
        <div>
          <p className="eyebrow">Contexto da consulta</p>
          <h3 id="electoral-insight-context-title">Escolha quem será analisado</h3>
        </div>
        <small>{analysisType === "candidate" ? "1 candidatura" : analysisType === "comparison" ? "2 a 5 candidaturas" : "Até 5 candidaturas"}</small>
      </header>
      <div className="electoral-insight-context-controls">
        <div className="electoral-insight-type-control">
          <div className="electoral-field-heading">
            <label htmlFor="electoral-analysis-type">Tipo de análise</label>
            <span className="electoral-field-help">
              <button type="button" aria-label="Ver orientações do tipo de análise" aria-describedby="electoral-analysis-guidance">
                <CircleHelp size={15} aria-hidden="true" />
              </button>
              <span id="electoral-analysis-guidance" className={`electoral-field-tooltip ${validSelection && contextElectionId ? "ready" : "pending"}`} role="tooltip">
                <strong>{validSelection && contextElectionId ? "Contexto pronto" : "Antes de analisar"}</strong>
                <span>{selectionGuidance}</span>
              </span>
            </span>
          </div>
          <span className="electoral-select-control">
            <select id="electoral-analysis-type" aria-label="Tipo de análise" aria-describedby="electoral-analysis-guidance" value={analysisType} onChange={(event) => changeAnalysisType(event.target.value)}>
              <option value="candidate">Análise individual</option>
              <option value="comparison">Comparação entre candidaturas</option>
              <option value="question">Pergunta fundamentada</option>
            </select>
          </span>
        </div>
        <label htmlFor="electoral-insight-election">
          <span>Eleição</span>
          <span className="electoral-select-control">
            <select id="electoral-insight-election" value={contextElectionId} onChange={(event) => changeContextElection(event.target.value)}>
              <option value="">Selecione uma eleição</option>
              {elections.map((item) => <option key={item.id} value={item.id}>{item.nome || item.name || item.year}</option>)}
            </select>
          </span>
        </label>
        <label htmlFor="electoral-insight-level">
          <span>Recorte territorial</span>
          <span className="electoral-select-control">
            <select id="electoral-insight-level" value={analysisLevel} onChange={(event) => setAnalysisLevel(event.target.value)}>
              <option value="municipality">Município</option>
              <option value="electoral_zone">Zona eleitoral</option>
              <option value="neighborhood">Bairro</option>
              <option value="polling_place">Local de votação</option>
            </select>
          </span>
        </label>
        <form className="electoral-insight-candidate-search" onSubmit={searchCandidates}>
          <label htmlFor="electoral-insight-candidate-query">
            <span>Buscar candidatura</span>
            <input
              id="electoral-insight-candidate-query"
              value={candidateQuery}
              minLength={2}
              onChange={(event) => setCandidateQuery(event.target.value)}
              placeholder="Digite nome ou número"
            />
          </label>
          <button type="submit" className="secondary-button" disabled={!contextElectionId || candidateQuery.trim().length < 2 || searchingCandidates}>
            <Search size={17} aria-hidden="true" />
            {searchingCandidates ? "Buscando..." : "Buscar"}
          </button>
        </form>
      </div>
      {candidateOptions.length > 0 && <div className="electoral-insight-candidate-options" aria-label="Candidaturas encontradas">
        {candidateOptions.map((candidate) => {
          const selected = contextCandidates.some((item) => item.id === candidate.id);
          return <button
            type="button"
            key={candidate.id}
            className={selected ? "selected" : ""}
            aria-pressed={selected}
            onClick={() => chooseCandidate(candidate)}
          >
            <span><strong>{candidate.ballot_name}</strong><small>{candidate.full_name}</small></span>
            <span>{candidate.number} · {candidate.party?.acronym}</span>
            <b>{selected ? "Selecionada" : "Selecionar"}</b>
          </button>;
        })}
      </div>}
      {candidateOptions.length === 0 && candidateQuery.trim().length >= 2 && !searchingCandidates && <p className="electoral-insight-search-hint">Use “Buscar” para localizar candidaturas nesta eleição.</p>}
      {selectionNotice && <p className="electoral-insight-selection-notice" role="status">{selectionNotice}</p>}
      {contextCandidates.length > 0 && <div className="electoral-insight-selected" aria-label="Candidaturas selecionadas">
        <strong>Selecionadas</strong>
        <div>{contextCandidates.map((candidate) => <span key={candidate.id}>
          {candidate.ballot_name || candidate.full_name || candidate.name}
          <button type="button" aria-label={`Remover ${candidate.ballot_name || candidate.full_name || candidate.name}`} onClick={() => setContextCandidates((current) => current.filter((item) => item.id !== candidate.id))}><X size={14} /></button>
        </span>)}</div>
        {analysisType === "question" && contextCandidates.length > 1 && <label className="electoral-reference-candidate" htmlFor="electoral-reference-candidate">
          <span>Quem representa “eu” na pergunta?</span>
          <span className="electoral-select-control">
            <select id="electoral-reference-candidate" value={referenceCandidateId} onChange={(event) => setReferenceCandidateId(event.target.value)}>
              {contextCandidates.map((candidate) => <option key={candidate.id} value={candidate.id}>
                {candidate.ballot_name || candidate.full_name || candidate.name}
              </option>)}
            </select>
          </span>
        </label>}
      </div>}
      <form className="electoral-insight-form" onSubmit={requestInsight}>
        <div className="electoral-insight-fields">
          {analysisType === "question" && <label htmlFor="electoral-insight-question">
            <span>Pergunta</span>
            <small id="electoral-question-help">Peça comparações, contexto público e sugestões. A GabIA separará fatos, hipóteses e ações recomendadas.</small>
            <textarea
              id="electoral-insight-question"
              aria-label="Pergunta"
              value={question}
              minLength={10}
              maxLength={1000}
              rows={4}
              required
              aria-describedby="electoral-question-help electoral-question-count"
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ex.: Em quais zonas a outra candidatura teve vantagem, quais hipóteses ajudam a explicar o resultado e que ações devo priorizar?"
            />
            <small id="electoral-question-count" className="electoral-character-count">{question.length}/1000 caracteres</small>
          </label>}
        </div>
        <div className="electoral-insight-form-actions">
          <small>A resposta será registrada com fontes, cálculos e trilha de revisão.</small>
          <button type="submit" className="primary-button" disabled={submitting || !validSelection || !contextElectionId}>
            <BrainCircuit size={18} aria-hidden="true" />
            {submitting ? "Enfileirando..." : "Analisar com a GabIA"}
          </button>
        </div>
      </form>
    </section>
    {feedbackNotice && <p className="electoral-selection-guidance ready" role="status">
      <strong>Contestação registrada</strong>
      <span>{feedbackNotice}</span>
    </p>}
    </div>}
    {activeTab === "history" && <section
      id="electoral-insight-history-panel"
      className="electoral-insight-history electoral-insight-tab-panel"
      role="tabpanel"
      aria-labelledby="electoral-insight-history-tab"
    >
      <header>
        <div>
          <p className="eyebrow">Consultas anteriores</p>
          <h3 id="electoral-insight-history-title">Histórico de análises</h3>
          <small>{historyMeta.total} análise(s) registrada(s)</small>
        </div>
        <History size={22} aria-hidden="true" />
      </header>
      <div id="electoral-insight-history-content" className="electoral-insight-history-content">
        <form className="electoral-insight-history-filters" onSubmit={(event) => {
          event.preventDefault();
          setHistoryPage(1);
          setHistorySearch(historySearchDraft.trim());
        }}>
          <label>Buscar no histórico
            <input value={historySearchDraft} maxLength={100} onChange={(event) => setHistorySearchDraft(event.target.value)} placeholder="Pergunta, candidatura ou conteúdo" />
          </label>
          <label>Tipo
            <select value={historyType} onChange={(event) => { setHistoryPage(1); setHistoryType(event.target.value); }}>
              <option value="">Todos os tipos</option>
              <option value="candidate">Análise individual</option>
              <option value="comparison">Comparação</option>
              <option value="question">Pergunta fundamentada</option>
            </select>
          </label>
          <label>Status
            <select value={historyStatus} onChange={(event) => { setHistoryPage(1); setHistoryStatus(event.target.value); }}>
              <option value="">Todos os status</option>
              <option value="COMPLETED">Concluídas</option>
              <option value="PROCESSING">Em análise</option>
              <option value="QUEUED">Na fila</option>
              <option value="REFUSED">Recusadas</option>
              <option value="FAILED">Com falha</option>
              <option value="HIDDEN">Em revisão</option>
            </select>
          </label>
          <button type="submit" className="secondary-button"><Search size={16} aria-hidden="true" /> Buscar</button>
        </form>
        {loadingHistory && <p className="electoral-insight-history-loading" role="status">Atualizando histórico...</p>}
        {!loadingHistory && items.length === 0 && <p className="electoral-empty">Nenhuma análise encontrada com estes filtros.</p>}
        {!loadingHistory && items.length > 0 && <ul className="electoral-insight-history-list">
          {items.map((item) => <li key={`history-${item.id}`}>
            <button type="button" className={activeItem?.id === item.id ? "selected" : ""} aria-pressed={activeItem?.id === item.id} onClick={() => { setActiveItem(item); setActiveTab("analysis"); }}>
              <span>
                <strong>{analysisTypeLabel(item.analysis_type)}</strong>
                <small>{insightSummary(item)}</small>
              </span>
              <span className="electoral-insight-history-meta">
                <small>{insightDate(item.requested_at)}</small>
                <b className={`electoral-job-status status-${item.status.toLowerCase()}`}>{statusLabels[item.status] || item.status}</b>
              </span>
            </button>
          </li>)}
        </ul>}
        {historyMeta.totalPages > 1 && <footer className="electoral-pagination" aria-label="Paginação do histórico de análises">
          <button type="button" className="secondary-button" disabled={historyPage <= 1 || loadingHistory} onClick={() => setHistoryPage((page) => page - 1)}>Anterior</button>
          <span>Página {historyMeta.page} de {historyMeta.totalPages}</span>
          <button type="button" className="secondary-button" disabled={historyPage >= historyMeta.totalPages || loadingHistory} onClick={() => setHistoryPage((page) => page + 1)}>Próxima</button>
        </footer>}
      </div>
    </section>}
    {activeTab === "analysis" && <div className="electoral-insight-list">
      {!activeItem && <p className="electoral-empty">Nenhum insight solicitado.</p>}
      {(activeItem ? [activeItem] : []).map((item) => <article key={item.id} className="electoral-insight-card">
        <header>
          <strong>{analysisTypeLabel(item.analysis_type)}</strong>
          <span className={`electoral-job-status status-${item.generation?.fallbackUsed ? "failed" : item.status.toLowerCase()}`}>
            {item.generation?.fallbackUsed ? "IA indisponível" : statusLabels[item.status] || item.status}
          </span>
        </header>
        {item.status === "COMPLETED" && <>
          {item.request?.question && <p className="electoral-insight-question">{item.request.question}</p>}
          {item.hypotheses?.some((hypothesis) => hypothesis.status === "EXECUTIVE_SUMMARY") && <section className="electoral-executive-summary">
            <span>Resposta estratégica</span>
            {item.hypotheses.filter((hypothesis) => hypothesis.status === "EXECUTIVE_SUMMARY").map((summary, index) => <p key={`${item.id}-summary-${index}`}>
              {summary.text}
              <CitationLinks ids={summary.citation_ids} citations={item.citations} insightId={item.id} />
            </p>)}
          </section>}
          <h3>O que os dados mostram</h3>
          <ul>{item.facts.map((fact, index) => <li key={`${item.id}-fact-${index}`}>
            {fact.text}
            <CitationLinks ids={fact.citation_ids} citations={item.citations} insightId={item.id} />
          </li>)}</ul>
          {item.calculations?.length > 0 && <><h3>Indicadores principais</h3>
            <ul>{item.calculations.slice(0, 6).map((calculation, index) => <li key={`${item.id}-calc-${index}`}>
              {calculation.label}: <strong>{calculationValue(calculation)}</strong>
              <details className="electoral-calculation-detail"><summary>Como foi calculado</summary>{calculation.formula}</details>
            </li>)}</ul>
          </>}
          {item.hypotheses?.some((hypothesis) => hypothesis.status === "CONTEXTUAL_HYPOTHESIS") && <><h3>Leituras estratégicas</h3>
            <p className="electoral-section-help">Hipóteses sustentadas pelo contexto disponível; não representam causa comprovada.</p>
            <ul>{item.hypotheses.filter((hypothesis) => hypothesis.status === "CONTEXTUAL_HYPOTHESIS").map((hypothesis, index) => <li key={`${item.id}-interpretation-${index}`}>
              {hypothesis.text}
              <CitationLinks ids={hypothesis.citation_ids} citations={item.citations} insightId={item.id} />
            </li>)}</ul>
          </>}
          {item.hypotheses?.some((hypothesis) => hypothesis.status === "STRATEGIC_RECOMMENDATION") && <><h3>Próximas ações sugeridas</h3>
            <div className="electoral-recommendation-grid">{item.hypotheses.filter((hypothesis) => hypothesis.status === "STRATEGIC_RECOMMENDATION").map((recommendation, index) => <article key={`${item.id}-recommendation-${index}`}>
              <div className="electoral-recommendation-meta">
                <span>{recommendationCategoryLabels[recommendation.category] || "Ação estratégica"}</span>
                <span>Prioridade {String(recommendation.priority || "média").toLocaleLowerCase("pt-BR")}</span>
                <span>{recommendationHorizonLabels[recommendation.time_horizon] || recommendation.time_horizon || "30 dias"}</span>
              </div>
              <strong>{recommendation.title}</strong>
              {recommendation.territory && <small className="electoral-recommendation-territory">Território: {recommendation.territory}</small>}
              <p>{recommendation.text}</p>
              <small>{recommendation.rationale}</small>
              <CitationLinks ids={recommendation.citation_ids} citations={item.citations} insightId={item.id} />
            </article>)}</div>
          </>}
          {item.hypotheses?.some((hypothesis) => !["EXECUTIVE_SUMMARY", "CONTEXTUAL_HYPOTHESIS", "STRATEGIC_RECOMMENDATION"].includes(hypothesis.status)) && <><h3>Pontos para aprofundar</h3>
            <ul>{item.hypotheses.filter((hypothesis) => !["EXECUTIVE_SUMMARY", "CONTEXTUAL_HYPOTHESIS", "STRATEGIC_RECOMMENDATION"].includes(hypothesis.status)).map((hypothesis, index) => <li key={`${item.id}-hypothesis-${index}`}>{hypothesis.text}</li>)}</ul>
          </>}
          <details className="electoral-limitations"><summary>Limites e cuidados desta análise</summary>
            <ul>{item.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
          </details>
          {item.generation?.fallbackUsed && <p className="electoral-refusal">
            A GabIA não gerou uma resposta para esta solicitação. Os números abaixo são apenas
            a camada determinística e não devem ser interpretados como recomendação estratégica.
          </p>}
          {item.citations?.length > 0 && <details className="electoral-source-list">
            <summary>Fontes consultadas</summary>
            <ol>{item.citations.map((source, index) => {
              const url = safeExternalUrl(source.source);
              return <li key={source.id} id={`source-${item.id}-${index + 1}`}>
                <span>Fonte {index + 1}</span>
                {url
                  ? <a href={url} target="_blank" rel="noreferrer">{sourceTitle(source)}</a>
                  : <strong>{sourceTitle(source)}</strong>}
                <small>{source.source_type === "WEB_RESEARCH" ? "Contexto público pesquisado na internet" : "Dado utilizado na análise e preservado para auditoria"}</small>
              </li>;
            })}</ol>
          </details>}
          <footer>
            <span>Análise fundamentada · revise antes de usar em uma decisão</span>
          </footer>
        </>}
        {item.status === "REFUSED" && <div className="electoral-refusal">
          <strong>Pergunta recusada com segurança</strong>
          <p>{item.refusal_reason}</p>
          <small>{item.safety?.category} · {item.safety?.policyVersion}</small>
        </div>}
        {item.status === "HIDDEN" && <p>Oculto da consulta normal e encaminhado para revisão.</p>}
        {(item.status === "COMPLETED" || (item.status === "HIDDEN" && item.review?.status === "PENDING")) && <div className="electoral-review-actions" aria-label="Ações da análise">
          {item.status === "COMPLETED" && <button type="button" className="secondary-button electoral-review-action" disabled={contestingId === item.id} onClick={() => contest(item)}>
            <MessageSquareWarning size={16} aria-hidden="true" /> {contestingId === item.id ? "Registrando..." : "Contestar"}
          </button>}
          {item.review?.status === "PENDING" && <>
            <button type="button" className="secondary-button electoral-review-action" onClick={() => openReviewDialog(item, "APPROVE")}>
              <Check size={16} aria-hidden="true" /> Aprovar
            </button>
            <button type="button" className="secondary-button electoral-review-action danger" onClick={() => openReviewDialog(item, "REJECT")}>
              <Trash2 size={16} aria-hidden="true" /> Descartar
            </button>
          </>}
        </div>}
      </article>)}
    </div>}
    {reviewDialog && <div className="modal-backdrop" role="presentation" onMouseDown={closeReviewDialog}>
      <section className="modal electoral-review-modal" role="dialog" aria-modal="true" aria-labelledby="electoral-review-modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">Revisão parlamentar</p>
            <h2 id="electoral-review-modal-title">{reviewDialog.decision === "REJECT" ? "Descartar análise" : "Aprovar análise"}</h2>
          </div>
          <button type="button" className="icon-button" onClick={closeReviewDialog} aria-label="Fechar" disabled={reviewing}><X size={20} /></button>
        </header>
        <form className="electoral-review-form" onSubmit={confirmReview}>
          <p>
            {reviewDialog.decision === "REJECT"
              ? "Informe o motivo do descarte para manter a decisão registrada na trilha de auditoria."
              : "Registre o que foi conferido antes de aprovar esta análise."}
          </p>
          <label htmlFor="electoral-review-note">Justificativa da revisão
            <textarea
              id="electoral-review-note"
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
              placeholder="Registre a conferência ou motivo do descarte"
              minLength={5}
              maxLength={1000}
              rows={4}
              required
              autoFocus
            />
          </label>
          <small className="electoral-review-character-count">{reviewNote.length}/1000 caracteres · mínimo de 5</small>
          <footer>
            <button type="button" className="secondary-button" onClick={closeReviewDialog} disabled={reviewing}>Cancelar</button>
            <button type="submit" className={reviewDialog.decision === "REJECT" ? "danger-button" : "primary-button"} disabled={reviewing || reviewNote.trim().length < 5}>
              {reviewing ? "Confirmando..." : reviewDialog.decision === "REJECT" ? "Confirmar descarte" : "Confirmar aprovação"}
            </button>
          </footer>
        </form>
      </section>
    </div>}
  </section>;
}
