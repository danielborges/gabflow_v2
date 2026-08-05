import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../api";
import { ElectoralAdvancedTools } from "./ElectoralAdvancedTools";

const isoDate = (date) => date.toISOString().slice(0, 10);
const alertTypeLabels = {
  SLA_DEGRADED: "SLA degradado",
  SLA_OVERDUE: "Demandas com SLA vencido",
  AGENDA_GAP: "Ausência de agenda",
  OVERSIGHT_GAP: "Ausência de fiscalização",
  COMMITMENT_OVERDUE: "Compromissos vencidos",
};

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
  const [profileDraft, setProfileDraft] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [selected, setSelected] = useState(null);
  const [briefing, setBriefing] = useState(null);
  const [alertPreference, setAlertPreference] = useState(null);
  const [alertFeed, setAlertFeed] = useState([]);
  const [alertDeliveries, setAlertDeliveries] = useState([]);
  const [territoryLinks, setTerritoryLinks] = useState({ content: [], operational_territories: [], electoral_territories: [] });
  const [linkDraft, setLinkDraft] = useState({ territory_id: "", electoral_territory_id: "", notes: "" });
  const [loading, setLoading] = useState(false);
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    Promise.all([
      apiRequest("/api/v1/electoral/coverage-profile"),
      apiRequest("/api/v1/electoral/mandate-snapshots"),
      apiRequest("/api/v1/electoral/alert-preferences"),
      apiRequest("/api/v1/electoral/alerts"),
      apiRequest("/api/v1/electoral/alert-deliveries"),
    ]).then(([profileResponse, snapshotResponse, preferenceResponse, alertResponse, deliveryResponse]) => {
      setProfile(profileResponse);
      setProfileDraft(profileResponse);
      setSnapshots(snapshotResponse.content || []);
      setSelected(snapshotResponse.content?.[0] || null);
      setAlertPreference(preferenceResponse);
      setAlertFeed(alertResponse.content || []);
      setAlertDeliveries(deliveryResponse?.content || []);
    }).catch((error) => onError(error.message));
  }, [onError]);

  useEffect(() => {
    if (!electionId) {
      setTerritoryLinks({ content: [], operational_territories: [], electoral_territories: [] });
      return;
    }
    apiRequest(`/api/v1/electoral/territory-links?election_id=${electionId}`)
      .then((response) => setTerritoryLinks({
        content: [], operational_territories: [], electoral_territories: [],
        ...(response || {}),
      }))
      .catch((error) => onError(error.message));
  }, [electionId, onError]);

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
      setBriefing(null);
      const deliveries = await apiRequest("/api/v1/electoral/alert-deliveries");
      setAlertDeliveries(deliveries.content || []);
    } catch (error) {
      onError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadBriefing(territoryId) {
    if (!selected) return;
    try {
      const params = new URLSearchParams({ snapshot_id: selected.id });
      setBriefing(await apiRequest(
        `/api/v1/electoral/territories/${territoryId}/briefing?${params}`,
      ));
    } catch (error) {
      onError(error.message);
    }
  }

  function toggleAlertChannel(channel) {
    setAlertPreference((current) => {
      const channels = current?.channels || ["IN_APP"];
      return {
        ...current,
        channels: channels.includes(channel)
          ? channels.filter((item) => item !== channel)
          : [...channels, channel],
      };
    });
  }

  function toggleAlertType(type) {
    setAlertPreference((current) => {
      const types = current?.alert_types || [];
      return {
        ...current,
        alert_types: types.includes(type)
          ? types.filter((item) => item !== type)
          : [...types, type],
      };
    });
  }

  async function saveAlertPreferences(event) {
    event.preventDefault();
    setSavingAlerts(true);
    try {
      const updated = await apiRequest("/api/v1/electoral/alert-preferences", {
        method: "PUT",
        body: JSON.stringify({
          enabled: alertPreference?.enabled ?? true,
          channels: alertPreference?.channels || ["IN_APP"],
          frequency: alertPreference?.frequency || "DAILY",
          alert_types: alertPreference?.alert_types || [],
        }),
      });
      setAlertPreference(updated);
      const alerts = await apiRequest("/api/v1/electoral/alerts");
      setAlertFeed(alerts.content || []);
    } catch (error) {
      onError(error.message);
    } finally {
      setSavingAlerts(false);
    }
  }

  function updateProfileGroup(group, key, value) {
    setProfileDraft((current) => ({
      ...current,
      [group]: { ...(current?.[group] || {}), [key]: Number(value) },
    }));
  }

  async function saveProfile(event) {
    event.preventDefault();
    setSavingProfile(true);
    try {
      const updated = await apiRequest("/api/v1/electoral/coverage-profile", {
        method: "POST",
        body: JSON.stringify({
          weights: profileDraft.weights,
          targets: profileDraft.targets,
          sensitive_categories: profileDraft.sensitive_categories,
          explanation: profileDraft.explanation,
        }),
      });
      setProfile(updated);
      setProfileDraft(updated);
    } catch (error) {
      onError(error.message);
    } finally {
      setSavingProfile(false);
    }
  }

  async function saveTerritoryLink(event) {
    event.preventDefault();
    try {
      const created = await apiRequest("/api/v1/electoral/territory-links", {
        method: "POST",
        body: JSON.stringify({ ...linkDraft, election_id: electionId }),
      });
      setTerritoryLinks((current) => ({ ...current, content: [
        ...current.content.filter((item) => item.id !== created.id), created,
      ] }));
      setLinkDraft({ territory_id: "", electoral_territory_id: "", notes: "" });
    } catch (error) {
      onError(error.message);
    }
  }

  async function removeTerritoryLink(linkId) {
    try {
      await apiRequest(`/api/v1/electoral/territory-links/${linkId}`, { method: "DELETE" });
      setTerritoryLinks((current) => ({ ...current, content: current.content.filter((item) => item.id !== linkId) }));
    } catch (error) {
      onError(error.message);
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
      {profileDraft && <details className="electoral-config-section">
        <summary>Configurar perfil do ICT <span>versão {profile?.version}</span></summary>
        <form className="electoral-profile-form" onSubmit={saveProfile}>
          <p>Os cinco pesos devem somar 100%. Uma nova versão preservará os snapshots anteriores.</p>
          <fieldset><legend>Pesos do índice</legend>{Object.entries(profileDraft.weights || {}).map(([key, value]) => <label key={key}>{key}<input aria-label={`Peso ${key}`} type="number" min="0" max="1" step="0.01" value={value} onChange={(event) => updateProfileGroup("weights", key, event.target.value)} /></label>)}</fieldset>
          <fieldset><legend>Metas do período</legend>{Object.entries(profileDraft.targets || {}).map(([key, value]) => <label key={key}>{key}<input aria-label={`Meta ${key}`} type="number" min="1" step="1" value={value} onChange={(event) => updateProfileGroup("targets", key, event.target.value)} /></label>)}</fieldset>
          <label className="full-field">Justificativa da nova versão<textarea aria-label="Justificativa do perfil ICT" minLength="20" maxLength="500" value={profileDraft.explanation || ""} onChange={(event) => setProfileDraft((current) => ({ ...current, explanation: event.target.value }))} required /></label>
          <button type="submit" className="secondary-button" disabled={savingProfile}>{savingProfile ? "Salvando..." : "Salvar nova versão"}</button>
        </form>
      </details>}
      {electionId && <details className="electoral-config-section">
        <summary>Vínculos territoriais revisados <span>{territoryLinks.content.length}</span></summary>
        <p>Associe áreas operacionais a municípios ou zonas eleitorais. O resultado será apenas uma camada contextual, fora do cálculo do ICT.</p>
        <form className="electoral-territory-link-form" onSubmit={saveTerritoryLink}>
          <label>Território do gabinete<select aria-label="Território do gabinete" value={linkDraft.territory_id} onChange={(event) => setLinkDraft((current) => ({ ...current, territory_id: event.target.value }))} required><option value="">Selecione</option>{territoryLinks.operational_territories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Unidade eleitoral<select aria-label="Unidade eleitoral" value={linkDraft.electoral_territory_id} onChange={(event) => setLinkDraft((current) => ({ ...current, electoral_territory_id: event.target.value }))} required><option value="">Selecione</option>{territoryLinks.electoral_territories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label>Nota de revisão<input aria-label="Nota de revisão territorial" value={linkDraft.notes} onChange={(event) => setLinkDraft((current) => ({ ...current, notes: event.target.value }))} placeholder="Critério utilizado no vínculo" /></label>
          <button type="submit" className="secondary-button">Adicionar vínculo</button>
        </form>
        {!!territoryLinks.content.length && <ul className="electoral-link-list">{territoryLinks.content.map((item) => <li key={item.id}><span><strong>{item.territory_name}</strong> → {item.electoral_territory?.label}</span><button type="button" className="table-link-button" onClick={() => removeTerritoryLink(item.id)}>Remover</button></li>)}</ul>}
      </details>}
      {alertPreference && <form className="electoral-alert-preferences" onSubmit={saveAlertPreferences}>
        <div><strong>Alertas territoriais</strong><small>{alertFeed.length} alerta(s) no snapshot mais recente</small></div>
        <label><input type="checkbox" checked={alertPreference.enabled ?? true} onChange={(event) => setAlertPreference((current) => ({ ...current, enabled: event.target.checked }))} />Ativos</label>
        <label><input type="checkbox" checked={(alertPreference.channels || []).includes("IN_APP")} onChange={() => toggleAlertChannel("IN_APP")} />No GabFlow</label>
        <label><input type="checkbox" checked={(alertPreference.channels || []).includes("EMAIL")} onChange={() => toggleAlertChannel("EMAIL")} />E-mail</label>
        <label>Frequência<select aria-label="Frequência dos alertas" value={alertPreference.frequency || "DAILY"} onChange={(event) => setAlertPreference((current) => ({ ...current, frequency: event.target.value }))}><option value="IMMEDIATE">Imediata</option><option value="DAILY">Diária</option><option value="WEEKLY">Semanal</option></select></label>
        <fieldset><legend>Tipos de alerta</legend>{(alertPreference.available_alert_types || Object.keys(alertTypeLabels)).map((type) => <label key={type}><input type="checkbox" checked={(alertPreference.alert_types || []).includes(type)} onChange={() => toggleAlertType(type)} />{alertTypeLabels[type] || type}</label>)}</fieldset>
        <button type="submit" className="secondary-button" disabled={savingAlerts || !(alertPreference.channels || []).length || !(alertPreference.alert_types || []).length}>{savingAlerts ? "Salvando..." : "Salvar alertas"}</button>
      </form>}
      {!!alertDeliveries.length && <details className="electoral-config-section"><summary>Histórico de entregas <span>{alertDeliveries.length}</span></summary><ul className="electoral-link-list">{alertDeliveries.map((item) => <li key={item.id}><span><strong>{alertTypeLabels[item.alert_type] || item.alert_type}</strong> · {item.payload?.territory_name || "Mandato"}<small>{item.channel === "EMAIL" ? "E-mail" : "GabFlow"} · {item.status}</small></span><time>{new Date(item.created_at).toLocaleString("pt-BR")}</time></li>)}</ul></details>}
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
          <div><span>ICT</span><strong>{mandateRow.ict.score}</strong></div><div><span>Demandas</span><strong>{mandateRow.demand_count}</strong></div><div><span>Resolvidas</span><strong>{mandateRow.metrics.resolved}</strong></div><div><span>SLA cumprido</span><strong>{mandateRow.metrics.sla_rate == null ? "N/A" : `${Math.round(mandateRow.metrics.sla_rate * 100)}%`}</strong></div><div><span>Agendas realizadas</span><strong>{mandateRow.metrics.agenda_realized}</strong></div><div><span>Entregas com evidência</span><strong>{mandateRow.metrics.deliveries_with_evidence}</strong></div><div><span>Compromissos públicos</span><strong>{mandateRow.public_commitments?.total || 0}</strong></div><div><span>Compromissos vencidos</span><strong>{mandateRow.public_commitments?.overdue || 0}</strong></div>
        </div>}
        {!!mandateRow?.alerts?.length && <ul className="electoral-alert-list">{mandateRow.alerts.map((alert) => <li key={alert}>{alert}</li>)}</ul>}
        {!!territoryRows.some((row) => row.electoral_overlay) && <div className="electoral-context-card"><strong>Resultado eleitoral por vínculo revisado</strong>{territoryRows.filter((row) => row.electoral_overlay).map((row) => <span key={row.territory_id}>{row.territory_name}: {row.electoral_overlay.votes.toLocaleString("pt-BR")} votos</span>)}<small>Camada contextual separada; estes votos não integram o ICT.</small></div>}
        {!!territoryRows.length && <div className="electoral-table-wrap"><table className="mandate-territory-table"><caption>Briefing territorial agregado; células protegidas não permitem detalhamento individual.</caption><thead><tr><th>Território</th><th>Demandas</th><th>ICT</th><th>SLA</th><th>Agenda</th><th>Ações</th><th>Entregas</th><th>Compromissos</th><th>Vencidos</th></tr></thead><tbody>{territoryRows.map((row) => <tr key={row.territory_id}><td><strong>{row.territory_name}</strong>{row.suppressed && <small>Protegido pelo limiar</small>}<button type="button" className="table-link-button" onClick={() => loadBriefing(row.territory_id)}>Abrir briefing</button></td>{row.suppressed ? <><td colSpan="6">Dados de atendimento suprimidos</td><td>{row.public_commitments?.total || 0}</td><td>{row.public_commitments?.overdue || 0}</td></> : <><td>{row.demand_count}</td><td>{row.ict.score}</td><td>{row.metrics.sla_rate == null ? "N/A" : `${Math.round(row.metrics.sla_rate * 100)}%`}</td><td>{row.metrics.agenda_realized}</td><td>{row.metrics.oversight_completed}</td><td>{row.metrics.deliveries_with_evidence}</td><td>{row.public_commitments?.total || 0}</td><td>{row.public_commitments?.overdue || 0}</td></>}</tr>)}</tbody></table></div>}
        {briefing && <article className="electoral-briefing" aria-labelledby="territory-briefing-title">
          <header><div><p className="eyebrow">Rascunho para revisão</p><h3 id="territory-briefing-title">{briefing.title}</h3></div><span className="electoral-job-status">Dados agregados</span></header>
          {briefing.privacy?.suppressed ? <p className="electoral-empty">Indicadores protegidos pelo limiar de privacidade.</p> : <dl>{briefing.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value == null ? "N/A" : fact.label === "SLA cumprido" ? `${Math.round(fact.value * 100)}%` : fact.value}</dd></div>)}</dl>}
          {!!briefing.alerts?.length && <ul className="electoral-alert-list">{briefing.alerts.map((alert) => <li key={`${alert.type}-${alert.message}`}>{alert.message}</li>)}</ul>}
          <p className="electoral-warning">{briefing.methodology_notice}</p>
        </article>}
      </>}
      <ElectoralAdvancedTools electionId={electionId} snapshotId={selected?.id} onError={onError} />
    </section>
  );
}
