import { CalendarDays, ClipboardPlus, MapPin, Plus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

const emptyForm = {
  tipo: "VISITA",
  titulo: "",
  descricao: "",
  local: "",
  inicio: "",
  participantes: "",
  ata: "",
  pendencias: "",
};

export function AgendaPage() {
  const [events, setEvents] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [jurisdiction, setJurisdiction] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [agendaData, routeData, jurisdictionData] = await Promise.all([
      apiRequest("/api/v1/agenda/compromissos"),
      apiRequest("/api/v1/agenda/roteiros-visita"),
      apiRequest("/api/v1/admin/jurisdicao"),
    ]);
    setEvents(agendaData.content);
    setRoutes(routeData.content);
    setJurisdiction(jurisdictionData);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/agenda/compromissos", {
        method: "POST",
        body: JSON.stringify({
          tipo: form.tipo,
          titulo: form.titulo,
          descricao: form.descricao,
          local: form.local,
          inicio: form.inicio,
          participantes: splitLines(form.participantes),
        }),
      });
      setForm(emptyForm);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function recordVisit() {
    if (!selected) return;
    setError("");
    try {
      const updated = await apiRequest(`/api/v1/agenda/compromissos/${selected.id}/registro`, {
        method: "POST",
        body: JSON.stringify({
          ata: form.ata,
          pendencias: splitLines(form.pendencias),
        }),
      });
      setSelected(updated);
      setForm((current) => ({ ...current, ata: "", pendencias: "" }));
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function createRequestFromVisit() {
    if (!selected) return;
    setError("");
    try {
      await apiRequest(`/api/v1/agenda/compromissos/${selected.id}/solicitacoes`, {
        method: "POST",
        body: JSON.stringify({
          titulo: `Demanda originada de ${selected.titulo}`,
          descricao: selected.ata || selected.descricao,
        }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Atuação externa</p>
          <h1>Agenda</h1>
          <p>Compromissos, visitas, reuniões e audiências vinculados às demandas do gabinete.</p>
        </div>
      </section>
      <section className="admin-layout agenda-layout">
        <form className="settings-form" onSubmit={submit}>
          <div className="settings-title"><CalendarDays size={21} /><div><strong>Novo compromisso</strong><small>Registre a agenda com local e participantes.</small></div></div>
          <div className="form-grid">
            <label>Tipo<select value={form.tipo} onChange={(event) => setForm((current) => ({ ...current, tipo: event.target.value }))}>
              <option value="COMPROMISSO">Compromisso</option>
              <option value="VISITA">Visita</option>
              <option value="REUNIAO">Reunião</option>
              <option value="AUDIENCIA">Audiência</option>
            </select></label>
            <label>Início<input required type="datetime-local" value={form.inicio} onChange={(event) => setForm((current) => ({ ...current, inicio: event.target.value }))} /></label>
          </div>
          <label>Título<input required value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} /></label>
          <label>Descrição<textarea rows="3" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} /></label>
          <label>Local<GooglePlaceAutocompleteInput value={form.local} onChange={(local) => setForm((current) => ({ ...current, local }))} placeholder="Digite um endereço ou ponto de referência" territoryBounds={jurisdiction?.limites} inputProps={{ "aria-label": "Local" }} /></label>
          <label>Participantes<textarea rows="3" value={form.participantes} onChange={(event) => setForm((current) => ({ ...current, participantes: event.target.value }))} /></label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button compact"><Plus size={18} /> Adicionar</button>
        </form>
        <div className="category-list agenda-list">
          {events.map((item) => (
            <button key={item.id} className={selected?.id === item.id ? "entity-row selected" : "entity-row"} onClick={() => setSelected(item)}>
              <span className="entity-icon"><CalendarDays size={19} /></span>
              <div><strong>{item.titulo}</strong><small>{typeLabel(item.tipo)} · {statusLabel(item.status)} · {formatDate(item.inicio)}</small></div>
            </button>
          ))}
        </div>
        <section className="settings-form agenda-detail">
          <div className="settings-title"><MapPin size={21} /><div><strong>Roteiros sugeridos</strong><small>Territórios com maior concentração de demandas abertas.</small></div></div>
          {routes.length ? routes.map((item) => (
            <article key={item.territorioId || item.territorio} className="route-suggestion">
              <strong>{item.territorio}</strong>
              <span>{item.justificativa}</span>
              <small>{item.solicitacoes.map((request) => request.protocolo).join(", ")}</small>
            </article>
          )) : <p className="muted-copy">Sem demandas abertas suficientes para sugerir roteiro.</p>}
        </section>
        {selected && (
          <section className="settings-form agenda-detail">
            <div className="settings-title"><Users size={21} /><div><strong>{selected.titulo}</strong><small>{selected.local || "Sem local informado"}</small></div></div>
            <p className="muted-copy">{selected.descricao || "Sem descrição."}</p>
            <div className="compact-facts">
              <span><MapPin size={15} /> {selected.local || "Local não informado"}</span>
              <span>{selected.participantes?.length || 0} participante(s)</span>
              <span>{selected.pendencias?.length || 0} pendência(s)</span>
            </div>
            <label>Ata ou registro<textarea rows="5" value={form.ata} onChange={(event) => setForm((current) => ({ ...current, ata: event.target.value }))} placeholder={selected.ata || ""} /></label>
            <label>Pendências<textarea rows="3" value={form.pendencias} onChange={(event) => setForm((current) => ({ ...current, pendencias: event.target.value }))} /></label>
            <div className="button-row">
              <button type="button" className="secondary-button compact" onClick={recordVisit}>Registrar visita</button>
              <button type="button" className="primary-button compact" disabled={!selected.ata && !form.ata} onClick={createRequestFromVisit}><ClipboardPlus size={16} /> Criar solicitação</button>
            </div>
          </section>
        )}
      </section>
    </>
  );
}

function splitLines(value) {
  return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function typeLabel(value) {
  return {
    COMPROMISSO: "Compromisso",
    VISITA: "Visita",
    REUNIAO: "Reunião",
    AUDIENCIA: "Audiência",
  }[value] || value;
}

function statusLabel(value) {
  return {
    AGENDADO: "Agendado",
    REALIZADO: "Realizado",
    CANCELADO: "Cancelado",
  }[value] || value;
}
