import { Eye, Plus, Save, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";

const emptyAssumption = (territoryId = "") => ({
  territory_id: territoryId,
  candidate_share_delta: "0",
  denominator_delta: "0",
  candidate_share_uncertainty: "0",
  denominator_uncertainty: "0",
  rationale: "",
});

export function ScenarioSimulatorWorkspace({
  elections = [],
  initialElectionId,
  initialCandidate,
  initialResults,
  initialLevel = "municipality",
  onCreated,
  onError,
}) {
  const [electionId, setElectionId] = useState(initialElectionId || elections[0]?.id || "");
  const [level, setLevel] = useState(initialLevel);
  const [query, setQuery] = useState("");
  const [candidateOptions, setCandidateOptions] = useState([]);
  const [candidate, setCandidate] = useState(initialCandidate || null);
  const [territories, setTerritories] = useState(initialResults?.items || []);
  const [assumptions, setAssumptions] = useState(() => (
    initialResults?.items?.length ? [emptyAssumption(initialResults.items[0].territory_id)] : []
  ));
  const [name, setName] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    if (!initialCandidate || !initialResults?.items?.length) return;
    setCandidate(initialCandidate);
    setTerritories(initialResults.items);
    setAssumptions((current) => current.length
      ? current
      : [emptyAssumption(initialResults.items[0].territory_id)]);
  }, [initialCandidate, initialResults]);

  async function searchCandidates(event) {
    event.preventDefault();
    if (!electionId || query.trim().length < 2) return;
    setBusy("search");
    try {
      const params = new URLSearchParams({ election_id: electionId, q: query.trim() });
      const response = await apiRequest(`/api/v1/electoral/candidates?${params}`);
      setCandidateOptions(response.items || []);
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy("");
    }
  }

  async function chooseCandidate(item) {
    setBusy("baseline");
    setCandidate(item);
    setPreview(null);
    try {
      const params = new URLSearchParams({
        election_id: electionId,
        level,
        page: "1",
        perPage: "100",
        sort: "name",
        order: "asc",
      });
      const response = await apiRequest(
        `/api/v1/electoral/candidates/${item.id}/results?${params}`,
      );
      const rows = response.items || [];
      setTerritories(rows);
      setAssumptions(rows.length ? [emptyAssumption(rows[0].territory_id)] : []);
    } catch (error) {
      setTerritories([]);
      setAssumptions([]);
      onError(error.message);
    } finally {
      setBusy("");
    }
  }

  function changeElection(value) {
    setElectionId(value);
    setCandidate(null);
    setCandidateOptions([]);
    setTerritories([]);
    setAssumptions([]);
    setPreview(null);
  }

  function addAssumption() {
    const available = territories.find((territory) => (
      !assumptions.some((item) => item.territory_id === territory.territory_id)
    ));
    if (available) setAssumptions((current) => [
      ...current,
      emptyAssumption(available.territory_id),
    ]);
  }

  function updateAssumption(index, field, value) {
    setPreview(null);
    setAssumptions((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [field]: value } : item
    )));
  }

  function payload() {
    return {
      baseline_election_id: electionId,
      candidate_id: candidate.id,
      level,
      assumptions: assumptions.map(toApiAssumption),
    };
  }

  async function simulate() {
    setBusy("preview");
    try {
      setPreview(await apiRequest("/api/v1/electoral/scenarios/preview", {
        method: "POST",
        body: JSON.stringify(payload()),
      }));
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy("");
    }
  }

  async function save(event) {
    event.preventDefault();
    setBusy("save");
    try {
      const created = await apiRequest("/api/v1/electoral/scenarios", {
        method: "POST",
        body: JSON.stringify({ ...payload(), name }),
      });
      onCreated(created);
      setName("");
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy("");
    }
  }

  const valid = Boolean(
    electionId
    && candidate
    && assumptions.length
    && assumptions.every((item) => item.territory_id && item.rationale.trim()),
  );
  return <section className="scenario-simulator" aria-labelledby="scenario-simulator-title">
    <header>
      <div><p className="eyebrow">Simulador territorial</p><h3 id="scenario-simulator-title">Construir simulação</h3></div>
      <span>1. Base · 2. Premissas · 3. Resultado</span>
    </header>

    <div className="scenario-baseline-selector">
      <label>Eleição-base<select value={electionId} onChange={(event) => changeElection(event.target.value)}>
        <option value="">Selecione</option>
        {elections.map((item) => <option key={item.id} value={item.id}>{item.nome || item.name || item.year}</option>)}
      </select></label>
      <label>Nível territorial<select value={level} onChange={(event) => {
        setLevel(event.target.value);
        setCandidate(null);
        setTerritories([]);
        setAssumptions([]);
      }}>
        <option value="municipality">Município</option>
        <option value="electoral_zone">Zona eleitoral</option>
      </select></label>
      <form onSubmit={searchCandidates} className="scenario-candidate-search">
        <label>Buscar candidatura<input value={query} minLength={2} onChange={(event) => setQuery(event.target.value)} placeholder="Nome ou número" /></label>
        <button type="submit" className="secondary-button" disabled={!electionId || query.trim().length < 2 || busy === "search"}><Search size={16} /> Buscar</button>
      </form>
    </div>
    {candidateOptions.length > 0 && <div className="scenario-candidate-options" aria-label="Candidaturas encontradas">
      {candidateOptions.map((item) => <button type="button" key={item.id} onClick={() => chooseCandidate(item)}>
        <strong>{item.ballot_name}</strong><small>{item.number} · {item.party?.acronym}</small>
      </button>)}
    </div>}
    {candidate && <p className="scenario-selected-baseline"><strong>Base selecionada:</strong> {candidate.ballot_name || candidate.full_name}</p>}
    {!candidate && <p className="electoral-empty">Busque e selecione uma candidatura sem sair do simulador.</p>}

    {assumptions.map((assumption, index) => <fieldset key={`${index}-${assumption.territory_id}`} className="scenario-assumption-card">
      <legend>Premissa territorial {index + 1}</legend>
      <label>Território<select value={assumption.territory_id} onChange={(event) => updateAssumption(index, "territory_id", event.target.value)}>
        {territories.map((territory) => <option key={territory.territory_id} value={territory.territory_id} disabled={assumptions.some((item, itemIndex) => itemIndex !== index && item.territory_id === territory.territory_id)}>{territory.territory_name}</option>)}
      </select></label>
      <PercentInput label="Variação da participação (p.p.)" value={assumption.candidate_share_delta} min="-100" onChange={(value) => updateAssumption(index, "candidate_share_delta", value)} />
      <PercentInput label="Variação do denominador (%)" value={assumption.denominator_delta} min="-100" onChange={(value) => updateAssumption(index, "denominator_delta", value)} />
      <PercentInput label="Incerteza da participação (p.p.)" value={assumption.candidate_share_uncertainty} onChange={(value) => updateAssumption(index, "candidate_share_uncertainty", value)} />
      <PercentInput label="Incerteza do denominador (%)" value={assumption.denominator_uncertainty} onChange={(value) => updateAssumption(index, "denominator_uncertainty", value)} />
      <label className="scenario-rationale">Justificativa<input value={assumption.rationale} maxLength={500} onChange={(event) => updateAssumption(index, "rationale", event.target.value)} /></label>
      {assumptions.length > 1 && <button type="button" className="icon-button" aria-label={`Remover premissa ${index + 1}`} onClick={() => setAssumptions((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={17} /></button>}
    </fieldset>)}
    {candidate && territories.length > assumptions.length && <button type="button" className="secondary-button scenario-add-assumption" onClick={addAssumption}><Plus size={16} /> Adicionar território</button>}

    <div className="scenario-simulator-actions">
      <button type="button" className="primary-button" disabled={!valid || Boolean(busy)} onClick={simulate}><Eye size={17} /> {busy === "preview" ? "Simulando..." : "Simular resultado"}</button>
    </div>
    {preview && <PreviewResult preview={preview} />}
    {preview && <form className="scenario-save-form" onSubmit={save}>
      <label>Nome do cenário<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
      <button className="primary-button" disabled={!name.trim() || busy === "save"}><Save size={17} /> {busy === "save" ? "Salvando..." : "Salvar cenário"}</button>
    </form>}
  </section>;
}

function PreviewResult({ preview }) {
  const result = preview.result;
  return <section className="scenario-preview" aria-live="polite" aria-labelledby="scenario-preview-title">
    <header><div><p className="eyebrow">Prévia não persistida</p><h4 id="scenario-preview-title">Resultado da simulação</h4></div><strong>{number(result.projected_total_votes)} votos</strong></header>
    <div className="shared-scenario-summary">
      <article><span>Base oficial</span><strong>{number(result.baseline_total_votes)}</strong></article>
      <article><span>Diferença simulada</span><strong>{signed(result.projected_total_votes - result.baseline_total_votes)}</strong></article>
      <article><span>Faixa inferior</span><strong>{number(result.uncertainty_interval.lower_votes)}</strong></article>
      <article><span>Faixa superior</span><strong>{number(result.uncertainty_interval.upper_votes)}</strong></article>
    </div>
    <div className="electoral-table-wrapper"><table className="electoral-table">
      <thead><tr><th>Território</th><th>Base</th><th>Simulado</th><th>Diferença</th><th>Faixa</th></tr></thead>
      <tbody>{result.territories.map((item) => <tr key={item.territory_id}><td>{item.territory_name}</td><td>{number(item.baseline_votes)}</td><td>{number(item.projected_votes)}</td><td>{signed(item.vote_difference)}</td><td>{number(item.uncertainty_interval.lower_votes)}–{number(item.uncertainty_interval.upper_votes)}</td></tr>)}</tbody>
    </table></div>
    <p className="scenario-statistical-note">{result.uncertainty_interval.disclaimer}</p>
  </section>;
}

function PercentInput({ label, value, min = "0", onChange }) {
  return <label>{label}<input type="number" min={min} max="100" step="0.1" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function toApiAssumption(assumption) {
  return {
    territory_id: assumption.territory_id,
    candidate_share_delta: Number(assumption.candidate_share_delta) / 100,
    denominator_delta: Number(assumption.denominator_delta) / 100,
    candidate_share_uncertainty: Number(assumption.candidate_share_uncertainty) / 100,
    denominator_uncertainty: Number(assumption.denominator_uncertainty) / 100,
    rationale: assumption.rationale,
  };
}

function number(value = 0) { return value.toLocaleString("pt-BR"); }
function signed(value = 0) { return `${value >= 0 ? "+" : ""}${number(value)}`; }
