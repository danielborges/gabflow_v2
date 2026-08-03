import { Database, Landmark, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";
import { CandidateResults } from "./CandidateResults";
import { CandidateSearch } from "./CandidateSearch";
import { CandidateComparison } from "./CandidateComparison";
import { CandidateHistory } from "./CandidateHistory";
import { CandidateMap } from "./CandidateMap";
import { DelegationPanel } from "./DelegationPanel";
import { ReportJobs } from "./ReportJobs";
import { MandateIntelligencePanel } from "./MandateIntelligencePanel";

const initialParams = new URLSearchParams(window.location.search);

export function ElectoralIntelligencePage() {
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
    Object.entries(values).forEach(([key, value]) => value ? params.set(key, value) : params.delete(key));
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

  async function loadResults(candidate, nextLevel = level, nextSort = sort, nextOrder = order, page = 1) {
    setSelectedCandidate(candidate);
    setLevel(nextLevel);
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
    setComparisonCandidates((current) => current.some((item) => item.id === candidate.id)
      ? current.filter((item) => item.id !== candidate.id)
      : current.length < 5 ? [...current, candidate] : current);
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
      await apiRequest(`/api/v1/electoral/candidates/${selectedCandidate.id}/identity-review`, {
        method: "PUT",
        body: JSON.stringify({ linked_candidate_ids: linkedCandidateIds, decision: "CONFIRMED" }),
      });
      setHistory(await apiRequest(`/api/v1/electoral/candidates/${selectedCandidate.id}/history`));
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
          body: JSON.stringify({ target_type: "candidate", target_id: candidate.id, label: candidate.ballot_name, snapshot: { number: candidate.number, party: candidate.party.acronym } }),
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
        body: JSON.stringify({ name, election_id: filters.electionId, candidate_ids: comparisonCandidates.map((candidate) => candidate.id), level }),
      });
      setSavedComparisons((current) => [created, ...current]);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function deleteSavedComparison(comparisonId) {
    try {
      await apiRequest(`/api/v1/electoral/saved-comparisons/${comparisonId}`, { method: "DELETE" });
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
        body: JSON.stringify({ election_id: item.election_id, candidate_ids: item.candidate_ids, level: item.level, municipalityCode: item.municipalityCode }),
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

  return (
    <section className="page-section electoral-foundation-page">
      <header className="page-header">
        <div><p className="eyebrow">Módulo exclusivo do Parlamentar</p><h1>Inteligência Eleitoral</h1><p>Pesquisa e resultado territorial com fonte, versão e metodologia.</p></div>
        <Landmark size={30} aria-hidden="true" />
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!data && !error && <p aria-live="polite">Carregando catálogo eleitoral...</p>}
      {data && (
        <>
          <div className="electoral-overview-grid">
            <div className="electoral-foundation-card"><ShieldCheck size={28} aria-hidden="true" /><div><h2>Catálogo consultável</h2><dl><div><dt>Mandato</dt><dd>{data.availability.mandato.jurisdicao}</dd></div><div><dt>Eleições</dt><dd>{data.elections.total}</dd></div></dl></div></div>
            <div className="electoral-foundation-card"><Database size={28} aria-hidden="true" /><div><h2>Cobertura oficial</h2><dl><div><dt>Recortes</dt><dd>{data.coverage.total}</dd></div><div><dt>Qualidade média</dt><dd>{data.quality.qualidadeMedia ?? "Sem carga"}</dd></div></dl></div></div>
          </div>
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
          <CandidateResults response={results} loading={loadingResults} level={level} onLevelChange={(nextLevel) => loadResults(selectedCandidate, nextLevel)} onSort={changeSort} onPageChange={(page) => loadResults(selectedCandidate, level, sort, order, page)} selectedTerritoryCode={selectedTerritoryCode} onTerritorySelect={setSelectedTerritoryCode} />
          <CandidateMap response={mapResponse} metric={mapMetric} onMetricChange={setMapMetric} selectedCode={selectedTerritoryCode} onSelect={setSelectedTerritoryCode} />
          <CandidateHistory response={history} loading={loadingResults} selectedCandidateId={selectedCandidate?.id} onReview={reviewIdentity} />
          <CandidateComparison selected={comparisonCandidates} response={comparison} loading={loadingComparison} onCompare={runComparison} onRemove={(candidateId) => toggleComparison(comparisonCandidates.find((item) => item.id === candidateId))} onSave={saveComparison} saved={savedComparisons} onLoadSaved={loadSavedComparison} onDeleteSaved={deleteSavedComparison} />
          {data.availability.funcionalidades?.camadasMandato && data.availability.capacidades?.includes("ver_camadas_mandato") && (
            <MandateIntelligencePanel electionId={filters.electionId} selectedCandidate={selectedCandidate} onError={setError} />
          )}
          {data.availability.funcionalidades?.exportacoes && data.availability.capacidades?.includes("exportar") && (
            <ReportJobs electionId={filters.electionId} selectedCandidate={selectedCandidate} comparisonCandidates={comparisonCandidates} level={level} onError={setError} />
          )}
          {data.availability.funcionalidades?.delegacao && data.availability.capacidades?.includes("delegar_acesso") && (
            <DelegationPanel onError={setError} />
          )}
        </>
      )}
    </section>
  );
}
