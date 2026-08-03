import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../api";

const isoDate = (date) => date.toISOString().slice(0, 10);

export function MandateIntelligencePanel({ electionId, selectedCandidate, onError }) {
  const today = useMemo(() => new Date(), []);
  const initialStart = useMemo(() => {
    const value = new Date(today);
    value.setDate(value.getDate() - 89);
    return value;
  }, [today]);
  const [periodStart, setPeriodStart] = useState(isoDate(initialStart));
  const [periodEnd, setPeriodEnd] = useState(isoDate(today));
  const [profile, setProfile] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      apiRequest("/api/v1/electoral/coverage-profile"),
      apiRequest("/api/v1/electoral/mandate-snapshots"),
    ]).then(([profileResponse, snapshotResponse]) => {
      setProfile(profileResponse);
      setSnapshots(snapshotResponse.content || []);
      setSelected(snapshotResponse.content?.[0] || null);
    }).catch((error) => onError(error.message));
  }, [onError]);

  async function createSnapshot(event) {
    event.preventDefault();
    setLoading(true);
    try {
      const body = { period_start: periodStart, period_end: periodEnd };
      if (electionId && selectedCandidate?.id) {
        body.election_id = electionId;
        body.candidate_id = selectedCandidate.id;
      }
      const created = await apiRequest("/api/v1/electoral/mandate-snapshots", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSnapshots((current) => [created, ...current]);
      setSelected(created);
    } catch (error) {
      onError(error.message);
    } finally {
      setLoading(false);
    }
  }

  const mandateRow = selected?.payload?.territories?.find((item) => item.scope === "mandate");
  const territoryRows = selected?.payload?.territories?.filter((item) => item.scope === "territory") || [];

  return (
    <section className="electoral-analysis-card" aria-labelledby="mandate-intelligence-title">
      <header>
        <div><h2 id="mandate-intelligence-title">Inteligência integrada do mandato</h2><p>Demandas, SLA, agenda, ações e entregas em recortes agregados e protegidos.</p></div>
        {profile && <span className="electoral-job-status">ICT {profile.formula_code} · perfil v{profile.version}</span>}
      </header>
      <p className="electoral-warning">O resultado eleitoral é contexto público. Ele não compõe o ICT e não pode orientar prioridade de atendimento.</p>
      <form className="electoral-snapshot-form" onSubmit={createSnapshot}>
        <label>Início<input aria-label="Início do período" type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required /></label>
        <label>Fim<input aria-label="Fim do período" type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required /></label>
        <button className="primary-button" type="submit" disabled={loading}>{loading ? "Gerando..." : "Gerar snapshot"}</button>
        <label>Snapshot<select aria-label="Snapshot territorial" value={selected?.id || ""} onChange={(event) => setSelected(snapshots.find((item) => item.id === event.target.value) || null)}><option value="">Nenhum snapshot</option>{snapshots.map((item) => <option key={item.id} value={item.id}>{item.period_start} a {item.period_end}</option>)}</select></label>
      </form>
      {selected && <>
        <div className="electoral-provenance"><span>Corte: {new Date(selected.source_cutoff_at).toLocaleString("pt-BR")}</span><span>Limiar: {selected.privacy_threshold} demandas</span><span>Configuração: {selected.config_hash.slice(0, 12)}</span></div>
        {selected.electoral_context?.available && <div className="electoral-context-card"><strong>{selected.electoral_context.candidate_name} · {selected.electoral_context.party}</strong><span>{selected.electoral_context.votes.toLocaleString("pt-BR")} votos em {selected.electoral_context.year}</span><small>{selected.electoral_context.warning}</small></div>}
        {mandateRow?.suppressed ? <p className="electoral-empty">Indicadores do mandato suprimidos pelo limiar de privacidade.</p> : mandateRow && <div className="electoral-result-summary" aria-label="Resumo agregado do mandato">
          <div><span>ICT</span><strong>{mandateRow.ict.score}</strong></div><div><span>Demandas</span><strong>{mandateRow.demand_count}</strong></div><div><span>Resolvidas</span><strong>{mandateRow.metrics.resolved}</strong></div><div><span>SLA cumprido</span><strong>{mandateRow.metrics.sla_rate == null ? "N/A" : `${Math.round(mandateRow.metrics.sla_rate * 100)}%`}</strong></div><div><span>Agendas realizadas</span><strong>{mandateRow.metrics.agenda_realized}</strong></div><div><span>Entregas com evidência</span><strong>{mandateRow.metrics.deliveries_with_evidence}</strong></div>
        </div>}
        {!!mandateRow?.alerts?.length && <ul className="electoral-alert-list">{mandateRow.alerts.map((alert) => <li key={alert}>{alert}</li>)}</ul>}
        {!!territoryRows.length && <div className="electoral-table-wrap"><table><caption>Briefing territorial agregado; células protegidas não permitem detalhamento individual.</caption><thead><tr><th>Território</th><th>Demandas</th><th>ICT</th><th>SLA</th><th>Agenda</th><th>Ações</th><th>Entregas</th></tr></thead><tbody>{territoryRows.map((row) => <tr key={row.territory_id}><td><strong>{row.territory_name}</strong>{row.suppressed && <small>Protegido pelo limiar</small>}</td>{row.suppressed ? <td colSpan="6">Dados suprimidos</td> : <><td>{row.demand_count}</td><td>{row.ict.score}</td><td>{row.metrics.sla_rate == null ? "N/A" : `${Math.round(row.metrics.sla_rate * 100)}%`}</td><td>{row.metrics.agenda_realized}</td><td>{row.metrics.oversight_completed}</td><td>{row.metrics.deliveries_with_evidence}</td></>}</tr>)}</tbody></table></div>}
      </>}
    </section>
  );
}
