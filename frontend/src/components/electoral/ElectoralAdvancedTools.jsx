import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../api";

const indicatorLabels = {
  votes: "Votos", share: "Participação", rank: "Posição", variation: "Variação",
  ict: "ICT", sla: "SLA", demands: "Demandas",
};

export function ElectoralAdvancedTools({ electionId, snapshotId, onError }) {
  const [preferences, setPreferences] = useState(null);
  const [segments, setSegments] = useState({ content: [], available_territories: [] });
  const [segmentDraft, setSegmentDraft] = useState({ name: "", description: "", territory_ids: [] });
  const [layers, setLayers] = useState(null);
  const [agenda, setAgenda] = useState({ stops: [] });
  const [briefing, setBriefing] = useState(null);
  const [reportJobs, setReportJobs] = useState([]);
  const [schedules, setSchedules] = useState({ content: [], available_recipients: [] });
  const [scheduleDraft, setScheduleDraft] = useState({ name: "", frequency: "WEEKLY", template_report_job_id: "", recipient_ids: [], next_run_at: "" });

  const range = useMemo(() => {
    const from = new Date();
    const to = new Date(from);
    to.setDate(to.getDate() + 7);
    return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
  }, []);

  useEffect(() => {
    apiRequest("/api/v1/electoral/preferences").then((response) => setPreferences({
      territory_level: "municipality", indicators: ["votes", "share", "rank"],
      available_indicators: Object.keys(indicatorLabels),
      available_territory_levels: ["municipality", "electoral_zone"],
      ...(response || {}),
    })).catch((error) => onError(error.message));
    apiRequest(`/api/v1/electoral/agenda-routes?from=${range.from}&to=${range.to}`)
      .then((response) => setAgenda({
        ...(response || {}),
        stops: Array.isArray(response?.stops) ? response.stops : [],
      }))
      .catch(() => {});
    apiRequest("/api/v1/electoral/report-jobs").then((response) => setReportJobs(response.content || [])).catch(() => {});
    apiRequest("/api/v1/electoral/report-schedules").then((response) => setSchedules({
      content: [], available_recipients: [], ...(response || {}),
    })).catch(() => {});
  }, [onError, range]);

  useEffect(() => {
    if (!electionId) return;
    apiRequest(`/api/v1/electoral/territory-segments?election_id=${electionId}`)
      .then((response) => setSegments({ content: [], available_territories: [], ...(response || {}) }))
      .catch((error) => onError(error.message));
  }, [electionId, onError]);

  useEffect(() => {
    if (!snapshotId) return;
    apiRequest(`/api/v1/electoral/mandate-map-layers?snapshot_id=${snapshotId}`)
      .then((response) => {
        if (Array.isArray(response?.heatmap) && Array.isArray(response?.clusters)) setLayers(response);
      }).catch((error) => onError(error.message));
  }, [snapshotId, onError]);

  function toggleValue(setter, key, value) {
    setter((current) => ({ ...current, [key]: current[key].includes(value)
      ? current[key].filter((item) => item !== value) : [...current[key], value] }));
  }

  async function savePreferences(event) {
    event.preventDefault();
    try {
      setPreferences(await apiRequest("/api/v1/electoral/preferences", {
        method: "PUT", body: JSON.stringify({ ...preferences, election_id: electionId || preferences.election_id }),
      }));
    } catch (error) { onError(error.message); }
  }

  async function createSegment(event) {
    event.preventDefault();
    try {
      const created = await apiRequest("/api/v1/electoral/territory-segments", {
        method: "POST", body: JSON.stringify({ ...segmentDraft, election_id: electionId }),
      });
      setSegments((current) => ({ ...current, content: [...current.content, created] }));
      setSegmentDraft({ name: "", description: "", territory_ids: [] });
    } catch (error) { onError(error.message); }
  }

  async function deleteSegment(id) {
    try {
      await apiRequest(`/api/v1/electoral/territory-segments/${id}`, { method: "DELETE" });
      setSegments((current) => ({ ...current, content: current.content.filter((item) => item.id !== id) }));
    } catch (error) { onError(error.message); }
  }

  async function loadPreVisit(eventId) {
    try {
      setBriefing(await apiRequest(`/api/v1/electoral/agenda-events/${eventId}/pre-visit-briefing?snapshot_id=${snapshotId}`));
    } catch (error) { onError(error.message); }
  }

  async function createSchedule(event) {
    event.preventDefault();
    try {
      const created = await apiRequest("/api/v1/electoral/report-schedules", {
        method: "POST", body: JSON.stringify(scheduleDraft),
      });
      setSchedules((current) => ({ ...current, content: [created, ...current.content] }));
    } catch (error) { onError(error.message); }
  }

  return <div className="electoral-advanced-tools">
    {preferences && <details className="electoral-config-section">
      <summary>Preferências individuais de análise</summary>
      <form className="electoral-profile-form" onSubmit={savePreferences}>
        <label>Recorte padrão<select value={preferences.territory_level} onChange={(event) => setPreferences((current) => ({ ...current, territory_level: event.target.value }))}>{preferences.available_territory_levels.map((level) => <option key={level} value={level}>{level}</option>)}</select></label>
        <fieldset><legend>Indicadores padrão</legend>{preferences.available_indicators.map((indicator) => <label key={indicator}><input type="checkbox" checked={preferences.indicators.includes(indicator)} onChange={() => toggleValue(setPreferences, "indicators", indicator)} />{indicatorLabels[indicator] || indicator}</label>)}</fieldset>
        <button className="secondary-button" type="submit">Salvar preferências</button>
      </form>
    </details>}

    {electionId && <details className="electoral-config-section">
      <summary>Segmentos territoriais <span>{segments.content.length}</span></summary>
      <form className="electoral-profile-form" onSubmit={createSegment}>
        <label>Nome<input value={segmentDraft.name} onChange={(event) => setSegmentDraft((current) => ({ ...current, name: event.target.value }))} required minLength="3" /></label>
        <label className="full-field">Descrição<input value={segmentDraft.description} onChange={(event) => setSegmentDraft((current) => ({ ...current, description: event.target.value }))} /></label>
        <fieldset><legend>Unidades agregadas</legend>{segments.available_territories.map((territory) => <label key={territory.id}><input type="checkbox" checked={segmentDraft.territory_ids.includes(territory.id)} onChange={() => toggleValue(setSegmentDraft, "territory_ids", territory.id)} />{territory.name}</label>)}</fieldset>
        <button className="secondary-button" type="submit" disabled={!segmentDraft.territory_ids.length}>Criar segmento</button>
      </form>
      <ul className="electoral-link-list">{segments.content.map((segment) => <li key={segment.id}><span><strong>{segment.name}</strong><small>{segment.territory_ids.length} unidade(s)</small></span><button className="table-link-button" type="button" onClick={() => deleteSegment(segment.id)}>Excluir</button></li>)}</ul>
    </details>}

    {layers && <details className="electoral-config-section" open>
      <summary>Heatmap e clusters territoriais</summary>
      <p>{layers.privacy.rule}</p>
      {layers.heatmap.length ? <div className="electoral-heatmap-grid">{layers.heatmap.map((cell) => <div key={cell.territory_id}><strong>{cell.territory_name}</strong><span style={{ "--heat": Math.min(cell.intensity / 20, 1) }}>{cell.intensity} demandas</span><small>{cell.public_reference_points} ponto(s) público(s)</small></div>)}</div> : <p className="electoral-empty">Não há locais públicos confirmados suficientes para esta camada.</p>}
      {!!layers.clusters.length && <ul className="electoral-link-list">{layers.clusters.map((cluster) => <li key={cluster.id}><span><strong>Cluster {cluster.territories.join(", ")}</strong><small>{cluster.intensity} demandas agregadas</small></span></li>)}</ul>}
    </details>}

    <details className="electoral-config-section">
      <summary>Agenda territorial e briefing pré-visita <span>{agenda.stops.length}</span></summary>
      <p>Rota cronológica com coordenadas derivadas exclusivamente de locais públicos confirmados.</p>
      <ol className="electoral-route-list">{agenda.stops.map((stop) => <li key={stop.agenda_event_id}><span>{stop.sequence}</span><div><strong>{stop.title}</strong><small>{stop.territory_name} · {new Date(stop.starts_at).toLocaleString("pt-BR")}</small></div><button type="button" className="secondary-button" disabled={!snapshotId} onClick={() => loadPreVisit(stop.agenda_event_id)}>Preparar visita</button></li>)}</ol>
      {briefing && <article className="electoral-briefing"><h3>{briefing.title}</h3><p>{briefing.agenda_event.title} · {new Date(briefing.agenda_event.starts_at).toLocaleString("pt-BR")}</p><dl>{briefing.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value ?? "N/A"}</dd></div>)}</dl><small>Rascunho editável sujeito a revisão humana.</small></article>}
    </details>

    {!!reportJobs.length && <details className="electoral-config-section">
      <summary>Relatórios recorrentes <span>{schedules.content.length}</span></summary>
      <form className="electoral-profile-form" onSubmit={createSchedule}>
        <label>Nome<input value={scheduleDraft.name} onChange={(event) => setScheduleDraft((current) => ({ ...current, name: event.target.value }))} required /></label>
        <label>Relatório-base<select value={scheduleDraft.template_report_job_id} onChange={(event) => setScheduleDraft((current) => ({ ...current, template_report_job_id: event.target.value }))} required><option value="">Selecione</option>{reportJobs.map((job) => <option key={job.id} value={job.id}>{job.report_type} · {job.format}</option>)}</select></label>
        <label>Frequência<select value={scheduleDraft.frequency} onChange={(event) => setScheduleDraft((current) => ({ ...current, frequency: event.target.value }))}><option value="DAILY">Diária</option><option value="WEEKLY">Semanal</option><option value="MONTHLY">Mensal</option></select></label>
        <label>Primeira execução<input type="datetime-local" value={scheduleDraft.next_run_at} onChange={(event) => setScheduleDraft((current) => ({ ...current, next_run_at: event.target.value }))} required /></label>
        <fieldset><legend>Destinatários internos</legend>{schedules.available_recipients.map((user) => <label key={user.id}><input type="checkbox" checked={scheduleDraft.recipient_ids.includes(user.id)} onChange={() => toggleValue(setScheduleDraft, "recipient_ids", user.id)} />{user.name}</label>)}</fieldset>
        <button className="secondary-button" type="submit" disabled={!scheduleDraft.recipient_ids.length}>Agendar relatório</button>
      </form>
      <ul className="electoral-link-list">{schedules.content.map((schedule) => <li key={schedule.id}><span><strong>{schedule.name}</strong><small>{schedule.frequency} · próxima {new Date(schedule.next_run_at).toLocaleString("pt-BR")}</small></span></li>)}</ul>
    </details>}
  </div>;
}
