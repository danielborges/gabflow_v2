import {
  AlertCircle, Camera, CheckCircle2, ChevronRight, ClipboardCheck, Clock3,
  Download, FileText, Link2, MapPin, Paperclip, Plus, Search, ShieldCheck,
  Upload, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api";
import { FeatureHeader } from "./FeatureHeader";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

const emptyForm = () => ({
  id: null, agendaEventoId: null, titulo: "", descricao: "", local: "",
  realizadaEm: toLocalInput(new Date()), solicitacaoId: "", solicitacao: null,
  achados: "", responsaveis: "", providencias: "", relatorio: "",
});

export function OversightPage() {
  const [items, setItems] = useState([]);
  const [pending, setPending] = useState([]);
  const [jurisdiction, setJurisdiction] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [actions, pendingData, jurisdictionData] = await Promise.all([
      apiRequest("/api/v1/fiscalizacoes"),
      apiRequest("/api/v1/fiscalizacoes/pendentes-relatorio"),
      apiRequest("/api/v1/admin/jurisdicao"),
    ]);
    setItems(actions.content);
    setPending(pendingData.content);
    setJurisdiction(jurisdictionData);
    setSelected((current) => current ? actions.content.find((item) => item.id === current.id) || null : null);
  }, []);

  useEffect(() => { load().catch((requestError) => setError(requestError.message)); }, [load]);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => [item.titulo, item.local, item.solicitacao?.protocolo]
      .filter(Boolean).some((value) => value.toLowerCase().includes(normalized)));
  }, [items, query]);

  function openNew() {
    setForm(emptyForm());
    setError("");
    setEditorOpen(true);
  }

  function openPending(item) {
    const draft = item.fiscalizacaoId && items.find((action) => action.id === item.fiscalizacaoId);
    if (draft) return openEdit(draft);
    setForm({
      ...emptyForm(),
      agendaEventoId: item.agendaEventoId,
      titulo: item.titulo,
      descricao: item.descricao || "",
      local: item.local || "",
      realizadaEm: toLocalInput(new Date(item.inicio)),
      solicitacaoId: item.solicitacaoId || "",
    });
    setError("");
    setEditorOpen(true);
  }

  function openEdit(item) {
    setForm({
      id: item.id,
      agendaEventoId: item.agendaEventoId,
      titulo: item.titulo,
      descricao: item.descricao || "",
      local: item.local || "",
      realizadaEm: item.realizadaEm ? toLocalInput(new Date(item.realizadaEm)) : "",
      solicitacaoId: item.solicitacaoId || "",
      solicitacao: item.solicitacao,
      achados: joinLines(item.achados),
      responsaveis: joinLines(item.responsaveis),
      providencias: joinLines(item.providencias),
      relatorio: item.relatorio || "",
    });
    setError("");
    setEditorOpen(true);
  }

  async function save(status) {
    setBusy(true);
    setError("");
    try {
      const body = JSON.stringify({
        agendaEventoId: form.agendaEventoId,
        titulo: form.titulo,
        descricao: form.descricao,
        local: form.local,
        realizadaEm: form.realizadaEm ? new Date(form.realizadaEm).toISOString() : null,
        solicitacaoId: form.solicitacaoId || null,
        achados: splitLines(form.achados),
        responsaveis: splitLines(form.responsaveis),
        providencias: splitLines(form.providencias),
        relatorio: form.relatorio,
        status,
      });
      const saved = await apiRequest(
        form.id ? `/api/v1/fiscalizacoes/${form.id}` : "/api/v1/fiscalizacoes",
        { method: form.id ? "PATCH" : "POST", body },
      );
      setEditorOpen(false);
      await load();
      setSelected(saved);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshSelected(id) {
    await load();
    const data = await apiRequest("/api/v1/fiscalizacoes");
    setSelected(data.content.find((item) => item.id === id) || null);
  }

  const completed = items.filter((item) => item.status === "CONCLUIDA").length;
  const withEvidence = items.filter((item) => item.evidencias?.length).length;

  return <div className="oversight-page">
    <FeatureHeader className="oversight-heading" eyebrow="Fiscalização" title="Fiscalizações do gabinete" description="Da vistoria em campo ao relatório final, com evidências e vínculo às demandas dos cidadãos.">
      <button className="primary-button compact" onClick={openNew}><Plus size={18} /> Fiscalização</button>
    </FeatureHeader>

    <section className="oversight-content">
      <div className="oversight-metrics">
        <Metric icon={<AlertCircle />} tone="warning" value={pending.length} label="Relatórios pendentes" />
        <Metric icon={<Clock3 />} tone="blue" value={items.length - completed} label="Em andamento" />
        <Metric icon={<CheckCircle2 />} tone="green" value={completed} label="Concluídas" />
        <Metric icon={<Camera />} tone="violet" value={withEvidence} label="Com evidências" />
      </div>

      {!!pending.length && <section className="oversight-pending-panel">
        <header><span><AlertCircle size={20} /></span><div><h2>Fiscalizações realizadas aguardando relatório</h2><p>Você participou destes compromissos. Complete o relato e anexe as evidências da vistoria.</p></div><b>{pending.length}</b></header>
        <div>{pending.map((item) => <article key={item.agendaEventoId}>
          <div className="oversight-pending-date"><strong>{dayNumber(item.inicio)}</strong><small>{monthName(item.inicio)}</small></div>
          <div><strong>{item.titulo}</strong><small><Clock3 size={13} /> {formatDateTime(item.inicio)} {item.local && <><MapPin size={13} /> {item.local}</>}</small></div>
          <span className={`oversight-draft-state ${item.fiscalizacaoId ? "draft" : "new"}`}>{item.fiscalizacaoId ? "Rascunho iniciado" : "Não iniciado"}</span>
          <button className="primary-button compact" onClick={() => openPending(item)}>Preencher relatório <ChevronRight size={16} /></button>
        </article>)}</div>
      </section>}

      {error && !editorOpen && <p className="form-error" role="alert">{error}</p>}
      <section className="oversight-workspace">
        <div className="oversight-list-panel">
          <header><div><h2>Histórico</h2><small>{items.length} fiscalização(ões) registrada(s)</small></div><label><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por título, local ou protocolo" /></label></header>
          <div className="oversight-action-list">
            {visibleItems.length ? visibleItems.map((item) => <button key={item.id} className={selected?.id === item.id ? "selected" : ""} onClick={() => setSelected(item)}>
              <span className={`oversight-list-icon status-${item.status.toLowerCase()}`}><ClipboardCheck size={19} /></span>
              <span><strong>{item.titulo}</strong><small>{formatDateTime(item.realizadaEm || item.criadaEm)} · {item.local || "Local não informado"}</small>{item.solicitacao && <em><Link2 size={12} /> {item.solicitacao.protocolo}</em>}</span>
              <StatusBadge status={item.status} /><ChevronRight size={17} />
            </button>) : <div className="oversight-empty"><ClipboardCheck size={30} /><strong>Nenhuma fiscalização encontrada</strong><small>Registre uma fiscalização realizada agora ou planejada.</small></div>}
          </div>
        </div>
        <div className="oversight-detail-panel">
          {selected ? <OversightDetail item={selected} onEdit={() => openEdit(selected)} onEvidenceChanged={() => refreshSelected(selected.id)} /> : <div className="oversight-detail-empty"><ShieldCheck size={40} /><h2>Registro completo da fiscalização</h2><p>Selecione uma fiscalização para consultar o relato, as providências, a solicitação vinculada e suas evidências.</p></div>}
        </div>
      </section>
    </section>

    {editorOpen && <OversightEditor form={form} setForm={setForm} jurisdiction={jurisdiction} error={error} busy={busy} onClose={() => setEditorOpen(false)} onSave={save} />}
  </div>;
}

function Metric({ icon, tone, value, label }) {
  return <article className={`oversight-metric ${tone}`}><span>{icon}</span><div><strong>{value}</strong><small>{label}</small></div></article>;
}

function OversightEditor({ form, setForm, jurisdiction, error, busy, onClose, onSave }) {
  const isAgenda = Boolean(form.agendaEventoId);
  return <div className="modal-backdrop oversight-editor-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal oversight-editor" role="dialog" aria-modal="true" aria-labelledby="oversight-editor-title">
      <header><div><span><ClipboardCheck size={20} /></span><div><small>{isAgenda ? "Originada na agenda" : "Registro em campo"}</small><h2 id="oversight-editor-title">{form.id ? "Atualizar fiscalização" : "Nova fiscalização"}</h2></div></div><button type="button" aria-label="Fechar" onClick={onClose}><X size={20} /></button></header>
      {isAgenda && <div className="oversight-agenda-callout"><Clock3 size={18} /><div><strong>Compromisso realizado</strong><small>Os dados da Agenda foram trazidos automaticamente. Complete o relatório para encerrar a pendência dos participantes.</small></div></div>}
      <div className="oversight-editor-body">
        <fieldset><legend>Identificação</legend>
          <label className="wide"><span>Título</span><input required minLength="3" value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} placeholder="Ex.: Vistoria na unidade de saúde" /></label>
          <label><span>Data e horário</span><input type="datetime-local" value={form.realizadaEm} onChange={(event) => setForm((current) => ({ ...current, realizadaEm: event.target.value }))} /></label>
          <label><span>Local</span><GooglePlaceAutocompleteInput value={form.local} onChange={(local) => setForm((current) => ({ ...current, local }))} placeholder="Endereço ou ponto de referência" territoryBounds={jurisdiction?.limites} /></label>
          <label className="wide"><span>Objetivo e contexto</span><textarea rows="2" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} placeholder="Por que a fiscalização foi realizada?" /></label>
          <RequestSearch value={form.solicitacaoId} selected={form.solicitacao} onChange={(solicitacaoId, solicitacao) => setForm((current) => ({ ...current, solicitacaoId, solicitacao }))} />
        </fieldset>
        <fieldset><legend>Constatações e encaminhamentos</legend>
          <label><span>Achados <small>um por linha</small></span><textarea rows="4" value={form.achados} onChange={(event) => setForm((current) => ({ ...current, achados: event.target.value }))} placeholder="Descreva fatos observados, sem conclusões vagas" /></label>
          <label><span>Responsáveis citados <small>um por linha</small></span><textarea rows="4" value={form.responsaveis} onChange={(event) => setForm((current) => ({ ...current, responsaveis: event.target.value }))} placeholder="Órgãos, setores ou responsáveis locais" /></label>
          <label className="wide"><span>Providências e próximos passos <small>um por linha</small></span><textarea rows="3" value={form.providencias} onChange={(event) => setForm((current) => ({ ...current, providencias: event.target.value }))} placeholder="Ofícios, retornos, prazos e responsáveis" /></label>
        </fieldset>
        <fieldset className="oversight-report-fieldset"><legend>Relatório da fiscalização</legend><label className="wide"><span>Relato conclusivo</span><textarea rows="7" value={form.relatorio} onChange={(event) => setForm((current) => ({ ...current, relatorio: event.target.value }))} placeholder="Consolide o que foi fiscalizado, o que foi constatado e quais medidas serão tomadas." /><small>O relato conclusivo é obrigatório para marcar a fiscalização como concluída.</small></label></fieldset>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
      <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button type="button" className="secondary-button" disabled={busy || form.titulo.trim().length < 3} onClick={() => onSave("EM_ANDAMENTO")}>Salvar rascunho</button><button type="button" className="primary-button compact" disabled={busy || form.titulo.trim().length < 3 || form.relatorio.trim().length < 10} onClick={() => onSave("CONCLUIDA")}><CheckCircle2 size={17} /> Concluir relatório</button></footer>
    </section>
  </div>;
}

function RequestSearch({ value, selected, onChange }) {
  const [query, setQuery] = useState(selected ? `${selected.protocolo} · ${selected.titulo}` : "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (query.trim().length < 2 || (selected && query.includes(selected.protocolo))) return setResults([]);
    const timer = setTimeout(() => apiRequest(`/api/v1/solicitacoes?q=${encodeURIComponent(query)}&size=8`).then((data) => { setResults(data.content || []); setOpen(true); }).catch(() => setResults([])), 250);
    return () => clearTimeout(timer);
  }, [query, selected]);
  return <div className="oversight-request-search wide"><label><span>Solicitação de cidadão vinculada <small>opcional</small></span><div><Link2 size={16} /><input value={query} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); if (value) onChange("", null); }} placeholder="Busque por protocolo, título ou descrição" />{value && <button type="button" aria-label="Remover vínculo" onClick={() => { setQuery(""); onChange("", null); }}><X size={15} /></button>}</div></label>{open && !!results.length && <div className="oversight-request-results">{results.map((item) => <button type="button" key={item.id} onClick={() => { onChange(item.id, item); setQuery(`${item.protocolo} · ${item.titulo}`); setOpen(false); }}><strong>{item.protocolo}</strong><span>{item.titulo}</span></button>)}</div>}</div>;
}

function OversightDetail({ item, onEdit, onEvidenceChanged }) {
  const [uploading, setUploading] = useState(false);
  const [observation, setObservation] = useState("");
  const [uploadError, setUploadError] = useState("");
  const photoRef = useRef(null);
  const documentRef = useRef(null);

  async function upload(file, type) {
    if (!file) return;
    setUploading(true);
    setUploadError("");
    try {
      const body = new FormData();
      body.append("arquivo", file);
      body.append("tipo", type);
      body.append("observacao", observation);
      await apiRequest(`/api/v1/fiscalizacoes/${item.id}/evidencias`, { method: "POST", body });
      setObservation("");
      await onEvidenceChanged();
    } catch (error) { setUploadError(error.message); } finally { setUploading(false); }
  }

  return <div className="oversight-detail">
    <header><div><StatusBadge status={item.status} />{item.agendaEventoId && <span className="oversight-source-badge"><Clock3 size={13} /> Agenda</span>}<h2>{item.titulo}</h2><p>{item.descricao || "Sem descrição complementar."}</p></div><button className="secondary-button compact" onClick={onEdit}>Editar registro</button></header>
    <dl className="oversight-detail-meta"><div><dt><Clock3 size={15} /> Realizada em</dt><dd>{formatDateTime(item.realizadaEm || item.criadaEm)}</dd></div><div><dt><MapPin size={15} /> Local</dt><dd>{item.local || "Não informado"}</dd></div>{item.solicitacao && <div><dt><Link2 size={15} /> Solicitação vinculada</dt><dd>{item.solicitacao.protocolo} · {item.solicitacao.titulo}</dd></div>}</dl>
    <div className="oversight-detail-sections">
      <TextSection title="Relatório" values={item.relatorio ? [item.relatorio] : []} empty="Relatório ainda não concluído." prose />
      <TextSection title="Achados" values={item.achados} empty="Nenhum achado registrado." />
      <TextSection title="Providências" values={item.providencias} empty="Nenhuma providência registrada." />
      <TextSection title="Responsáveis citados" values={item.responsaveis} empty="Nenhum responsável citado." />
    </div>
    <section className="oversight-evidence-section"><header><div><h3>Evidências e documentos</h3><p>Fotos e arquivos são verificados, criptografados e preservados com a observação de campo.</p></div><b>{item.evidencias?.length || 0}</b></header>
      <div className="oversight-evidence-upload"><label><span>Observação da evidência</span><input value={observation} onChange={(event) => setObservation(event.target.value)} placeholder="O que esta foto ou documento comprova?" /></label><div><button type="button" className="secondary-button compact" disabled={uploading} onClick={() => photoRef.current?.click()}><Camera size={16} /> Tirar foto</button><input ref={photoRef} hidden type="file" accept="image/jpeg,image/png" capture="environment" onChange={(event) => upload(event.target.files?.[0], "FOTO")} /><button type="button" className="secondary-button compact" disabled={uploading} onClick={() => documentRef.current?.click()}><Upload size={16} /> Enviar arquivo</button><input ref={documentRef} hidden type="file" accept="image/jpeg,image/png,application/pdf,text/plain" onChange={(event) => upload(event.target.files?.[0], event.target.files?.[0]?.type.startsWith("image/") ? "FOTO" : "DOCUMENTO")} /></div></div>
      {uploadError && <p className="form-error">{uploadError}</p>}
      <div className="oversight-evidence-grid">{item.evidencias?.length ? item.evidencias.map((evidence) => <EvidenceCard key={evidence.id} evidence={evidence} onChanged={onEvidenceChanged} />) : <div className="oversight-evidence-empty"><Paperclip size={24} /><span>Nenhuma evidência anexada.</span></div>}</div>
    </section>
  </div>;
}

function EvidenceCard({ evidence, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [observation, setObservation] = useState(evidence.observacao || "");
  async function save() { await apiRequest(`/api/v1/fiscalizacoes/evidencias/${evidence.id}`, { method: "PATCH", body: JSON.stringify({ observacao: observation }) }); setEditing(false); await onChanged(); }
  const image = evidence.mimeType?.startsWith("image/");
  return <article className="oversight-evidence-card">{image ? <img src={evidence.downloadUrl} alt={evidence.observacao || evidence.nomeArquivo} /> : <span className="oversight-document-icon"><FileText size={27} /></span>}<div><strong>{evidence.nomeArquivo}</strong><small>{formatBytes(evidence.tamanho)} · {evidence.autor}</small>{editing ? <><textarea rows="2" value={observation} onChange={(event) => setObservation(event.target.value)} /><button type="button" onClick={save}>Salvar observação</button></> : <p>{evidence.observacao || "Sem observação."}</p>}</div><footer><button type="button" onClick={() => setEditing((value) => !value)}>Observação</button><a href={evidence.downloadUrl} title="Baixar evidência"><Download size={16} /></a></footer></article>;
}

function TextSection({ title, values = [], empty, prose = false }) {
  return <section className={prose ? "prose" : ""}><h3>{title}</h3>{values.length ? (prose ? <p>{values[0]}</p> : <ul>{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul>) : <p className="empty">{empty}</p>}</section>;
}

function StatusBadge({ status }) { return <span className={`oversight-status status-${status.toLowerCase()}`}>{statusLabel(status)}</span>; }
function statusLabel(value) { return { PLANEJADA: "Planejada", EM_ANDAMENTO: "Em andamento", CONCLUIDA: "Concluída", CANCELADA: "Cancelada" }[value] || value; }
function splitLines(value) { return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean); }
function joinLines(value) { return (value || []).join("\n"); }
function toLocalInput(value) { const offset = value.getTimezoneOffset() * 60000; return new Date(value.getTime() - offset).toISOString().slice(0, 16); }
function formatDateTime(value) { if (!value) return "Data não informada"; return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function dayNumber(value) { return new Intl.DateTimeFormat("pt-BR", { day: "2-digit" }).format(new Date(value)); }
function monthName(value) { return new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(new Date(value)).replace(".", "").toUpperCase(); }
function formatBytes(value) { if (!value) return "0 B"; if (value < 1024) return `${value} B`; if (value < 1048576) return `${Math.round(value / 1024)} KB`; return `${(value / 1048576).toFixed(1)} MB`; }
