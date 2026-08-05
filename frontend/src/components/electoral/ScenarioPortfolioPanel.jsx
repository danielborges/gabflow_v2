import { Archive, Download, Flag, FolderKanban, History, Plus, Star, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiRequest } from "../../api";

export function ScenarioPortfolioPanel({ scenarios, onError }) {
  const [portfolios, setPortfolios] = useState([]);
  const [active, setActive] = useState(null);
  const [history, setHistory] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [initialIds, setInitialIds] = useState([]);
  const [scenarioToAdd, setScenarioToAdd] = useState("");
  const [goal, setGoal] = useState({ scope: "TOTAL", metric: "VOTES", territoryId: "", target: "", rationale: "" });
  const [purpose, setPurpose] = useState("");

  useEffect(() => {
    apiRequest("/api/v1/electoral/scenario-portfolios")
      .then((response) => setPortfolios(response.content || []))
      .catch((error) => onError(error.message));
  }, [onError]);

  const activeScenarioIds = new Set((active?.scenarios || []).map((item) => item.id));
  const availableScenarios = scenarios.filter((item) => !activeScenarioIds.has(item.id));
  const territoryOptions = useMemo(() => {
    const firstId = active?.scenarios?.[0]?.id;
    return scenarios.find((item) => item.id === firstId)?.result?.territories || [];
  }, [active, scenarios]);

  async function createPortfolio(event) {
    event.preventDefault();
    try {
      const created = await apiRequest("/api/v1/electoral/scenario-portfolios", {
        method: "POST",
        body: JSON.stringify({ name, description, scenario_ids: initialIds }),
      });
      setPortfolios((current) => [created, ...current]);
      setActive(created);
      setName(""); setDescription(""); setInitialIds([]);
    } catch (error) { onError(error.message); }
  }

  async function openPortfolio(id) {
    try {
      setActive(await apiRequest(`/api/v1/electoral/scenario-portfolios/${id}`));
      setHistory([]);
    } catch (error) { onError(error.message); }
  }

  async function addScenario() {
    if (!scenarioToAdd) return;
    try {
      const updated = await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}/scenarios`, {
        method: "POST",
        body: JSON.stringify({ scenario_id: scenarioToAdd }),
      });
      setActive(updated); setScenarioToAdd("");
    } catch (error) { onError(error.message); }
  }

  async function removeScenario(id) {
    try {
      await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}/scenarios/${id}`, { method: "DELETE" });
      await openPortfolio(active.id);
    } catch (error) { onError(error.message); }
  }

  async function setReference(id) {
    try {
      setActive(await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}/reference`, {
        method: "PUT",
        body: JSON.stringify({ scenario_id: id }),
      }));
    } catch (error) { onError(error.message); }
  }

  async function saveGoals(nextGoals) {
    try {
      setActive(await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}/goals`, {
        method: "PUT",
        body: JSON.stringify({ goals: nextGoals }),
      }));
    } catch (error) { onError(error.message); }
  }

  async function addGoal(event) {
    event.preventDefault();
    const target = Number(goal.target) / (goal.metric === "SHARE" ? 100 : 1);
    await saveGoals([...(active.goals || []), {
      scope: goal.scope,
      metric: goal.metric,
      territory_id: goal.scope === "TERRITORY" ? goal.territoryId : null,
      target_value: target,
      rationale: goal.rationale,
    }]);
    setGoal({ scope: "TOTAL", metric: "VOTES", territoryId: "", target: "", rationale: "" });
  }

  async function loadHistory() {
    try {
      const response = await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}/history`);
      setHistory(response.content || []);
    } catch (error) { onError(error.message); }
  }

  async function archivePortfolio() {
    try {
      const updated = await apiRequest(`/api/v1/electoral/scenario-portfolios/${active.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "ARCHIVED" }),
      });
      setActive(updated);
      setPortfolios((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (error) { onError(error.message); }
  }

  async function exportPortfolio() {
    try {
      const blob = await apiDownload(`/api/v1/electoral/scenario-portfolios/${active.id}/export`, {
        method: "POST",
        body: JSON.stringify({ purpose }),
        headers: { "Content-Type": "application/json" },
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `portfolio-cenarios-${active.id}.csv`; anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) { onError(error.message); }
  }

  return <section className="scenario-portfolio-panel" aria-labelledby="portfolio-title">
    <header className="electoral-results-header"><div><p className="eyebrow">Organização de alternativas</p><h3 id="portfolio-title">Metas e portfólios</h3></div><FolderKanban size={25} /></header>
    <p className="scenario-statistical-note">O cenário de referência é apenas uma base de comparação e não representa previsão ou recomendação.</p>
    <form className="scenario-editor" onSubmit={createPortfolio}>
      <label>Nome do portfólio<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
      <label>Descrição<input value={description} maxLength={1000} onChange={(event) => setDescription(event.target.value)} /></label>
      <fieldset><legend>Cenários iniciais compatíveis</legend>{scenarios.map((scenario) => <label key={scenario.id} className="electoral-scenario-select"><input type="checkbox" checked={initialIds.includes(scenario.id)} onChange={() => setInitialIds((current) => current.includes(scenario.id) ? current.filter((id) => id !== scenario.id) : [...current, scenario.id])} />{scenario.name}</label>)}</fieldset>
      <button className="primary-button" disabled={!name.trim()}><Plus size={16} /> Criar portfólio</button>
    </form>
    <div className="portfolio-selector">{portfolios.map((portfolio) => <button type="button" className={active?.id === portfolio.id ? "secondary-button active" : "secondary-button"} key={portfolio.id} onClick={() => openPortfolio(portfolio.id)}>{portfolio.name} · {portfolio.status}</button>)}</div>
    {active && <PortfolioWorkspace
      active={active}
      availableScenarios={availableScenarios}
      scenarioToAdd={scenarioToAdd}
      setScenarioToAdd={setScenarioToAdd}
      addScenario={addScenario}
      removeScenario={removeScenario}
      setReference={setReference}
      goal={goal}
      setGoal={setGoal}
      territoryOptions={territoryOptions}
      addGoal={addGoal}
      removeGoal={(id) => saveGoals(active.goals.filter((item) => item.id !== id))}
      history={history}
      loadHistory={loadHistory}
      archivePortfolio={archivePortfolio}
      purpose={purpose}
      setPurpose={setPurpose}
      exportPortfolio={exportPortfolio}
    />}
  </section>;
}

function PortfolioWorkspace({ active, availableScenarios, scenarioToAdd, setScenarioToAdd, addScenario, removeScenario, setReference, goal, setGoal, territoryOptions, addGoal, removeGoal, history, loadHistory, archivePortfolio, purpose, setPurpose, exportPortfolio }) {
  const editable = active.status === "ACTIVE";
  return <div className="portfolio-workspace">
    <header><div><h4>{active.name}</h4><p>{active.description}</p></div>{editable && <button type="button" className="secondary-button" onClick={archivePortfolio}><Archive size={16} /> Arquivar</button>}</header>
    {editable && <div className="portfolio-add-scenario"><label>Adicionar cenário<select value={scenarioToAdd} onChange={(event) => setScenarioToAdd(event.target.value)}><option value="">Selecione</option>{availableScenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label><button type="button" className="secondary-button" disabled={!scenarioToAdd} onClick={addScenario}>Adicionar</button></div>}
    <div className="electoral-table-wrapper"><table className="electoral-table"><thead><tr><th>Cenário</th><th>Total projetado</th><th>Faixa</th><th>Função</th><th>Ações</th></tr></thead><tbody>{active.scenarios.map((scenario) => <tr key={scenario.id}><td>{scenario.name}</td><td>{scenario.projected_total_votes.toLocaleString("pt-BR")}</td><td>{scenario.uncertainty_interval.lower_votes.toLocaleString("pt-BR")}–{scenario.uncertainty_interval.upper_votes.toLocaleString("pt-BR")}</td><td>{scenario.is_reference ? <strong><Star size={15} /> Referência</strong> : "Alternativa"}</td><td>{editable && <><button type="button" className="secondary-button" disabled={scenario.is_reference} onClick={() => setReference(scenario.id)}>Definir referência</button><button type="button" className="danger-button" onClick={() => removeScenario(scenario.id)}><Trash2 size={15} /> Remover</button></>}</td></tr>)}</tbody></table></div>
    <h4><Flag size={17} /> Metas hipotéticas</h4>
    {editable && <form className="scenario-editor" onSubmit={addGoal}>
      <label>Escopo<select value={goal.scope} onChange={(event) => setGoal({ ...goal, scope: event.target.value })}><option value="TOTAL">Total agregado</option><option value="TERRITORY">Território</option></select></label>
      {goal.scope === "TERRITORY" && <label>Território<select value={goal.territoryId} onChange={(event) => setGoal({ ...goal, territoryId: event.target.value })}><option value="">Selecione</option>{territoryOptions.map((item) => <option key={item.territory_id} value={item.territory_id}>{item.territory_name}</option>)}</select></label>}
      <label>Métrica<select value={goal.metric} onChange={(event) => setGoal({ ...goal, metric: event.target.value })}><option value="VOTES">Votos</option><option value="SHARE">Participação (%)</option></select></label>
      <label>Valor da meta<input type="number" min="0" step="0.01" value={goal.target} onChange={(event) => setGoal({ ...goal, target: event.target.value })} /></label>
      <label>Justificativa<input maxLength={500} value={goal.rationale} onChange={(event) => setGoal({ ...goal, rationale: event.target.value })} /></label>
      <button className="primary-button" disabled={!goal.target || !goal.rationale.trim() || goal.scope === "TERRITORY" && !goal.territoryId}>Adicionar meta</button>
    </form>}
    <div className="portfolio-goal-list">{active.goals.map((item) => <article key={item.id}><strong>{goalLabel(item, territoryOptions)}</strong><span>Meta: {formatGoal(item)}</span><p>{item.rationale}</p>{editable && <button type="button" className="danger-button" onClick={() => removeGoal(item.id)}>Remover</button>}</article>)}</div>
    {active.evaluation?.scenarios?.length > 0 && <><h4>Avaliação das metas</h4><div className="electoral-table-wrapper"><table className="electoral-table"><thead><tr><th>Cenário</th><th>Meta</th><th>Valor</th><th>Diferença</th><th>Atingimento</th></tr></thead><tbody>{active.evaluation.scenarios.flatMap((scenario) => scenario.goals.map((item) => <tr key={`${scenario.scenario_id}-${item.id}`}><td>{scenario.name}{scenario.is_reference ? " · referência" : ""}</td><td>{formatGoal(item)}</td><td>{formatActual(item)}</td><td>{formatDifference(item)}</td><td>{item.attainment_percent == null ? "—" : `${item.attainment_percent.toLocaleString("pt-BR")}%`}</td></tr>))}</tbody></table></div></>}
    <div className="portfolio-actions"><button type="button" className="secondary-button" onClick={loadHistory}><History size={16} /> Ver histórico</button><label>Finalidade da exportação<input value={purpose} minLength={10} maxLength={500} onChange={(event) => setPurpose(event.target.value)} /></label><button type="button" className="secondary-button" disabled={purpose.trim().length < 10} onClick={exportPortfolio}><Download size={16} /> Exportar CSV</button></div>
    {history.length > 0 && <ol className="portfolio-history">{history.map((event) => <li key={event.id}><strong>{event.event_type}</strong><span>{new Date(event.created_at).toLocaleString("pt-BR")}</span></li>)}</ol>}
  </div>;
}

function goalLabel(goal, territories) { return goal.scope === "TOTAL" ? "Total agregado" : territories.find((item) => item.territory_id === goal.territory_id)?.territory_name || goal.territory_id; }
function formatGoal(goal) { return goal.metric === "SHARE" ? `${(goal.target_value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%` : `${goal.target_value.toLocaleString("pt-BR")} votos`; }
function formatActual(goal) { return goal.metric === "SHARE" ? `${(goal.actual_value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%` : goal.actual_value.toLocaleString("pt-BR"); }
function formatDifference(goal) { const value = goal.metric === "SHARE" ? goal.difference * 100 : goal.difference; return `${value >= 0 ? "+" : ""}${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}${goal.metric === "SHARE" ? " p.p." : ""}`; }
