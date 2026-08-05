import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api";
import { OperationalCommitmentMap } from "./OperationalCommitmentMap";

const statusLabels = { PLANNED: "Planejado", IN_PROGRESS: "Em andamento", COMPLETED: "Concluído", CANCELLED: "Cancelado", OVERDUE: "Prazo vencido" };

function initialDueDate() {
  const date = new Date(); date.setDate(date.getDate() + 30);
  return date.toISOString().slice(0, 10);
}

export function PublicCommitmentsPanel({ onError }) {
  const [data, setData] = useState(null);
  const [map, setMap] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ title: "", description: "", territory_id: "", responsible_user_id: "", due_on: initialDueDate(), public_location_name: "", latitude: "", longitude: "", location_is_public: false });
  const [evidence, setEvidence] = useState({ title: "", public_url: "", evidence_date: new Date().toISOString().slice(0, 10) });
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async (preferredId) => {
    const [commitments, mapResponse] = await Promise.all([apiRequest("/api/v1/electoral/public-commitments"), apiRequest("/api/v1/electoral/operational-map")]);
    setData(commitments); setMap(mapResponse);
    if (preferredId) setSelected(commitments.content.find((item) => item.id === preferredId) || null);
  }, []);

  useEffect(() => { reload().catch((error) => onError(error.message)); }, [onError, reload]);

  function change(name, value) { setForm((current) => ({ ...current, [name]: value })); }

  async function create(event) {
    event.preventDefault(); setSaving(true);
    try {
      const payload = { ...form };
      if (!payload.latitude && !payload.longitude) { delete payload.latitude; delete payload.longitude; delete payload.location_is_public; }
      const created = await apiRequest("/api/v1/electoral/public-commitments", { method: "POST", body: JSON.stringify(payload) });
      setForm((current) => ({ ...current, title: "", description: "", public_location_name: "", latitude: "", longitude: "", location_is_public: false }));
      await reload(created.id); setSelected(created);
    } catch (error) { onError(error.message); } finally { setSaving(false); }
  }

  async function update(item, changes) {
    try {
      const updated = await apiRequest(`/api/v1/electoral/public-commitments/${item.id}`, { method: "PATCH", body: JSON.stringify(changes) });
      await reload(updated.id); setSelected(updated);
    } catch (error) { onError(error.message); }
  }

  async function addEvidence(event) {
    event.preventDefault();
    try {
      const updated = await apiRequest(`/api/v1/electoral/public-commitments/${selected.id}/evidence`, { method: "POST", body: JSON.stringify(evidence) });
      setEvidence((current) => ({ ...current, title: "", public_url: "" }));
      await reload(updated.id); setSelected(updated);
    } catch (error) { onError(error.message); }
  }

  async function selectCommitment(id) {
    try { setSelected(await apiRequest(`/api/v1/electoral/public-commitments/${id}`)); }
    catch (error) { onError(error.message); }
  }

  if (!data) return <section className="electoral-analysis-card"><p aria-live="polite">Carregando compromissos públicos...</p></section>;
  return <section className="electoral-analysis-card" aria-labelledby="public-commitments-title">
    <header><div><h2 id="public-commitments-title">Compromissos públicos territoriais</h2><p>Responsável, prazo, progresso e evidências públicas com histórico imutável.</p></div></header>
    {data.can_manage && <form className="electoral-commitment-form" onSubmit={create}>
      <label>Título<input value={form.title} onChange={(event) => change("title", event.target.value)} maxLength="180" required /></label>
      <label>Território<select value={form.territory_id} onChange={(event) => change("territory_id", event.target.value)} required><option value="">Selecione</option>{data.territories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Responsável<select value={form.responsible_user_id} onChange={(event) => change("responsible_user_id", event.target.value)} required><option value="">Selecione</option>{data.responsible_users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Prazo<input type="date" value={form.due_on} onChange={(event) => change("due_on", event.target.value)} required /></label>
      <label className="commitment-description">Descrição<textarea value={form.description} onChange={(event) => change("description", event.target.value)} required /></label>
      <fieldset><legend>Local público opcional para o mapa</legend><label>Nome do local<input value={form.public_location_name} onChange={(event) => change("public_location_name", event.target.value)} /></label><label>Latitude<input type="number" step="any" value={form.latitude} onChange={(event) => change("latitude", event.target.value)} /></label><label>Longitude<input type="number" step="any" value={form.longitude} onChange={(event) => change("longitude", event.target.value)} /></label><label className="commitment-public-check"><input type="checkbox" checked={form.location_is_public} onChange={(event) => change("location_is_public", event.target.checked)} /> Confirmo que não é endereço residencial</label></fieldset>
      <button className="primary-button" type="submit" disabled={saving}>{saving ? "Salvando..." : "Cadastrar compromisso"}</button>
    </form>}
    <div className="electoral-commitment-layout">
      <div className="electoral-commitment-list"><h3>Progresso por território</h3>{!data.content.length && <p className="electoral-empty">Nenhum compromisso cadastrado.</p>}{data.content.map((item) => <article key={item.id} className={selected?.id === item.id ? "commitment-row selected" : "commitment-row"} onClick={() => selectCommitment(item.id)}><div><strong>{item.title}</strong><span>{item.territory.name} · {item.responsible.name}</span><small>Prazo {new Date(`${item.due_on}T12:00:00`).toLocaleDateString("pt-BR")}</small></div><div><span className={`electoral-job-status status-${item.effective_status.toLowerCase()}`}>{statusLabels[item.effective_status]}</span><strong>{item.progress}%</strong></div>{data.can_manage && <div className="commitment-actions">{item.status === "PLANNED" && <button type="button" onClick={(event) => { event.stopPropagation(); update(item, { status: "IN_PROGRESS", progress: 10 }); }}>Iniciar</button>}{!(["COMPLETED", "CANCELLED"].includes(item.status)) && <button type="button" onClick={(event) => { event.stopPropagation(); update(item, { status: "COMPLETED" }); }}>Concluir</button>}</div>}</article>)}</div>
      <OperationalCommitmentMap response={map} selectedId={selected?.id} onSelect={selectCommitment} />
    </div>
    {selected && <aside className="commitment-detail"><h3>{selected.title}</h3><p>{selected.description}</p><p><strong>Evidências:</strong> {selected.evidence.length}</p><ul>{selected.evidence.map((item) => <li key={item.id}><a href={item.public_url} target="_blank" rel="noreferrer">{item.title}</a> · {item.evidence_date}</li>)}</ul>{data.can_manage && <form className="commitment-evidence-form" onSubmit={addEvidence}><label>Título da evidência<input value={evidence.title} onChange={(event) => setEvidence((current) => ({ ...current, title: event.target.value }))} required /></label><label>URL pública<input type="url" value={evidence.public_url} onChange={(event) => setEvidence((current) => ({ ...current, public_url: event.target.value }))} required /></label><label>Data<input type="date" value={evidence.evidence_date} onChange={(event) => setEvidence((current) => ({ ...current, evidence_date: event.target.value }))} required /></label><button className="secondary-button" type="submit">Adicionar evidência</button></form>} {selected.history && <details><summary>Histórico imutável ({selected.history.length})</summary><ol>{selected.history.map((item) => <li key={item.id}>{item.action} · {new Date(item.created_at).toLocaleString("pt-BR")}</li>)}</ol></details>}</aside>}
  </section>;
}
