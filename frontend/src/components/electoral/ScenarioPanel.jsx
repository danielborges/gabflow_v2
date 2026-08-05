import { Clipboard, FlaskConical, Link2, SlidersHorizontal, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api";
import { ScenarioPortfolioPanel } from "./ScenarioPortfolioPanel";
import { ScenarioSimulatorWorkspace } from "./ScenarioSimulatorWorkspace";

export function ScenarioPanel({ elections, electionId, selectedCandidate, results, level, onError }) {
  const [items, setItems] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [copyDraft, setCopyDraft] = useState(null);
  const [shareDraft, setShareDraft] = useState(null);
  const [sensitivityDraft, setSensitivityDraft] = useState(null);
  const [shareLink, setShareLink] = useState(null);
  const [sharesByScenario, setSharesByScenario] = useState({});
  const [managedScenarioId, setManagedScenarioId] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showPortfolios, setShowPortfolios] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await apiRequest("/api/v1/electoral/scenarios");
      setItems(response.content || []);
    } catch (error) { onError(error.message); }
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  function beginCopy(item) {
    setCopyDraft({
      sourceId: item.id,
      sourceName: item.name,
      name: `${item.name} - cópia`,
      assumptions: item.assumptions.map(toEditableAssumption),
    });
  }

  function updateCopyAssumption(index, field, value) {
    setCopyDraft((current) => ({
      ...current,
      assumptions: current.assumptions.map((assumption, assumptionIndex) => (
        assumptionIndex === index ? { ...assumption, [field]: value } : assumption
      )),
    }));
  }

  async function submitCopy(event) {
    event.preventDefault();
    try {
      const created = await apiRequest(`/api/v1/electoral/scenarios/${copyDraft.sourceId}/copy`, {
        method: "POST",
        body: JSON.stringify({
          name: copyDraft.name,
          assumptions: copyDraft.assumptions.map(toApiAssumption),
        }),
      });
      setItems((current) => [created, ...current]);
      setCopyDraft(null);
    } catch (error) { onError(error.message); }
  }

  async function submitShare(event) {
    event.preventDefault();
    try {
      const response = await apiRequest(`/api/v1/electoral/scenarios/${shareDraft.id}/share`, {
        method: "POST",
        body: JSON.stringify({ expires_in_days: Number(shareDraft.days) }),
      });
      setShareLink(response);
      setCopied(false);
      setShareDraft(null);
      await loadShares(response.scenario_id);
    } catch (error) { onError(error.message); }
  }

  async function copyShareUrl() {
    if (!navigator.clipboard?.writeText) {
      setCopied(false);
      return;
    }
    try {
      await navigator.clipboard.writeText(shareLink.url);
      setCopied(true);
    } catch { setCopied(false); }
  }

  async function loadShares(scenarioOrId) {
    const scenarioId = typeof scenarioOrId === "string" ? scenarioOrId : scenarioOrId.id;
    try {
      const response = await apiRequest(`/api/v1/electoral/scenarios/${scenarioId}/shares`);
      setSharesByScenario((current) => ({ ...current, [scenarioId]: response.content || [] }));
      setManagedScenarioId(scenarioId);
    } catch (error) { onError(error.message); }
  }

  async function revokeShare(scenarioId, shareId) {
    try {
      await apiRequest(`/api/v1/electoral/scenarios/${scenarioId}/shares/${shareId}`, {
        method: "DELETE",
      });
      await loadShares(scenarioId);
    } catch (error) { onError(error.message); }
  }

  async function submitSensitivity(event) {
    event.preventDefault();
    try {
      const response = await apiRequest(
        `/api/v1/electoral/scenarios/${sensitivityDraft.id}/sensitivity`,
        {
          method: "POST",
          body: JSON.stringify({
            candidate_share_range_pp: Number(sensitivityDraft.shareRange),
            denominator_range_percent: Number(sensitivityDraft.denominatorRange),
            steps: Number(sensitivityDraft.steps),
          }),
        },
      );
      setAnalysis(response);
      setSensitivityDraft(null);
    } catch (error) { onError(error.message); }
  }

  async function compare() {
    try {
      const response = await apiRequest("/api/v1/electoral/scenarios/compare", {
        method: "POST",
        body: JSON.stringify({ scenario_ids: selectedIds }),
      });
      setAnalysis(response);
    } catch (error) { onError(error.message); }
  }

  function toggleSelection(id) {
    setSelectedIds((current) => current.includes(id)
      ? current.filter((value) => value !== id)
      : current.length < 5 ? [...current, id] : current);
  }

  return <section className="electoral-analysis-card" aria-labelledby="scenarios-title">
    <header className="electoral-results-header">
      <div><p className="eyebrow">Laboratório de premissas</p><h2 id="scenarios-title">Simulador eleitoral</h2></div>
      <FlaskConical size={28} aria-hidden="true" />
    </header>
    <p className="electoral-simulation-warning">Simulação hipotética: não altera resultados oficiais, não é pesquisa registrada e não é previsão.</p>
    <ScenarioSimulatorWorkspace
      elections={elections}
      initialElectionId={electionId}
      initialCandidate={selectedCandidate}
      initialResults={results}
      initialLevel={level}
      onCreated={(created) => setItems((current) => [created, ...current])}
      onError={onError}
    />

    {copyDraft && <CopyEditor draft={copyDraft} onChange={setCopyDraft} onAssumptionChange={updateCopyAssumption} onSubmit={submitCopy} onClose={() => setCopyDraft(null)} />}
    {shareDraft && <ShareEditor draft={shareDraft} onChange={setShareDraft} onSubmit={submitShare} onClose={() => setShareDraft(null)} />}
    {sensitivityDraft && <SensitivityEditor draft={sensitivityDraft} onChange={setSensitivityDraft} onSubmit={submitSensitivity} onClose={() => setSensitivityDraft(null)} />}

    {selectedIds.length >= 2 && <button className="secondary-button scenario-compare-button" type="button" onClick={compare}>Comparar {selectedIds.length} cenários</button>}
    {shareLink && <div className="electoral-share-link" role="status">
      <strong>Link somente leitura criado</strong>
      <input aria-label="URL compartilhada" readOnly value={shareLink.url} />
      <button type="button" className="secondary-button" onClick={copyShareUrl}><Clipboard size={16} /> {copied ? "Copiado" : "Copiar URL"}</button>
      <small>O token só é exibido agora. Se perder a URL, gere um novo link.</small>
    </div>}
    {analysis?.analysis_type === "SENSITIVITY" && <SensitivityResult analysis={analysis} />}
    {analysis?.analysis_type === "COMPARISON" && <ComparisonResult analysis={analysis} />}
    <button type="button" className="secondary-button scenario-portfolio-toggle" onClick={() => setShowPortfolios((current) => !current)}><FolderPortfolioIcon /> {showPortfolios ? "Fechar portfólios" : "Abrir metas e portfólios"}</button>
    {showPortfolios && <ScenarioPortfolioPanel scenarios={items} onError={onError} />}

    <div className="electoral-insight-list">
      {items.map((item) => <article key={item.id} className="electoral-insight-card">
        <header><strong>{item.name}</strong><span>SIMULAÇÃO</span></header>
        <label className="electoral-scenario-select"><input type="checkbox" checked={selectedIds.includes(item.id)} onChange={() => toggleSelection(item.id)} /> Selecionar para comparar</label>
        <p>{item.result.baseline_total_votes.toLocaleString("pt-BR")} votos na base → <strong>{item.result.projected_total_votes.toLocaleString("pt-BR")}</strong> no cenário</p>
        {item.result.uncertainty_interval && <p>Faixa: {item.result.uncertainty_interval.lower_votes.toLocaleString("pt-BR")} a {item.result.uncertainty_interval.upper_votes.toLocaleString("pt-BR")} votos</p>}
        <small>Dataset {item.baseline_snapshot.dataset_version} · {item.methodology_version}</small>
        <footer className="electoral-scenario-actions">
          <button type="button" className="secondary-button" onClick={() => beginCopy(item)}>Copiar e editar</button>
          <button type="button" className="secondary-button" onClick={() => setShareDraft({ id: item.id, name: item.name, days: "7" })}>Criar link</button>
          <button type="button" className="secondary-button" onClick={() => loadShares(item)}><Link2 size={16} /> Gerenciar links</button>
          <button type="button" className="secondary-button" onClick={() => setSensitivityDraft({ id: item.id, name: item.name, shareRange: "5", denominatorRange: "5", steps: "5" })}><SlidersHorizontal size={16} /> Configurar sensibilidade</button>
        </footer>
        {managedScenarioId === item.id && <ShareManagement shares={sharesByScenario[item.id] || []} onRevoke={(shareId) => revokeShare(item.id, shareId)} />}
      </article>)}
    </div>
  </section>;
}

function PercentInput({ label, value, min = "0", onChange }) {
  return <label>{label}<input type="number" min={min} max="100" step="0.1" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function EditorHeader({ title, onClose }) {
  return <header><h3>{title}</h3><button type="button" className="icon-button" onClick={onClose} aria-label="Fechar editor"><X size={18} /></button></header>;
}

function CopyEditor({ draft, onChange, onAssumptionChange, onSubmit, onClose }) {
  return <form className="scenario-editor" onSubmit={onSubmit} aria-label="Editar cópia do cenário">
    <EditorHeader title={`Copiar ${draft.sourceName}`} onClose={onClose} />
    <label>Nome da cópia<input value={draft.name} maxLength={160} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label>
    {draft.assumptions.map((assumption, index) => <fieldset key={assumption.territory_id}>
      <legend>Premissa {index + 1}</legend>
      <PercentInput label={`Participação da premissa ${index + 1} (p.p.)`} min="-100" value={assumption.candidate_share_delta} onChange={(value) => onAssumptionChange(index, "candidate_share_delta", value)} />
      <PercentInput label={`Denominador da premissa ${index + 1} (%)`} min="-100" value={assumption.denominator_delta} onChange={(value) => onAssumptionChange(index, "denominator_delta", value)} />
      <PercentInput label={`Incerteza de participação ${index + 1} (p.p.)`} value={assumption.candidate_share_uncertainty} onChange={(value) => onAssumptionChange(index, "candidate_share_uncertainty", value)} />
      <PercentInput label={`Incerteza do denominador ${index + 1} (%)`} value={assumption.denominator_uncertainty} onChange={(value) => onAssumptionChange(index, "denominator_uncertainty", value)} />
      <label>Justificativa da premissa {index + 1}<input value={assumption.rationale} maxLength={500} onChange={(event) => onAssumptionChange(index, "rationale", event.target.value)} /></label>
    </fieldset>)}
    <button className="primary-button" disabled={!draft.name.trim() || draft.assumptions.some((item) => !item.rationale.trim())}>Criar cópia</button>
  </form>;
}

function ShareEditor({ draft, onChange, onSubmit, onClose }) {
  return <form className="scenario-editor" onSubmit={onSubmit} aria-label="Criar compartilhamento">
    <EditorHeader title={`Compartilhar ${draft.name}`} onClose={onClose} />
    <label>Validade do link (dias)<input type="number" min="1" max="30" value={draft.days} onChange={(event) => onChange({ ...draft, days: event.target.value })} /></label>
    <p>O destinatário deverá estar autenticado e autorizado no mesmo gabinete.</p>
    <button className="primary-button">Gerar link somente leitura</button>
  </form>;
}

function SensitivityEditor({ draft, onChange, onSubmit, onClose }) {
  return <form className="scenario-editor" onSubmit={onSubmit} aria-label="Configurar análise de sensibilidade">
    <EditorHeader title={`Sensibilidade de ${draft.name}`} onClose={onClose} />
    <PercentInput label="Amplitude de participação (p.p.)" value={draft.shareRange} onChange={(value) => onChange({ ...draft, shareRange: value })} />
    <PercentInput label="Amplitude do denominador (%)" value={draft.denominatorRange} onChange={(value) => onChange({ ...draft, denominatorRange: value })} />
    <label>Passos da grade<select value={draft.steps} onChange={(event) => onChange({ ...draft, steps: event.target.value })}>
      {[3, 5, 7, 9, 11].map((steps) => <option key={steps} value={steps}>{steps} × {steps} ({steps * steps} amostras)</option>)}
    </select></label>
    <button className="primary-button">Executar sensibilidade</button>
  </form>;
}

function ShareManagement({ shares, onRevoke }) {
  return <section className="scenario-share-management" aria-label="Compartilhamentos do cenário">
    <h3>Links emitidos</h3>
    {!shares.length && <p>Nenhum link emitido.</p>}
    {shares.map((share) => <div key={share.id}>
      <span className={`scenario-share-status status-${share.status.toLowerCase()}`}>{share.status}</span>
      <span>Expira em {new Date(share.expires_at).toLocaleString("pt-BR")}</span>
      <span>{share.access_count} acesso(s)</span>
      <span>{share.last_accessed_at ? `Último acesso em ${new Date(share.last_accessed_at).toLocaleString("pt-BR")}` : "Ainda não acessado"}</span>
      {share.status === "ACTIVE" && <button type="button" className="secondary-button" onClick={() => onRevoke(share.id)}>Revogar</button>}
    </div>)}
  </section>;
}

function ComparisonResult({ analysis }) {
  const { result } = analysis;
  return <section className="electoral-scenario-comparison" aria-labelledby="comparison-result-title">
    <h3 id="comparison-result-title">Comparação compatível</h3>
    <div className="electoral-table-wrapper"><table className="electoral-table">
      <thead><tr><th>Cenário</th><th>Total</th><th>Diferença da base</th><th>Diferença do primeiro</th><th>Faixa</th></tr></thead>
      <tbody>{result.scenarios.map((scenario) => <tr key={scenario.scenario_id}>
        <td>{scenario.name}</td><td>{number(scenario.projected_total_votes)}</td><td>{signed(scenario.difference_from_baseline)}</td><td>{signed(scenario.difference_from_anchor)}</td>
        <td>{number(scenario.uncertainty_interval?.lower_votes ?? scenario.projected_total_votes)}–{number(scenario.uncertainty_interval?.upper_votes ?? scenario.projected_total_votes)}</td>
      </tr>)}</tbody>
    </table></div>
    <h4>Detalhamento territorial</h4>
    <div className="electoral-table-wrapper"><table className="electoral-table">
      <thead><tr><th>Território</th>{result.scenarios.map((scenario) => <th key={scenario.scenario_id}>{scenario.name}</th>)}</tr></thead>
      <tbody>{(result.territories || []).map((territory) => <tr key={territory.territory_id}><td>{territory.territory_name}</td>{territory.scenarios.map((scenario) => <td key={scenario.scenario_id}>{number(scenario.projected_votes)}<small>{(scenario.projected_share * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%</small></td>)}</tr>)}</tbody>
    </table></div>
    <p className="scenario-statistical-note">Comparação hipotética; não representa ranking preditivo.</p>
  </section>;
}

function SensitivityResult({ analysis }) {
  const { result } = analysis;
  return <section className="electoral-scenario-comparison" aria-labelledby="sensitivity-result-title">
    <h3 id="sensitivity-result-title">Resultado da sensibilidade</h3>
    <p><strong>{number(result.minimum_projected_total_votes)}</strong> a <strong>{number(result.maximum_projected_total_votes)}</strong> votos; centro em {number(result.baseline_projected_total_votes)}.</p>
    <p className="scenario-statistical-note">{result.disclaimer || "Faixa hipotética, sem nível de confiança estatístico."}</p>
    <div className="electoral-table-wrapper sensitivity-grid"><table className="electoral-table">
      <thead><tr><th>Participação</th><th>Denominador</th><th>Votos projetados</th></tr></thead>
      <tbody>{result.samples.map((sample) => <tr key={`${sample.candidate_share_offset}-${sample.denominator_offset}`}>
        <td>{signedPercent(sample.candidate_share_offset, " p.p.")}</td><td>{signedPercent(sample.denominator_offset, "%")}</td><td>{number(sample.projected_total_votes)}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

function toEditableAssumption(assumption) {
  return {
    ...assumption,
    candidate_share_delta: String((assumption.candidate_share_delta || 0) * 100),
    denominator_delta: String((assumption.denominator_delta || 0) * 100),
    candidate_share_uncertainty: String((assumption.candidate_share_uncertainty || 0) * 100),
    denominator_uncertainty: String((assumption.denominator_uncertainty || 0) * 100),
  };
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
function signedPercent(value = 0, suffix) { return `${value >= 0 ? "+" : ""}${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}${suffix}`; }

function FolderPortfolioIcon() { return <span aria-hidden="true">▣</span>; }
