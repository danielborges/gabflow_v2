import {
  AlignLeft,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardPlus,
  Clock3,
  Download,
  MapPin,
  Pencil,
  Plus,
  Search,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiDownload, apiRequest } from "../api";
import { FeatureHeader } from "./FeatureHeader";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

const VIEW_OPTIONS = [
  ["day", "Dia"],
  ["week", "Semana"],
  ["month", "Mês"],
];
const WEEK_DAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const CALENDAR_HOURS = Array.from({ length: 24 }, (_, index) => index);

export function AgendaPage() {
  const [events, setEvents] = useState([]);
  const [participants, setParticipants] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [jurisdiction, setJurisdiction] = useState(null);
  const [calendarDate, setCalendarDate] = useState(startOfDay(new Date()));
  const [view, setView] = useState("month");
  const [form, setForm] = useState(() => emptyEventForm(new Date()));
  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [recordForm, setRecordForm] = useState({ ata: "", pendencias: "" });
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [agendaData, participantData, routeData, jurisdictionData] = await Promise.all([
      apiRequest("/api/v1/agenda/compromissos"),
      apiRequest("/api/v1/agenda/participantes"),
      apiRequest("/api/v1/agenda/roteiros-visita"),
      apiRequest("/api/v1/admin/jurisdicao"),
    ]);
    setEvents(agendaData.content || []);
    setParticipants(participantData.content || []);
    setRoutes(routeData.content || []);
    setJurisdiction(jurisdictionData);
  }, []);

  useEffect(() => { load().catch((requestError) => setError(requestError.message)); }, [load]);

  function openEditor(date = new Date()) {
    const startsAt = normalizeSlotDate(date);
    setForm(emptyEventForm(startsAt));
    setError("");
    setEditorOpen(true);
  }

  function openEvent(item) {
    setSelected(item);
    setRecordForm({ ata: "", pendencias: "" });
    setError("");
  }

  function openEdit(item) {
    setForm({
      id: item.id,
      tipo: item.tipo,
      titulo: item.titulo,
      descricao: item.descricao || "",
      local: item.local || "",
      inicio: toLocalInput(new Date(item.inicio)),
      fim: item.fim
        ? toLocalInput(new Date(item.fim))
        : toLocalInput(new Date(new Date(item.inicio).getTime() + 60 * 60 * 1000)),
      presencaParlamentar: Boolean(item.presencaParlamentar),
      participanteIds: (item.participantes || [])
        .filter((participant) => typeof participant === "object" && participant.id)
        .map((participant) => participant.id),
    });
    setSelected(null);
    setError("");
    setEditorOpen(true);
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await apiRequest(form.id ? `/api/v1/agenda/compromissos/${form.id}` : "/api/v1/agenda/compromissos", {
        method: form.id ? "PATCH" : "POST",
        body: JSON.stringify({
          tipo: form.tipo,
          titulo: form.titulo,
          descricao: form.descricao,
          local: form.local,
          inicio: new Date(form.inicio).toISOString(),
          fim: form.fim ? new Date(form.fim).toISOString() : null,
          presencaParlamentar: form.presencaParlamentar,
          participanteIds: form.participanteIds,
        }),
      });
      setEditorOpen(false);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function downloadWeeklyReport() {
    setDownloading(true);
    setError("");
    try {
      const reference = localDateValue(calendarDate);
      const blob = await apiDownload(`/api/v1/agenda/relatorio-semanal.pdf?data=${reference}`, { method: "GET" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `agenda-executiva-${reference}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setDownloading(false);
    }
  }

  async function recordVisit() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await apiRequest(`/api/v1/agenda/compromissos/${selected.id}/registro`, {
        method: "POST",
        body: JSON.stringify({
          ata: recordForm.ata,
          pendencias: splitLines(recordForm.pendencias),
        }),
      });
      setSelected(updated);
      setRecordForm({ ata: "", pendencias: "" });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function createRequestFromVisit() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      await apiRequest(`/api/v1/agenda/compromissos/${selected.id}/solicitacoes`, {
        method: "POST",
        body: JSON.stringify({
          titulo: `Demanda originada de ${selected.titulo}`,
          descricao: selected.ata || recordForm.ata || selected.descricao,
        }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  function navigate(direction) {
    setCalendarDate((current) => {
      if (view === "day") return addDays(current, direction);
      if (view === "week") return addDays(current, direction * 7);
      return addMonths(current, direction);
    });
  }

  return <>
    <FeatureHeader className="agenda-page-heading" eyebrow="Agenda institucional" title="Agenda" description="Organize a rotina do gabinete e identifique rapidamente os compromissos com presença parlamentar." />

    <section className="agenda-google-shell">
      <aside className="agenda-sidebar">
        <button type="button" className="agenda-create-button" onClick={() => openEditor()}><Plus size={19} /> Compromisso</button>
        <MiniCalendar value={calendarDate} onChange={setCalendarDate} />
        <div className="agenda-legend">
          <strong>Identificação</strong>
          <span><i className="standard" /> Agenda do gabinete</span>
          <span><i className="representative" /> Presença do parlamentar</span>
        </div>
        <div className="agenda-route-summary">
          <header><MapPin size={16} /><strong>Roteiros sugeridos</strong></header>
          {routes.slice(0, 3).map((item) => <article key={item.territorioId || item.territorio}><b>{item.territorio}</b><small>{item.totalDemandas} demandas abertas</small></article>)}
          {!routes.length && <small>Sem sugestões no momento.</small>}
        </div>
      </aside>

      <main className="agenda-calendar-card">
        <header className="agenda-calendar-toolbar">
          <button type="button" className="agenda-today-button" onClick={() => setCalendarDate(startOfDay(new Date()))}>Hoje</button>
          <div className="agenda-navigation">
            <button type="button" aria-label="Período anterior" onClick={() => navigate(-1)}><ChevronLeft size={19} /></button>
            <button type="button" aria-label="Próximo período" onClick={() => navigate(1)}><ChevronRight size={19} /></button>
          </div>
          <h2>{calendarTitle(calendarDate, view)}</h2>
          <button type="button" className="agenda-weekly-report-button" disabled={downloading} onClick={downloadWeeklyReport}><Download size={16} /> {downloading ? "Gerando..." : "PDF da semana"}</button>
          <div className="agenda-view-switcher" aria-label="Visualização da agenda">
            {VIEW_OPTIONS.map(([id, label]) => <button type="button" key={id} className={view === id ? "active" : ""} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>)}
          </div>
        </header>
        <CalendarSurface view={view} date={calendarDate} events={events} onCreate={openEditor} onSelect={openEvent} />
      </main>
    </section>

    {editorOpen && <EventEditor form={form} setForm={setForm} participants={participants} jurisdiction={jurisdiction} error={error} saving={saving} onClose={() => setEditorOpen(false)} onSubmit={submit} />}
    {selected && <EventDetail item={selected} recordForm={recordForm} setRecordForm={setRecordForm} error={error} saving={saving} onClose={() => setSelected(null)} onEdit={() => openEdit(selected)} onRecord={recordVisit} onCreateRequest={createRequestFromVisit} />}
  </>;
}

function CalendarSurface({ view, date, events, onCreate, onSelect }) {
  if (view === "month") return <MonthCalendar date={date} events={events} onCreate={onCreate} onSelect={onSelect} />;
  const days = view === "week" ? weekDays(date) : [startOfDay(date)];
  return <TimeGrid days={days} events={events} onCreate={onCreate} onSelect={onSelect} />;
}

function MonthCalendar({ date, events, onCreate, onSelect }) {
  const days = monthGridDays(date);
  return <div className="agenda-month-view">
    <div className="agenda-month-weekdays">{WEEK_DAYS.map((day) => <span key={day}>{day}</span>)}</div>
    <div className="agenda-month-grid">
      {days.map((day) => {
        const dayEvents = eventsForDay(events, day);
        return <div key={day.toISOString()} className={`agenda-month-day ${day.getMonth() !== date.getMonth() ? "outside" : ""} ${isToday(day) ? "today" : ""}`} onClick={() => onCreate(day)}>
          <span className="agenda-day-number">{day.getDate()}</span>
          <div>{dayEvents.slice(0, 3).map((item) => <CalendarEvent key={item.id} item={item} compact onSelect={onSelect} />)}{dayEvents.length > 3 && <small className="agenda-more-events">+{dayEvents.length - 3} compromissos</small>}</div>
        </div>;
      })}
    </div>
  </div>;
}

function TimeGrid({ days, events, onCreate, onSelect }) {
  return <div className={`agenda-time-view ${days.length === 1 ? "day-view" : "week-view"}`}>
    <div className="agenda-time-header"><span /><div>{days.map((day) => <button type="button" key={day.toISOString()} className={isToday(day) ? "today" : ""} onClick={() => onCreate(day)}><small>{WEEK_DAYS[day.getDay()]}</small><b>{day.getDate()}</b></button>)}</div></div>
    <div className="agenda-time-scroll">
      {CALENDAR_HOURS.map((hour) => <div className="agenda-hour-row" key={hour}><time>{String(hour).padStart(2, "0")}:00</time><div>{days.map((day) => {
        const slot = dateAtHour(day, hour);
        const slotEvents = eventsForHour(events, day, hour);
        return <div className="agenda-time-slot" key={slot.toISOString()} onClick={() => onCreate(slot)}>{slotEvents.map((item) => <CalendarEvent key={item.id} item={item} onSelect={onSelect} />)}</div>;
      })}</div></div>)}
    </div>
  </div>;
}

function CalendarEvent({ item, compact = false, onSelect }) {
  return <button type="button" className={`agenda-event ${item.presencaParlamentar ? "with-representative" : "standard"} ${item.tipo === "FISCALIZACAO" ? "oversight-event" : ""}`} onClick={(event) => { event.stopPropagation(); onSelect(item); }} title={`${formatTime(item.inicio)} · ${item.titulo}`}>
    {!compact && <time>{formatTime(item.inicio)}</time>}<strong>{item.titulo}</strong>{item.presencaParlamentar && <UserCheck size={12} aria-label="Presença do parlamentar" />}
  </button>;
}

function EventEditor({ form, setForm, participants, jurisdiction, error, saving, onClose, onSubmit }) {
  return <div className="agenda-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <form className="agenda-event-dialog" role="dialog" aria-modal="true" aria-labelledby="agenda-editor-title" onSubmit={onSubmit}>
      <header><div><span><CalendarDays size={18} /></span><div><small>{form.id ? "Editar compromisso" : "Novo compromisso"}</small><h2 id="agenda-editor-title">{form.id ? "Atualizar compromisso" : "Adicionar à agenda"}</h2></div></div><button type="button" aria-label="Fechar" onClick={onClose}><X size={20} /></button></header>
      <div className="agenda-event-form-body">
        <label className="agenda-title-field"><input required autoFocus value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} placeholder="Adicionar título" /></label>
        <div className="agenda-form-row agenda-form-two-columns">
          <label><span>Tipo</span><select value={form.tipo} onChange={(event) => setForm((current) => ({ ...current, tipo: event.target.value }))}><option value="COMPROMISSO">Compromisso</option><option value="VISITA">Visita</option><option value="REUNIAO">Reunião</option><option value="AUDIENCIA">Audiência</option><option value="FISCALIZACAO">Fiscalização</option></select></label>
          <label className="agenda-representative-check"><input type="checkbox" checked={form.presencaParlamentar} onChange={(event) => setForm((current) => ({ ...current, presencaParlamentar: event.target.checked }))} /><span><UserCheck size={18} /><b>Presença do Parlamentar</b><small>Destacar este compromisso no calendário</small></span></label>
        </div>
        <div className="agenda-form-row agenda-date-row"><Clock3 size={19} /><label><span>Início</span><input required type="datetime-local" value={form.inicio} onChange={(event) => updateStartAndEnd(setForm, event.target.value)} /></label><label><span>Fim</span><input required type="datetime-local" min={form.inicio} value={form.fim} onChange={(event) => setForm((current) => ({ ...current, fim: event.target.value }))} /></label></div>
        <div className="agenda-form-row"><MapPin size={19} /><label className="agenda-grow"><span>Local</span><GooglePlaceAutocompleteInput value={form.local} onChange={(local) => setForm((current) => ({ ...current, local }))} placeholder="Adicionar local" territoryBounds={jurisdiction?.limites} inputProps={{ "aria-label": "Local" }} /></label></div>
        <div className="agenda-form-row"><Users size={19} /><ParticipantMultiSelect options={participants} value={form.participanteIds} onChange={(participanteIds) => setForm((current) => ({ ...current, participanteIds }))} /></div>
        <div className="agenda-form-row"><AlignLeft size={19} /><label className="agenda-grow"><span>Descrição</span><textarea rows="3" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} placeholder="Adicionar descrição ou observações" /></label></div>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
      <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact" disabled={saving}>{saving ? "Salvando..." : form.id ? "Salvar alterações" : "Salvar compromisso"}</button></footer>
    </form>
  </div>;
}

function ParticipantMultiSelect({ options, value, onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const selected = options.filter((item) => value.includes(item.id));
  const available = options.filter((item) => !value.includes(item.id) && item.nome.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 8);

  useEffect(() => {
    function closeOnOutsideInteraction(event) {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsideInteraction);
    return () => document.removeEventListener("pointerdown", closeOnOutsideInteraction);
  }, []);

  function select(item) {
    onChange([...value, item.id]);
    setQuery("");
    setOpen(false);
  }

  return <div ref={containerRef} className="agenda-participant-select agenda-grow">
    <label htmlFor="agenda-participant-search">Participantes</label>
    {!!selected.length && <div className="agenda-participant-chips">{selected.map((item) => <button type="button" key={item.id} onClick={() => onChange(value.filter((id) => id !== item.id))}>{initials(item.nome)} <span>{item.nome}</span><X size={13} /></button>)}</div>}
    <div className={`agenda-participant-control ${open ? "open" : ""}`}><Search size={17} /><input id="agenda-participant-search" role="combobox" aria-expanded={open} aria-controls="agenda-participant-options" value={query} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} placeholder="Pesquisar funcionários do gabinete" /></div>
    {open && <div id="agenda-participant-options" className="agenda-participant-options" role="listbox">{available.length ? available.map((item) => <button type="button" role="option" aria-selected="false" key={item.id} onClick={() => select(item)}><span>{initials(item.nome)}</span><div><strong>{item.nome}</strong><small>{roleLabel(item.perfil)}</small></div><Plus size={15} /></button>) : <p>{options.length ? "Nenhum outro funcionário encontrado." : "Nenhum funcionário disponível."}</p>}</div>}
  </div>;
}

function EventDetail({ item, recordForm, setRecordForm, error, saving, onClose, onEdit, onRecord, onCreateRequest }) {
  const participantNames = (item.participantes || []).map((participant) => typeof participant === "string" ? participant : participant.nome).filter(Boolean);
  return <div className="agenda-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`agenda-event-detail-dialog ${item.presencaParlamentar ? "with-representative" : ""}`} role="dialog" aria-modal="true" aria-labelledby="agenda-detail-title">
      <header><div className="agenda-detail-color" /><div><small>{typeLabel(item.tipo)} · {statusLabel(item.status)}</small><h2 id="agenda-detail-title">{item.titulo}</h2></div><button type="button" aria-label="Fechar" onClick={onClose}><X size={20} /></button></header>
      <div className="agenda-detail-body">
        {item.presencaParlamentar && <div className="agenda-presence-callout"><UserCheck size={18} /><strong>Presença do parlamentar confirmada</strong></div>}
        <dl><div><Clock3 size={18} /><dt>Data e horário</dt><dd>{formatDateRange(item.inicio, item.fim)}</dd></div><div><MapPin size={18} /><dt>Local</dt><dd>{item.local || "Não informado"}</dd></div><div><Users size={18} /><dt>Participantes</dt><dd>{participantNames.join(", ") || "Nenhum funcionário selecionado"}</dd></div></dl>
        {item.descricao && <p className="agenda-detail-description">{item.descricao}</p>}
        {item.ata && <article className="agenda-existing-record"><strong>Registro realizado</strong><p>{item.ata}</p></article>}
        <div className="agenda-record-form"><label>Ata ou registro<textarea rows="4" value={recordForm.ata} onChange={(event) => setRecordForm((current) => ({ ...current, ata: event.target.value }))} placeholder="Registre os principais pontos do compromisso" /></label><label>Pendências<textarea rows="2" value={recordForm.pendencias} onChange={(event) => setRecordForm((current) => ({ ...current, pendencias: event.target.value }))} placeholder="Uma pendência por linha" /></label></div>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
      <footer><button type="button" className="secondary-button agenda-edit-event-button" onClick={onEdit}><Pencil size={16} /> Editar compromisso</button><button type="button" className="secondary-button" disabled={saving || recordForm.ata.trim().length < 3} onClick={onRecord}><Check size={16} /> Registrar realização</button><button type="button" className="primary-button compact" disabled={saving || (!item.ata && recordForm.ata.trim().length < 10)} onClick={onCreateRequest}><ClipboardPlus size={16} /> Criar solicitação</button></footer>
    </section>
  </div>;
}

function MiniCalendar({ value, onChange }) {
  const days = monthGridDays(value);
  return <div className="agenda-mini-calendar"><header><strong>{capitalize(new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(value))}</strong></header><div className="agenda-mini-weekdays">{WEEK_DAYS.map((day) => <span key={day}>{day[0]}</span>)}</div><div className="agenda-mini-days">{days.map((day) => <button type="button" key={day.toISOString()} className={`${day.getMonth() !== value.getMonth() ? "outside" : ""} ${sameDay(day, value) ? "selected" : ""} ${isToday(day) ? "today" : ""}`} onClick={() => onChange(day)}>{day.getDate()}</button>)}</div></div>;
}

function emptyEventForm(date) {
  const start = normalizeSlotDate(date);
  return { id: null, tipo: "COMPROMISSO", titulo: "", descricao: "", local: "", inicio: toLocalInput(start), fim: toLocalInput(new Date(start.getTime() + 60 * 60 * 1000)), presencaParlamentar: false, participanteIds: [] };
}

function updateStartAndEnd(setForm, value) {
  if (!value) return setForm((current) => ({ ...current, inicio: "", fim: "" }));
  const start = new Date(value);
  setForm((current) => ({
    ...current,
    inicio: value,
    fim: toLocalInput(new Date(start.getTime() + 60 * 60 * 1000)),
  }));
}

function normalizeSlotDate(value) {
  const date = new Date(value);
  if (date.getHours() === 0 && date.getMinutes() === 0) date.setHours(Math.max(new Date().getHours() + 1, 8), 0, 0, 0);
  else date.setMinutes(date.getMinutes() < 30 ? 0 : 30, 0, 0);
  return date;
}

function monthGridDays(value) {
  const first = new Date(value.getFullYear(), value.getMonth(), 1);
  const start = addDays(first, -first.getDay());
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

function weekDays(value) {
  const start = addDays(startOfDay(value), -value.getDay());
  return Array.from({ length: 7 }, (_, index) => addDays(start, index));
}

function eventsForDay(events, day) {
  return events.filter((item) => sameDay(new Date(item.inicio), day)).sort((left, right) => new Date(left.inicio) - new Date(right.inicio));
}

function eventsForHour(events, day, hour) {
  return eventsForDay(events, day).filter((item) => new Date(item.inicio).getHours() === hour);
}

function startOfDay(value) { return new Date(value.getFullYear(), value.getMonth(), value.getDate()); }
function addDays(value, amount) { const date = new Date(value); date.setDate(date.getDate() + amount); return date; }
function addMonths(value, amount) { const date = new Date(value); date.setDate(1); date.setMonth(date.getMonth() + amount); return date; }
function dateAtHour(day, hour) { return new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0, 0, 0); }
function sameDay(left, right) { return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate(); }
function isToday(value) { return sameDay(value, new Date()); }
function toLocalInput(value) { const offset = value.getTimezoneOffset() * 60000; return new Date(value.getTime() - offset).toISOString().slice(0, 16); }
function localDateValue(value) { const offset = value.getTimezoneOffset() * 60000; return new Date(value.getTime() - offset).toISOString().slice(0, 10); }
function splitLines(value) { return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean); }
function formatTime(value) { return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function formatDateRange(start, end) { const startDate = new Date(start); const date = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "2-digit", month: "long" }).format(startDate); return `${capitalize(date)}, ${formatTime(start)}${end ? ` – ${formatTime(end)}` : ""}`; }
function calendarTitle(date, view) { if (view === "day") return capitalize(new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" }).format(date)); if (view === "week") { const days = weekDays(date); return `${new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(days[0])} – ${new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(days[6])}`; } return capitalize(new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(date)); }
function initials(value) { return String(value || "").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase(); }
function capitalize(value) { return value ? value[0].toUpperCase() + value.slice(1) : value; }
function roleLabel(value) { return { admin: "Administrador", manager: "Gestor", staff: "Funcionário" }[value] || "Funcionário"; }
function typeLabel(value) { return { COMPROMISSO: "Compromisso", VISITA: "Visita", REUNIAO: "Reunião", AUDIENCIA: "Audiência", FISCALIZACAO: "Fiscalização" }[value] || value; }
function statusLabel(value) { return { AGENDADO: "Agendado", REALIZADO: "Realizado", CANCELADO: "Cancelado" }[value] || value; }
