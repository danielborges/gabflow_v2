import { Database, Landmark, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";
import { CandidateComparison } from "./CandidateComparison";
import { CandidateHistory } from "./CandidateHistory";
import { CandidateMap } from "./CandidateMap";
import { CandidateResults } from "./CandidateResults";
import { CandidateSearch } from "./CandidateSearch";
import { DelegationPanel } from "./DelegationPanel";
import { MandateIntelligencePanel } from "./MandateIntelligencePanel";
import { PublicCommitmentsPanel } from "./PublicCommitmentsPanel";
import { ReportJobs } from "./ReportJobs";
import { electoralSectionDefinitions } from "./electoralNavigation";

export function ElectoralIntelligencePage({
  activeSection = "overview",
  onSectionChange,
  onSectionsChange,
}) {
  const [initialParams] = useState(() => new URLSearchParams(window.location.search));
  const [data, setData] = useState(null);
  const [filters, setFilters] = useState({
    electionId: initialParams.get("eleicao") || "",
    q: initialParams.get("busca") || "",
    party: initialParams.get("partido") || "",
    office: initialParams.get("cargo") || "",
  });
  const [candidates, setCandidates] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [results, setResults] = useState(null);
  const [history, setHistory] = useState(null);
  const [comparisonCandidates, setComparisonCandidates] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [mapResponse, setMapResponse] = useState(null);
  const [mapMetric, setMapMetric] = useState("votes");
  const [selectedTerritoryCode, setSelectedTerritoryCode] = useState("");
  const [favorites, setFavorites] = useState([]);
  const [savedComparisons, setSavedComparisons] = useState([]);
  const [level, setLevel] = useState(initialParams.get("nivel") || "municipality");
  const [sort, setSort] = useState("votes");
  const [order, setOrder] = useState("desc");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [error, setError] = useState("");
  const [analysisView, setAnalysisView] = useState(
    initialParams.get("detalhe") || "results",
  );

  useEffect(() => {
    Promise.all([
      apiRequest("/api/v1/electoral/disponibilidade"),
      apiRequest("/api/v1/electoral/elections"),
      apiRequest("/api/v1/electoral/coverage"),
      apiRequest("/api/v1/electoral/quality"),
      apiRequest("/api/v1/electoral/favorites"),
      apiRequest("/api/v1/electoral/saved-comparisons"),
    ])
      .then(([availability, elections, coverage, quality, favoriteResponse, savedResponse]) => {
        setData({ availability, elections, coverage, quality });
        setFavorites(favoriteResponse.content || []);
        setSavedComparisons(savedResponse.content || []);
        setFilters((current) => ({
          ...current,
          electionId: current.electionId || elections.items?.[0]?.id || "",
        }));
      })
      .catch((requestError) => setError(requestError.message));
  }, []);

  useEffect(() => {
    function restoreNavigation() {
      const params = new URLSearchParams(window.location.search);
      onSectionChange?.(params.get("secao") || "overview");
      setAnalysisView(params.get("detalhe") || "results");
    }
    window.addEventListener("popstate", restoreNavigation);
    return () => window.removeEventListener("popstate", restoreNavigation);
  }, [onSectionChange]);

  function persistUrl(nextFilters, nextCandidate = selectedCandidate, nextLevel = level) {
    const params = new URLSearchParams(window.location.search);
    const values = {
      eleicao: nextFilters.electionId,
      busca: nextFilters.q,
      partido: nextFilters.party,
      cargo: nextFilters.office,
      candidato: nextCandidate?.id,
      nivel: nextLevel,
    };
    Object.entries(values).forEach(([key, value]) => (
      value ? params.set(key, value) : params.delete(key)
    ));
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
  }

  function navigateSection(sectionId) {
    onSectionChange?.(sectionId);
    setError("");
    const params = new URLSearchParams(window.location.search);
    params.set("secao", sectionId);
    window.history.pushState({}, "", `${window.location.pathname}?${params}`);
  }

  function navigateAnalysis(view) {
    setAnalysisView(view);
    const params = new URLSearchParams(window.location.search);
    params.set("detalhe", view);
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
  }

  async function submitSearch(event) {
    event?.preventDefault();
    return runSearch(1);
  }

  async function runSearch(page) {
    setError("");
    setLoadingSearch(true);
    setSelectedCandidate(null);
    setResults(null);
    setHistory(null);
    setMapResponse(null);
    persistUrl(filters, null, level);
    try {
      const params = new URLSearchParams({ election_id: filters.electionId, q: filters.q });
      params.set("page", String(page));
      if (filters.party) params.set("party", filters.party);
      if (filters.office) params.set("office", filters.office);
      setCandidates(await apiRequest(`/api/v1/electoral/candidates?${params}`));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingSearch(false);
    }
  }

  async function loadResults(
    candidate,
    nextLevel = level,
    nextSort = sort,
    nextOrder = order,
    page = 1,
  ) {
    setSelectedCandidate(candidate);
    setLevel(nextLevel);
    setAnalysisView("results");
    setLoadingResults(true);
    setError("");
    persistUrl(filters, candidate, nextLevel);
    try {
      const params = new URLSearchParams({
        election_id: filters.electionId,
        level: nextLevel,
        sort: nextSort,
        order: nextOrder,
        page: String(page),
      });
      const [resultResponse, historyResponse, mapData] = await Promise.all([
        apiRequest(`/api/v1/electoral/candidates/${candidate.id}/results?${params}`),
        apiRequest(`/api/v1/electoral/candidates/${candidate.id}/history`),
        apiRequest(`/api/v1/electoral/candidates/${candidate.id}/map?${params}`),
      ]);
      setResults(resultResponse);
      setHistory(historyResponse);
      setMapResponse(mapData);
      setSelectedTerritoryCode(resultResponse.items?.[0]?.territory_code || "");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingResults(false);
    }
  }

  function updateFilters(changes) {
    if (changes.electionId && changes.electionId !== filters.electionId) {
      setComparisonCandidates([]);
      setComparison(null);
      setHistory(null);
      setMapResponse(null);
    }
    setFilters((current) => ({ ...current, ...changes }));
  }

  function toggleComparison(candidate) {
    if (!candidate) return;
    setComparison(null);
    setComparisonCandidates((current) => (
      current.some((item) => item.id === candidate.id)
        ? current.filter((item) => item.id !== candidate.id)
        : current.length < 5 ? [...current, candidate] : current
    ));
  }

  async function runComparison() {
    setLoadingComparison(true);
    setError("");
    try {
      setComparison(await apiRequest("/api/v1/electoral/comparisons", {
        method: "POST",
        body: JSON.stringify({
          election_id: filters.electionId,
          candidate_ids: comparisonCandidates.map((candidate) => candidate.id),
          level,
        }),
      }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingComparison(false);
    }
  }

  async function reviewIdentity(linkedCandidateIds) {
    try {
      await apiRequest(
        `/api/v1/electoral/candidates/${selectedCandidate.id}/identity-review`,
        {
          method: "PUT",
          body: JSON.stringify({
            linked_candidate_ids: linkedCandidateIds,
            decision: "CONFIRMED",
          }),
        },
      );
      setHistory(await apiRequest(
        `/api/v1/electoral/candidates/${selectedCandidate.id}/history`,
      ));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function toggleFavorite(candidate) {
    const existing = favorites.find((item) => item.target_id === candidate.id);
    try {
      if (existing) {
        await apiRequest(`/api/v1/electoral/favorites/${existing.id}`, { method: "DELETE" });
        setFavorites((current) => current.filter((item) => item.id !== existing.id));
      } else {
        const created = await apiRequest("/api/v1/electoral/favorites", {
          method: "POST",
          body: JSON.stringify({
            target_type: "candidate",
            target_id: candidate.id,
            label: candidate.ballot_name,
            snapshot: { number: candidate.number, party: candidate.party.acronym },
          }),
        });
        setFavorites((current) => [created, ...current]);
      }
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function saveComparison(name) {
    try {
      const created = await apiRequest("/api/v1/electoral/saved-comparisons", {
        method: "POST",
        body: JSON.stringify({
          name,
          election_id: filters.electionId,
          candidate_ids: comparisonCandidates.map((candidate) => candidate.id),
          level,
        }),
      });
      setSavedComparisons((current) => [created, ...current]);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function deleteSavedComparison(comparisonId) {
    try {
      await apiRequest(`/api/v1/electoral/saved-comparisons/${comparisonId}`, {
        method: "DELETE",
      });
      setSavedComparisons((current) => current.filter((item) => item.id !== comparisonId));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function loadSavedComparison(item) {
    setLoadingComparison(true);
    try {
      const loaded = await apiRequest("/api/v1/electoral/comparisons", {
        method: "POST",
        body: JSON.stringify({
          election_id: item.election_id,
          candidate_ids: item.candidate_ids,
          level: item.level,
          municipalityCode: item.municipalityCode,
        }),
      });
      setFilters((current) => ({ ...current, electionId: item.election_id }));
      setLevel(item.level);
      setComparisonCandidates(loaded.candidates);
      setComparison(loaded);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingComparison(false);
    }
  }

  function changeSort(nextSort) {
    const nextOrder = sort === nextSort && order === "desc" ? "asc" : "desc";
    setSort(nextSort);
    setOrder(nextOrder);
    loadResults(selectedCandidate, level, nextSort, nextOrder);
  }

  const hasMandateLayers = data?.availability.funcionalidades?.camadasMandato
    && data.availability.capacidades?.includes("ver_camadas_mandato");
  const hasReports = data?.availability.funcionalidades?.exportacoes
    && data.availability.capacidades?.includes("exportar");
  const hasDelegation = data?.availability.funcionalidades?.delegacao
    && data.availability.capacidades?.includes("delegar_acesso");
  const canCompare = data?.availability.capacidades?.includes("comparar_candidatos");
  const enabledSectionIds = new Set([
    "overview",
    "results",
    ...(canCompare ? ["comparisons"] : []),
    ...(hasMandateLayers ? ["mandate", "commitments"] : []),
    ...(hasReports ? ["reports"] : []),
    ...(hasDelegation ? ["access"] : []),
  ]);
  const sections = electoralSectionDefinitions.filter((section) => (
    enabledSectionIds.has(section.id)
  ));
  const sectionIdsKey = sections.map((section) => section.id).join(",");
  useEffect(() => {
    if (data) onSectionsChange?.(sectionIdsKey.split(",").filter(Boolean));
  }, [data, onSectionsChange, sectionIdsKey]);
  const currentSection = sections.find((section) => section.id === activeSection)
    || sections[0];

  return (
    <section className="page-section electoral-foundation-page">
      <header className="page-header electoral-page-header">
        <div>
          <p className="eyebrow">Módulo de insights eleitorais</p>
          <h1><Landmark className="electoral-title-icon" size={30} aria-hidden="true" />Inteligência Eleitoral</h1>
          <p>Dados eleitorais e gestão territorial organizados por área de trabalho.</p>
        </div>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!data && !error && <p aria-live="polite">Carregando catálogo eleitoral...</p>}

      {data && <div className="electoral-workspace-shell">
        <div className="electoral-workspace-content" aria-labelledby="electoral-section-title">
          <header className="electoral-section-heading">
            <p className="eyebrow">Área de trabalho</p>
            <h2 id="electoral-section-title">{currentSection.label}</h2>
            <p>{currentSection.description}</p>
          </header>

          {currentSection.id === "overview" && <>
            <div className="electoral-overview-grid">
              <div className="electoral-foundation-card">
                <ShieldCheck size={28} aria-hidden="true" />
                <div>
                  <h3>Catálogo consultável</h3>
                  <dl>
                    <div><dt>Mandato</dt><dd>{data.availability.mandato.jurisdicao}</dd></div>
                    <div><dt>Eleições</dt><dd>{data.elections.total}</dd></div>
                  </dl>
                </div>
              </div>
              <div className="electoral-foundation-card">
                <Database size={28} aria-hidden="true" />
                <div>
                  <h3>Cobertura oficial</h3>
                  <dl>
                    <div><dt>Recortes</dt><dd>{data.coverage.total}</dd></div>
                    <div>
                      <dt>Qualidade média</dt>
                      <dd>{data.quality.qualidadeMedia ?? "Sem carga"}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>
            <div className="electoral-quick-actions" aria-label="Atalhos da Inteligência Eleitoral">
              {sections.filter((section) => section.id !== "overview").map((section) => {
                const Icon = section.icon;
                return <button
                  type="button"
                  key={section.id}
                  onClick={() => navigateSection(section.id)}
                >
                  <Icon size={22} aria-hidden="true" />
                  <span><strong>{section.label}</strong><small>{section.description}</small></span>
                  <span aria-hidden="true">→</span>
                </button>;
              })}
            </div>
          </>}

          {currentSection.id === "results" && <>
            <CandidateSearch
              elections={data.elections.items || []}
              filters={filters}
              onFiltersChange={updateFilters}
              onSubmit={submitSearch}
              loading={loadingSearch}
              response={candidates}
              selectedCandidateId={selectedCandidate?.id}
              onSelect={(candidate) => loadResults(candidate)}
              onPageChange={runSearch}
              comparisonCandidates={comparisonCandidates}
              onToggleComparison={toggleComparison}
              favorites={favorites}
              onToggleFavorite={toggleFavorite}
            />
            {(selectedCandidate || loadingResults) && <nav
              className="electoral-detail-tabs"
              aria-label="Detalhes da candidatura"
            >
              {[
                ["results", "Resultado"],
                ["map", "Mapa"],
                ["history", "Histórico"],
              ].map(([id, label]) => <button
                type="button"
                key={id}
                className={analysisView === id ? "active" : ""}
                aria-pressed={analysisView === id}
                onClick={() => navigateAnalysis(id)}
              >{label}</button>)}
            </nav>}
            {analysisView === "results" && <CandidateResults
              response={results}
              loading={loadingResults}
              level={level}
              onLevelChange={(nextLevel) => loadResults(selectedCandidate, nextLevel)}
              onSort={changeSort}
              onPageChange={(page) => loadResults(selectedCandidate, level, sort, order, page)}
              selectedTerritoryCode={selectedTerritoryCode}
              onTerritorySelect={setSelectedTerritoryCode}
            />}
            {analysisView === "map" && <CandidateMap
              response={mapResponse}
              metric={mapMetric}
              onMetricChange={setMapMetric}
              selectedCode={selectedTerritoryCode}
              onSelect={setSelectedTerritoryCode}
            />}
            {analysisView === "history" && <CandidateHistory
              response={history}
              loading={loadingResults}
              selectedCandidateId={selectedCandidate?.id}
              onReview={reviewIdentity}
            />}
          </>}

          {currentSection.id === "comparisons" && <CandidateComparison
            selected={comparisonCandidates}
            response={comparison}
            loading={loadingComparison}
            onCompare={runComparison}
            onRemove={(candidateId) => toggleComparison(
              comparisonCandidates.find((item) => item.id === candidateId),
            )}
            onSave={saveComparison}
            saved={savedComparisons}
            onLoadSaved={loadSavedComparison}
            onDeleteSaved={deleteSavedComparison}
          />}
          {currentSection.id === "mandate" && <MandateIntelligencePanel
            electionId={filters.electionId}
            selectedCandidate={selectedCandidate}
            onError={setError}
          />}
          {currentSection.id === "commitments" && <PublicCommitmentsPanel onError={setError} />}
          {currentSection.id === "reports" && <ReportJobs
            electionId={filters.electionId}
            selectedCandidate={selectedCandidate}
            comparisonCandidates={comparisonCandidates}
            level={level}
            onError={setError}
          />}
          {currentSection.id === "access" && <DelegationPanel onError={setError} />}
        </div>
      </div>}
    </section>
  );
}
