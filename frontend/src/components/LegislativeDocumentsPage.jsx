import {
  BookMarked,
  CheckCircle2,
  Clock3,
  Download,
  ExternalLink,
  FilePlus2,
  FileText,
  GitCompare,
  History,
  Eye,
  EyeOff,
  LayoutTemplate,
  Library,
  Link2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Milestone,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiDownload, apiRequest } from "../api";
import { RequestSearchSelect } from "./RequestsPage";

const TYPES = [
  ["INDICACAO", "Indicação"],
  ["REQUERIMENTO", "Requerimento"],
  ["OFICIO", "Ofício"],
  ["MOCAO", "Moção"],
  ["PEDIDO_INFORMACAO", "Pedido de informação"],
  ["PROJETO_LEI", "Projeto de lei"],
];
const STATUS_LABELS = { RASCUNHO: "Rascunho", EM_REVISAO: "Em revisão", APROVADA: "Aprovada", REJEITADA: "Rejeitada" };
const TRAMITATION_STATUS_LABELS = {
  PROTOCOLADA: "Protocolada",
  DISTRIBUIDA: "Distribuída",
  EM_COMISSAO: "Em comissão",
  EM_PAUTA: "Em pauta",
  APROVADA: "Aprovada",
  REJEITADA: "Rejeitada",
  SANCIONADA: "Sancionada",
  VETADA: "Vetada",
  ARQUIVADA: "Arquivada",
  RETIRADA: "Retirada",
};
const NORMATIVE_TYPES = [
  ["LEI_ORGANICA", "Lei orgânica"],
  ["REGIMENTO_INTERNO", "Regimento interno"],
  ["LEI_MUNICIPAL", "Lei municipal"],
  ["DECRETO", "Decreto"],
  ["PLANO_DIRETOR", "Plano diretor"],
  ["CODIGO_OBRAS", "Código de obras"],
  ["CODIGO_POSTURAS", "Código de posturas"],
  ["OUTRO", "Outro"],
];

export function LegislativeDocumentsPage({ user }) {
  const manager = ["admin", "manager"].includes(user.role);
  const [items, setItems] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [activeSection, setActiveSection] = useState("drafts");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
      const [drafts, templateData] = await Promise.all([
        apiRequest(`/api/v1/legislativo/minutas${suffix}`),
        apiRequest(`/api/v1/legislativo/templates${manager ? "?incluirInativos=true" : ""}`),
      ]);
      setItems(drafts.content);
      setTemplates(templateData.content);
    } catch (requestError) { setError(requestError.message); }
  }, [manager, query]);

  const loadDetail = useCallback(async (id) => {
    if (!id) return undefined;
    try {
      const value = await apiRequest(`/api/v1/legislativo/minutas/${id}`);
      setDraft(value);
      setItems((current) => current.map((item) => (item.id === id ? { ...item, ...value } : item)));
      return value;
    } catch (requestError) { setError(requestError.message); return undefined; }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadDetail(selectedId); }, [loadDetail, selectedId]);
  useEffect(() => {
    if (!draft || !["PENDENTE", "PROCESSANDO"].includes(draft.statusGeracao)) return undefined;
    const timer = setInterval(async () => {
      const updated = await loadDetail(draft.id);
      if (updated && !["PENDENTE", "PROCESSANDO"].includes(updated.statusGeracao)) clearInterval(timer);
    }, 2500);
    return () => clearInterval(timer);
  }, [draft, loadDetail]);

  async function createDraft(values) {
    setBusy(true); setError("");
    try {
      const created = await apiRequest(`/api/v1/solicitacoes/${values.requestId}/gerar-minuta`, { method: "POST", body: JSON.stringify(values.payload) });
      setCreating(false); setItems((current) => [created, ...current]); setSelectedId(created.id); setDraft(created);
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  async function review(action, values = {}) {
    setBusy(true); setError("");
    try {
      const updated = await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/revisao`, { method: "POST", body: JSON.stringify({ acao: action, ...values }) });
      setDraft(updated); await load();
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  return <>
    <section className="page-heading legislative-heading"><div><p className="eyebrow">Produção legislativa</p><h1>Documentos e minutas</h1><p>Transforme demandas selecionadas em proposições revisáveis e rastreáveis.</p></div><div className="legislative-heading-actions"><div className="legislative-view-switch" role="tablist" aria-label="Área legislativa"><button role="tab" aria-selected={activeSection === "drafts"} className={activeSection === "drafts" ? "active" : ""} onClick={() => setActiveSection("drafts")}><FileText size={17} /> Minutas</button><button role="tab" aria-selected={activeSection === "precedents"} className={activeSection === "precedents" ? "active" : ""} onClick={() => { setActiveSection("precedents"); setCreating(false); }}><Library size={17} /> Precedentes</button><button role="tab" aria-selected={activeSection === "templates"} className={activeSection === "templates" ? "active" : ""} onClick={() => { setActiveSection("templates"); setCreating(false); }}><LayoutTemplate size={17} /> Templates</button>{manager && <button role="tab" aria-selected={activeSection === "sources"} className={activeSection === "sources" ? "active" : ""} onClick={() => { setActiveSection("sources"); setCreating(false); }}><BookMarked size={17} /> Base normativa</button>}</div>{activeSection === "drafts" && <button className="primary-button" onClick={() => setCreating(true)}><FilePlus2 size={18} /> Nova minuta</button>}</div></section>
    {error && <p className="form-error">{error}</p>}
    {activeSection === "drafts" && creating && <DraftCreationForm templates={templates} busy={busy} onCancel={() => setCreating(false)} onSubmit={createDraft} />}
    {activeSection === "drafts" && <section className="legislative-workspace">
      <aside className="legislative-list"><div className="legislative-search"><Search size={17} /><input aria-label="Pesquisar minutas" placeholder="Título ou protocolo" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="icon-button" onClick={load} title="Atualizar"><RefreshCw size={17} /></button></div><div className="legislative-items">{items.map((item) => <button key={item.id} className={selectedId === item.id ? "legislative-item active" : "legislative-item"} onClick={() => setSelectedId(item.id)}><FileText size={18} /><span><strong>{item.titulo}</strong><small>{typeLabel(item.tipo)} · {STATUS_LABELS[item.status] || item.status}</small></span><StatusDot generation={item.statusGeracao} /></button>)}{!items.length && <p className="table-message">Nenhuma minuta cadastrada.</p>}</div></aside>
      <div className="legislative-editor-area">{draft ? <DraftEditor draft={draft} user={user} busy={busy} onReview={review} onChange={setDraft} onReload={() => loadDetail(draft.id)} onOpenDraft={setSelectedId} /> : <div className="legislative-empty"><FileText size={34} /><h2>Selecione uma minuta</h2><p>O conteúdo, fontes, versões e decisões aparecerão aqui.</p></div>}</div>
    </section>}
    {activeSection === "precedents" && <PrecedentSearch onOpenDraft={(id) => { setSelectedId(id); setActiveSection("drafts"); }} />}
    {activeSection === "templates" && <TemplateManagement templates={templates} manager={manager} onTemplatesChange={setTemplates} />}
    {activeSection === "sources" && manager && <NormativeSourceManagement />}
  </>;
}

function PrecedentSearch({ onOpenDraft }) {
  const [query, setQuery] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search(event) {
    event.preventDefault();
    if (query.trim().length < 3) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: query.trim(), limite: "10" });
      if (documentType) params.set("tipo", documentType);
      if (status) params.set("status", status);
      setResult(await apiRequest(`/api/v1/legislativo/precedentes?${params}`));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="precedent-search-page">
    <form className="precedent-search-form" onSubmit={search}>
      <header><div><Library size={22} /><span><h2>Busca semântica de precedentes</h2><p>Localize proposições pelo significado do tema, mesmo com palavras diferentes.</p></span></div>{result && <span className="precedent-model">{result.modelo}{result.fallbackUtilizado ? " · fallback local" : " · embeddings locais"}</span>}</header>
      <div className="precedent-search-controls">
        <label className="precedent-query"><span>Assunto, problema ou providência</span><div><Search size={18} /><input aria-label="Assunto do precedente" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ex.: garantir iluminação e segurança em espaços públicos" /></div></label>
        <label><span>Tipo</span><select aria-label="Tipo do precedente" value={documentType} onChange={(event) => setDocumentType(event.target.value)}><option value="">Todos</option>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span>Status</span><select aria-label="Status do precedente" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button className="primary-button" disabled={loading || query.trim().length < 3}><Search size={18} /> {loading ? "Buscando..." : "Buscar precedentes"}</button>
      </div>
    </form>
    {error && <p className="form-error">{error}</p>}
    {!result && <div className="precedent-empty"><Library size={30} /><h3>Consulte o acervo legislativo do gabinete</h3><p>A busca considera título, conteúdo, justificativa e fundamentação normativa.</p></div>}
    {result && <div className="precedent-results">
      <header><div><strong>{result.content.length} {result.content.length === 1 ? "precedente encontrado" : "precedentes encontrados"}</strong><small>{result.totalCandidatos} documentos avaliados · limiar de {Math.round(result.limiar * 100)}%</small></div></header>
      {!result.content.length && <div className="precedent-empty compact"><Search size={25} /><h3>Nenhum precedente relevante</h3><p>Tente ampliar os termos ou remover algum filtro.</p></div>}
      {result.content.map((item) => <article key={item.id} className="precedent-result">
        <div className="precedent-score"><strong>{Math.round(item.similaridade * 100)}%</strong><span>similar</span><i><b style={{ width: `${Math.round(item.similaridade * 100)}%` }} /></i></div>
        <div className="precedent-result-content"><header><span className={`status-badge status-${item.status.toLowerCase()}`}>{STATUS_LABELS[item.status] || item.status}</span><small>{typeLabel(item.tipo)}{item.protocolo ? ` · ${item.protocolo}` : ""}</small></header><h3>{item.titulo}</h3><p>{item.resumo || "Sem resumo disponível."}</p><div>{item.justificativas.map((reason) => <span key={reason}>{reason}</span>)}</div></div>
        <button className="secondary-button" onClick={() => onOpenDraft(item.id)}><Eye size={17} /> Abrir minuta</button>
      </article>)}
    </div>}
  </section>;
}

function TemplateManagement({ templates, manager, onTemplatesChange }) {
  const [selectedId, setSelectedId] = useState("");
  const [creatingNew, setCreatingNew] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("TODOS");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ tipo: "INDICACAO", nome: "", estrutura: "" });
  const selected = templates.find((item) => item.id === selectedId);
  const visibleTemplates = templates.filter((item) => {
    const matchesQuery = `${item.nome} ${typeLabel(item.tipo)}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "TODOS" || (status === "ATIVOS" ? item.ativo : !item.ativo);
    return matchesQuery && matchesStatus;
  });

  useEffect(() => {
    if (!creatingNew && !selectedId && templates.length) setSelectedId(templates[0].id);
  }, [creatingNew, selectedId, templates]);

  useEffect(() => {
    if (!selected || creatingNew) return;
    setForm({ tipo: selected.tipo, nome: selected.nome, estrutura: selected.estrutura });
    setError("");
  }, [creatingNew, selected]);

  function startNew() {
    setCreatingNew(true);
    setSelectedId("");
    setForm({ tipo: "INDICACAO", nome: "", estrutura: "" });
    setError("");
  }

  function selectTemplate(id) {
    setCreatingNew(false);
    setSelectedId(id);
  }

  function mergeTemplate(updated) {
    onTemplatesChange((current) => {
      const exists = current.some((item) => item.id === updated.id);
      const next = exists
        ? current.map((item) => (item.id === updated.id ? updated : item))
        : [...current, updated];
      return next.sort((left, right) => left.tipo.localeCompare(right.tipo) || left.nome.localeCompare(right.nome));
    });
  }

  async function save(event) {
    event.preventDefault();
    if (!form.nome.trim() || !form.estrutura.trim()) return;
    setSaving(true);
    setError("");
    try {
      const path = creatingNew
        ? "/api/v1/legislativo/templates"
        : `/api/v1/legislativo/templates/${selected.id}`;
      const updated = await apiRequest(path, {
        method: creatingNew ? "POST" : "PUT",
        body: JSON.stringify(form),
      });
      mergeTemplate(updated);
      setCreatingNew(false);
      setSelectedId(updated.id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await apiRequest(`/api/v1/legislativo/templates/${selected.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ ativo: !selected.ativo }),
      });
      mergeTemplate(updated);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="template-management">
    <aside className="template-list-pane">
      <div className="template-toolbar"><div className="legislative-search"><Search size={17} /><input aria-label="Pesquisar templates" placeholder="Nome ou tipo" value={query} onChange={(event) => setQuery(event.target.value)} /></div><select aria-label="Filtrar templates por status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="TODOS">Todos</option><option value="ATIVOS">Ativos</option><option value="INATIVOS">Inativos</option></select>{manager && <button className="primary-button" onClick={startNew}><Plus size={17} /> Novo template</button>}</div>
      <div className="template-items">{visibleTemplates.map((item) => <button key={item.id} className={selectedId === item.id && !creatingNew ? "template-item active" : "template-item"} onClick={() => selectTemplate(item.id)}><LayoutTemplate size={18} /><span><strong>{item.nome}</strong><small>{typeLabel(item.tipo)}</small></span><span className={item.ativo ? "template-status active" : "template-status"}>{item.ativo ? "Ativo" : "Inativo"}</span></button>)}{!visibleTemplates.length && <div className="template-empty-list"><LayoutTemplate size={24} /><p>Nenhum template encontrado.</p></div>}</div>
    </aside>
    <div className="template-editor-pane">{selected || creatingNew ? <form className="template-editor" onSubmit={save}><header><div><p className="eyebrow">{creatingNew ? "Novo template" : "Template legislativo"}</p><h2>{creatingNew ? "Defina a estrutura" : selected.nome}</h2></div>{selected && manager && <button type="button" className={selected.ativo ? "secondary-button danger" : "secondary-button"} disabled={saving} onClick={toggleStatus}>{selected.ativo ? <EyeOff size={17} /> : <Eye size={17} />}{selected.ativo ? "Desativar" : "Reativar"}</button>}</header><div className="template-editor-grid"><div className="template-fields"><label>Tipo de documento<select aria-label="Tipo de documento" value={form.tipo} disabled={!manager} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Nome<input aria-label="Nome" value={form.nome} disabled={!manager} maxLength={160} onChange={(event) => setForm({ ...form, nome: event.target.value })} placeholder="Ex.: Indicação para serviços urbanos" /></label><label>Estrutura<textarea aria-label="Estrutura" value={form.estrutura} disabled={!manager} maxLength={20000} rows={18} onChange={(event) => setForm({ ...form, estrutura: event.target.value })} placeholder={"EMENTA\nDESTINATÁRIO\nOBJETO\nJUSTIFICATIVA"} /><small>{form.estrutura.length.toLocaleString("pt-BR")} de 20.000 caracteres</small></label></div><section className="template-preview" aria-label="Pré-visualização do template"><div><Eye size={17} /><strong>Pré-visualização</strong></div><h3>{form.nome || "Nome do template"}</h3><span>{typeLabel(form.tipo)}</span><pre>{form.estrutura || "A estrutura do documento aparecerá aqui."}</pre></section></div>{error && <p className="form-error">{error}</p>}{manager && <div className="template-editor-actions">{creatingNew && <button type="button" className="secondary-button" onClick={() => { setCreatingNew(false); setSelectedId(templates[0]?.id || ""); }}>Cancelar</button>}<button className="primary-button" disabled={saving || !form.nome.trim() || !form.estrutura.trim()}><Save size={17} /> {saving ? "Salvando..." : creatingNew ? "Criar template" : "Salvar alterações"}</button></div>}</form> : <div className="legislative-empty"><LayoutTemplate size={34} /><h2>Selecione um template</h2><p>Consulte a estrutura ou crie um novo modelo legislativo.</p></div>}</div>
  </section>;
}

function NormativeSourceManagement() {
  const emptyForm = { tipo: "LEI_MUNICIPAL", titulo: "", referencia: "", trecho: "", jurisdicao: "", url: "", versao: "1", vigenteDesde: "", vigenteAte: "" };
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const selected = items.find((item) => item.id === selectedId);
  const visible = items.filter((item) => `${item.titulo} ${item.referencia} ${item.jurisdicao || ""}`.toLowerCase().includes(query.toLowerCase()));

  const loadSources = useCallback(async () => {
    try {
      const result = await apiRequest("/api/v1/legislativo/fontes-normativas?incluirInativas=true");
      setItems(result.content);
      if (!selectedId && result.content.length) setSelectedId(result.content[0].id);
    } catch (requestError) { setError(requestError.message); }
  }, [selectedId]);

  useEffect(() => { loadSources(); }, [loadSources]);
  useEffect(() => {
    if (!selected || creating) return;
    setForm({ tipo: selected.tipo, titulo: selected.titulo, referencia: selected.referencia, trecho: selected.trecho, jurisdicao: selected.jurisdicao || "", url: selected.url || "", versao: selected.versao, vigenteDesde: selected.vigenteDesde || "", vigenteAte: selected.vigenteAte || "" });
  }, [creating, selected]);

  function startNew() { setCreating(true); setSelectedId(""); setForm(emptyForm); setError(""); }
  function choose(id) { setCreating(false); setSelectedId(id); setError(""); }
  function merge(updated) { setItems((current) => current.some((item) => item.id === updated.id) ? current.map((item) => item.id === updated.id ? updated : item) : [updated, ...current]); }

  async function save(event) {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const updated = await apiRequest(creating ? "/api/v1/legislativo/fontes-normativas" : `/api/v1/legislativo/fontes-normativas/${selectedId}`, { method: creating ? "POST" : "PUT", body: JSON.stringify(form) });
      merge(updated); setCreating(false); setSelectedId(updated.id);
    } catch (requestError) { setError(requestError.message); } finally { setSaving(false); }
  }

  async function toggleStatus() {
    setSaving(true); setError("");
    try {
      const updated = await apiRequest(`/api/v1/legislativo/fontes-normativas/${selected.id}/status`, { method: "PATCH", body: JSON.stringify({ ativo: !selected.ativo }) });
      merge(updated);
    } catch (requestError) { setError(requestError.message); } finally { setSaving(false); }
  }

  return <section className="normative-management">
    <aside className="normative-list-pane"><div className="normative-toolbar"><div className="legislative-search"><Search size={17} /><input aria-label="Pesquisar fontes normativas" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Título, referência ou jurisdição" /></div><button className="primary-button" onClick={startNew}><Plus size={17} /> Nova fonte</button></div><div className="normative-items">{visible.map((item) => <button key={item.id} className={!creating && selectedId === item.id ? "normative-item active" : "normative-item"} onClick={() => choose(item.id)}><BookMarked size={18} /><span><strong>{item.titulo}</strong><small>{item.referencia} · versão {item.versao}</small></span><span className={item.ativo ? "template-status active" : "template-status"}>{item.ativo ? "Ativa" : "Inativa"}</span></button>)}{!visible.length && <div className="template-empty-list"><BookMarked size={24} /><p>Nenhuma fonte cadastrada.</p></div>}</div></aside>
    <div className="normative-editor-pane"><form className="normative-editor" onSubmit={save}><header><div><p className="eyebrow">Catálogo versionado</p><h2>{creating ? "Cadastrar fonte normativa" : selected?.titulo}</h2></div>{selected && !creating && <button type="button" className={selected.ativo ? "secondary-button danger" : "secondary-button"} onClick={toggleStatus}>{selected.ativo ? <EyeOff size={17} /> : <Eye size={17} />}{selected.ativo ? "Desativar" : "Reativar"}</button>}</header><div className="normative-form-grid"><label>Tipo<select aria-label="Tipo da fonte" value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{NORMATIVE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Versão<input aria-label="Versão da fonte" value={form.versao} maxLength={80} onChange={(event) => setForm({ ...form, versao: event.target.value })} /></label><label className="full-width">Título<input aria-label="Título da fonte" value={form.titulo} maxLength={240} onChange={(event) => setForm({ ...form, titulo: event.target.value })} /></label><label>Referência<input aria-label="Referência normativa" value={form.referencia} maxLength={240} onChange={(event) => setForm({ ...form, referencia: event.target.value })} placeholder="Ex.: art. 30, inciso V" /></label><label>Jurisdição<input aria-label="Jurisdição" value={form.jurisdicao} maxLength={120} onChange={(event) => setForm({ ...form, jurisdicao: event.target.value })} /></label><label>Vigente desde<input type="date" value={form.vigenteDesde} onChange={(event) => setForm({ ...form, vigenteDesde: event.target.value })} /></label><label>Vigente até<input type="date" value={form.vigenteAte} onChange={(event) => setForm({ ...form, vigenteAte: event.target.value })} /></label><label className="full-width">URL oficial<input aria-label="URL oficial" type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="https://..." /></label><label className="full-width">Trecho normativo<textarea aria-label="Trecho normativo" rows={10} maxLength={20000} value={form.trecho} onChange={(event) => setForm({ ...form, trecho: event.target.value })} /><small>{form.trecho.length.toLocaleString("pt-BR")} de 20.000 caracteres</small></label></div>{error && <p className="form-error">{error}</p>}<div className="normative-editor-actions">{creating && items.length > 0 && <button type="button" className="secondary-button" onClick={() => choose(items[0].id)}>Cancelar</button>}<button className="primary-button" disabled={saving || !form.titulo.trim() || !form.referencia.trim() || form.trecho.trim().length < 20}><Save size={17} /> {saving ? "Salvando..." : creating ? "Cadastrar fonte" : "Salvar alterações"}</button></div></form></div>
  </section>;
}

function DraftCreationForm({ templates, busy, onCancel, onSubmit }) {
  const [requestId, setRequestId] = useState("");
  const [relatedRequests, setRelatedRequests] = useState([]);
  const [type, setType] = useState("INDICACAO");
  const [templateId, setTemplateId] = useState("");
  const [title, setTitle] = useState("");
  const [facts, setFacts] = useState("");
  const [instructions, setInstructions] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [sourceExcerpt, setSourceExcerpt] = useState("");
  const availableTemplates = templates.filter((item) => item.tipo === type && item.ativo);

  function selectPrimary(option) {
    setRelatedRequests((current) => current.filter((item) => item.id !== option.id));
  }

  function addRelated(option) {
    setRelatedRequests((current) => {
      if (current.length >= 19 || current.some((item) => item.id === option.id)) return current;
      return [...current, option];
    });
  }

  function submit(event) {
    event.preventDefault();
    if (!requestId) return;
    const normativeSources = sourceTitle.trim() ? [{
      titulo: sourceTitle.trim(),
      referencia: sourceReference.trim() || undefined,
      trecho: sourceExcerpt.trim() || undefined,
      validadaPeloUsuario: true,
    }] : [];
    onSubmit({
      requestId,
      payload: {
        tipo: type,
        titulo: title || undefined,
        templateId: templateId || undefined,
        solicitacoesRelacionadasIds: relatedRequests.map((item) => item.id),
        fatosSelecionados: facts.split("\n").map((item) => item.trim()).filter(Boolean),
        instrucoes: instructions || undefined,
        fontesNormativas: normativeSources,
      },
    });
  }
  return <form className="legislative-create" onSubmit={submit}>
    <header><div><h2>Gerar minuta assistida</h2><p>A IA utilizará as solicitações e os fatos selecionados.</p></div><button type="button" className="icon-button" onClick={onCancel} aria-label="Fechar"><XCircle size={19} /></button></header>
    <div className="form-grid">
      <div className="full-width"><RequestSearchSelect value={requestId} label="Solicitação principal" onChange={setRequestId} onSelect={selectPrimary} /></div>
      <section className="legislative-request-links full-width">
        <div className="legislative-source-heading"><strong>Solicitações relacionadas</strong><span>{relatedRequests.length} de 19</span></div>
        {relatedRequests.length < 19 && <RequestSearchSelect value="" label="Adicionar solicitação relacionada" placeholder="Busque outra demanda" clearAfterSelect excludeIds={[requestId, ...relatedRequests.map((item) => item.id)]} onChange={() => {}} onSelect={addRelated} />}
        {!!relatedRequests.length && <div className="legislative-request-chips">{relatedRequests.map((item) => <span key={item.id}><Link2 size={14} /><span><strong>{item.protocolo}</strong>{item.titulo || "Sem título"}</span><button type="button" aria-label={`Remover ${item.protocolo}`} onClick={() => setRelatedRequests((current) => current.filter((candidate) => candidate.id !== item.id))}><XCircle size={16} /></button></span>)}</div>}
      </section>
      <label>Tipo<select value={type} onChange={(event) => { setType(event.target.value); setTemplateId(""); }}>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Template<select value={templateId} onChange={(event) => setTemplateId(event.target.value)}><option value="">Estrutura padrão segura</option>{availableTemplates.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
      <label className="full-width">Título opcional<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={240} /></label>
      <label className="full-width">Fatos selecionados<textarea value={facts} onChange={(event) => setFacts(event.target.value)} rows={4} placeholder="Um fato por linha" /></label>
      <label className="full-width">Instruções de redação<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={3} /></label>
      <div className="legislative-source-heading full-width"><strong>Fonte normativa opcional</strong><span>Inclua somente fontes que você conferiu.</span></div>
      <label>Título da fonte<input value={sourceTitle} onChange={(event) => setSourceTitle(event.target.value)} placeholder="Ex.: Lei Orgânica Municipal" /></label>
      <label>Referência<input value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} placeholder="Ex.: art. 12, inciso II" /></label>
      <label className="full-width">Trecho conferido<textarea value={sourceExcerpt} onChange={(event) => setSourceExcerpt(event.target.value)} rows={3} /></label>
    </div>
    <div className="form-actions"><button type="button" className="secondary-button" onClick={onCancel}>Cancelar</button><button className="primary-button" disabled={!requestId || busy}><FilePlus2 size={18} /> {busy ? "Criando..." : "Gerar rascunho"}</button></div>
  </form>;
}

function DraftEditor({ draft, user, busy, onReview, onChange, onReload, onOpenDraft }) {
  const editable = ["RASCUNHO", "EM_REVISAO"].includes(draft.status) && draft.statusGeracao === "CONCLUIDA";
  const manager = ["admin", "manager"].includes(user.role);
  const [confirmFoundation, setConfirmFoundation] = useState(false);
  const [reason, setReason] = useState("");
  const [protocol, setProtocol] = useState("");
  async function registerProtocol() { if (!protocol.trim()) return; await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/protocolo`, { method: "POST", body: JSON.stringify({ protocolo: protocol }) }); onReload(); }
  async function download(format) { const blob = await apiDownload(`/api/v1/legislativo/minutas/${draft.id}/exportar/${format}`, { method: "GET" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `minuta-${draft.id}.${format}`; anchor.click(); URL.revokeObjectURL(url); }
  if (["PENDENTE", "PROCESSANDO"].includes(draft.statusGeracao)) return <div className="legislative-processing"><RefreshCw className="spin" size={24} /><h2>Gerando minuta localmente</h2><p>O worker está estruturando o rascunho e verificando a fundamentação.</p></div>;
  if (draft.statusGeracao === "FALHOU") return <div className="legislative-processing error"><ShieldAlert size={24} /><h2>Não foi possível gerar</h2><p>{draft.erro}</p></div>;
  return <div className="legislative-editor"><header className="legislative-document-header"><div><span className={`status-badge status-${draft.status.toLowerCase()}`}>{STATUS_LABELS[draft.status]}</span><small>{typeLabel(draft.tipo)} · versão {draft.versaoAtual}</small></div><div className="legislative-downloads"><button className="icon-button" onClick={() => download("docx")} title="Exportar DOCX"><Download size={18} /></button><button className="secondary-button compact" onClick={() => download("pdf")}><FileText size={17} /> PDF</button></div></header><label>Título<input value={draft.titulo || ""} disabled={!editable} onChange={(event) => onChange({ ...draft, titulo: event.target.value })} /></label><label>Conteúdo da minuta<textarea className="legislative-content" value={draft.conteudo || ""} disabled={!editable} onChange={(event) => onChange({ ...draft, conteudo: event.target.value })} /></label><label>Justificativa<textarea value={draft.justificativa || ""} disabled={!editable} rows={5} onChange={(event) => onChange({ ...draft, justificativa: event.target.value })} /></label>
    {!!draft.trechosSemFundamentacao?.length && <section className="foundation-alert"><ShieldAlert size={20} /><div><h3>Fundamentação pendente</h3><p>Revise estes trechos antes da aprovação.</p>{draft.trechosSemFundamentacao.map((item, index) => <div key={`${item.trecho}-${index}`}><strong>{item.trecho}</strong><span>{item.motivo}</span></div>)}</div></section>}
    <FoundationRecovery draft={draft} editable={editable} onReload={onReload} />
    <LinkedRequests requests={draft.solicitacoes || []} />
    <VersionHistory draft={draft} editable={editable} onReload={onReload} />
    <section className="legislative-support"><div><h3>Fontes informadas</h3>{draft.fontes?.length ? draft.fontes.map((item) => <p key={`${item.titulo}-${item.referencia}`}><strong>{item.titulo}</strong><span>{item.referencia || "Sem referência"}</span></p>) : <p className="muted">Nenhuma fonte normativa informada.</p>}</div><PrecedentSuggestions items={draft.proposicoesSemelhantes || []} onOpen={onOpenDraft} /></section>
    {editable && <div className="legislative-review-actions"><label>Motivo da alteração<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: ajuste de redação" /></label><div><button className="secondary-button" disabled={busy} onClick={() => onReview("SALVAR", { titulo: draft.titulo, conteudo: draft.conteudo, justificativa: draft.justificativa, motivo: reason })}><Save size={17} /> Salvar versão</button>{draft.status === "RASCUNHO" && <button className="primary-button" disabled={busy} onClick={() => onReview("SUBMETER", { titulo: draft.titulo, conteudo: draft.conteudo, justificativa: draft.justificativa, motivo: reason || "Submissão para revisão" })}><Send size={17} /> Submeter</button>}</div></div>}
    {draft.status === "EM_REVISAO" && manager && <section className="approval-band"><label><input type="checkbox" checked={confirmFoundation} onChange={(event) => setConfirmFoundation(event.target.checked)} /> Confirmo que revisei os fatos, a competência e a fundamentação</label><div><button className="secondary-button danger" disabled={busy || !reason} onClick={() => onReview("REJEITAR", { motivo: reason })}><XCircle size={17} /> Rejeitar</button><button className="primary-button" disabled={busy || !confirmFoundation} onClick={() => onReview("APROVAR", { confirmarFundamentacao: true })}><CheckCircle2 size={17} /> Aprovar minuta</button></div></section>}
    {draft.status === "APROVADA" && manager && !draft.protocolo && <section className="protocol-band"><div><h3>Registrar protocolo externo</h3><p>O GabFlow nunca protocola automaticamente.</p></div><input aria-label="Número do protocolo" value={protocol} onChange={(event) => setProtocol(event.target.value)} placeholder="Número informado pelo sistema oficial" /><button className="primary-button" disabled={!protocol.trim()} onClick={registerProtocol}><CheckCircle2 size={17} /> Registrar</button></section>}
    {draft.protocolo && <TramitationPanel draft={draft} manager={manager} onReload={onReload} />}
  </div>;
}

function FoundationRecovery({ draft, editable, onReload }) {
  const [result, setResult] = useState(draft.fundamentacaoSugerida || null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(draft.fundamentacaoSugerida || null);
    setSelectedIds([]);
    setReason("");
  }, [draft.id, draft.fundamentacaoSugerida]);

  async function retrieve() {
    setLoading(true); setError("");
    try {
      const value = await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/fundamentacao/recuperar`, { method: "POST", body: JSON.stringify({}) });
      setResult(value); setSelectedIds([]);
    } catch (requestError) { setError(requestError.message); } finally { setLoading(false); }
  }

  function toggle(id) {
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  }

  async function apply() {
    setLoading(true); setError("");
    try {
      await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/fundamentacao/aplicar`, { method: "POST", body: JSON.stringify({ fonteIds: selectedIds, motivo: reason.trim() }) });
      await onReload();
    } catch (requestError) { setError(requestError.message); } finally { setLoading(false); }
  }

  return <section className="foundation-recovery">
    <header><div><Sparkles size={20} /><span><h3>Fundamentação sugerida</h3><p>Recuperação local preparada para o futuro RAG. Nenhuma fonte é aplicada automaticamente.</p></span></div><button className="secondary-button" disabled={loading} onClick={retrieve}><RefreshCw size={17} className={loading ? "spin" : ""} /> {result ? "Buscar novamente" : "Buscar fundamentação"}</button></header>
    {result && <div className="foundation-recovery-meta"><span>{result.modelo}{result.fallbackUtilizado ? " · fallback lexical" : " · embeddings locais"}</span><span>{result.totalCandidatos} fontes avaliadas</span><span>limiar {Math.round(result.limiar * 100)}%</span></div>}
    {result && !result.fontes?.length && <div className="foundation-recovery-empty"><BookMarked size={22} /><p>Nenhuma fonte vigente atingiu o grau mínimo de aderência.</p></div>}
    {!!result?.fontes?.length && <div className="foundation-suggestions">{result.fontes.map((item) => <article key={item.id} className={selectedIds.includes(item.id) ? "selected" : ""}><label><input type="checkbox" disabled={!editable} checked={selectedIds.includes(item.id)} onChange={() => toggle(item.id)} /><span><strong>{item.titulo}</strong><small>{item.referencia} · versão {item.versao}{item.jurisdicao ? ` · ${item.jurisdicao}` : ""}</small></span><b>{Math.round(item.pontuacao * 100)}%</b></label><p>{item.trecho}</p><footer><span>{item.justificativas?.join(" · ")}</span>{item.url && <a href={item.url} target="_blank" rel="noreferrer">Fonte oficial <ExternalLink size={13} /></a>}</footer></article>)}</div>}
    {editable && !!result?.fontes?.length && <div className="foundation-apply"><label>Motivo da seleção<input aria-label="Motivo da fundamentação" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: dispositivos aderentes ao objeto da minuta" /></label><button className="primary-button" disabled={loading || !selectedIds.length || !reason.trim()} onClick={apply}><CheckCircle2 size={17} /> Aplicar fontes selecionadas</button></div>}
    {error && <p className="form-error">{error}</p>}
  </section>;
}

function PrecedentSuggestions({ items, onOpen }) {
  return <div className="draft-precedents"><h3>Proposições semelhantes</h3>{items.length ? items.map((item) => <button key={item.id} onClick={() => onOpen(item.id)}><span><strong>{item.titulo}</strong><small>{typeLabel(item.tipo)} · {STATUS_LABELS[item.status] || item.status}</small></span><b>{Math.round(item.similaridade * 100)}%</b></button>) : <p className="muted">Nenhum precedente semelhante encontrado.</p>}</div>;
}

function LinkedRequests({ requests }) {
  return <section className="linked-requests">
    <header><div><Link2 size={18} /><h3>Solicitações vinculadas</h3></div><span>{requests.length}</span></header>
    <div>{requests.map((item) => <article key={item.id}><span className={item.principal ? "linked-request-type primary" : "linked-request-type"}>{item.principal ? "Principal" : "Relacionada"}</span><strong>{item.protocolo}</strong><p>{item.titulo || "Sem título"}</p></article>)}</div>
  </section>;
}

function VersionHistory({ draft, editable, onReload }) {
  const versions = draft.versoes || [];
  const [fromVersion, setFromVersion] = useState("");
  const [toVersion, setToVersion] = useState("");
  const [preview, setPreview] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [restoreVersion, setRestoreVersion] = useState(null);
  const [restoreReason, setRestoreReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const current = String(draft.versaoAtual || "");
    const previous = versions.find((item) => item.numero !== draft.versaoAtual);
    setFromVersion(previous ? String(previous.numero) : current);
    setToVersion(current);
    setPreview(null);
    setComparison(null);
    setRestoreVersion(null);
    setRestoreReason("");
    setError("");
  }, [draft.id, draft.versaoAtual]); // eslint-disable-line react-hooks/exhaustive-deps

  async function viewVersion(number) {
    setLoading(true);
    setError("");
    try {
      const value = await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/versoes/${number}`);
      setPreview(value);
      setComparison(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function compareVersions() {
    if (!fromVersion || !toVersion || fromVersion === toVersion) return;
    setLoading(true);
    setError("");
    try {
      const value = await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/comparacao?de=${fromVersion}&para=${toVersion}`);
      setComparison(value);
      setPreview(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function restore() {
    if (!restoreVersion || !restoreReason.trim()) return;
    setLoading(true);
    setError("");
    try {
      await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/versoes/${restoreVersion}/restaurar`, {
        method: "POST",
        body: JSON.stringify({ motivo: restoreReason.trim() }),
      });
      await onReload();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  if (!versions.length) return null;
  return <section className="version-history">
    <header className="version-history-header">
      <div><History size={19} /><span><strong>Histórico de versões</strong><small>Snapshots imutáveis da minuta</small></span></div>
      <span>{versions.length} {versions.length === 1 ? "versão" : "versões"}</span>
    </header>
    <div className="version-history-layout">
      <div className="version-list" aria-label="Versões da minuta">
        {versions.map((item) => <button key={item.id || item.numero} className={preview?.numero === item.numero ? "active" : ""} onClick={() => viewVersion(item.numero)}>
          <span className="version-number">v{item.numero}</span>
          <span><strong>{item.motivo}</strong><small>{item.autor} · {formatDateTime(item.criadaEm)}</small></span>
          {item.numero === draft.versaoAtual && <span className="version-current">Atual</span>}
        </button>)}
      </div>
      <div className="version-compare-controls">
        <label>Versão base<select value={fromVersion} onChange={(event) => setFromVersion(event.target.value)}>{versions.map((item) => <option key={item.numero} value={item.numero}>Versão {item.numero}</option>)}</select></label>
        <label>Comparar com<select value={toVersion} onChange={(event) => setToVersion(event.target.value)}>{versions.map((item) => <option key={item.numero} value={item.numero}>Versão {item.numero}</option>)}</select></label>
        <button className="secondary-button" disabled={loading || !fromVersion || fromVersion === toVersion} onClick={compareVersions}><GitCompare size={17} /> Comparar</button>
      </div>
    </div>
    {error && <p className="form-error">{error}</p>}
    {preview && <VersionPreview version={preview} currentVersion={draft.versaoAtual} editable={editable} loading={loading} onRequestRestore={setRestoreVersion} />}
    {comparison && <VersionComparison comparison={comparison} />}
    {restoreVersion && <div className="version-restore-confirmation">
      <div><RotateCcw size={19} /><span><strong>Restaurar a versão {restoreVersion}?</strong><small>O conteúdo atual será preservado e a restauração criará uma nova versão.</small></span></div>
      <label>Motivo da restauração<input autoFocus value={restoreReason} maxLength={500} onChange={(event) => setRestoreReason(event.target.value)} placeholder="Descreva por que esta versão deve voltar a ser usada" /></label>
      <div><button className="secondary-button" onClick={() => { setRestoreVersion(null); setRestoreReason(""); }}>Cancelar</button><button className="primary-button" disabled={loading || !restoreReason.trim()} onClick={restore}><RotateCcw size={17} /> {loading ? "Restaurando..." : "Confirmar restauração"}</button></div>
    </div>}
  </section>;
}

function VersionPreview({ version, currentVersion, editable, loading, onRequestRestore }) {
  return <div className="version-preview">
    <header><div><Eye size={17} /><strong>Versão {version.numero}</strong></div><small>{version.autor} · {formatDateTime(version.criadaEm)}</small></header>
    <div className="version-preview-field"><span>Título</span><p>{version.titulo}</p></div>
    <div className="version-preview-field"><span>Conteúdo</span><pre>{version.conteudo}</pre></div>
    {version.justificativa && <div className="version-preview-field"><span>Justificativa</span><pre>{version.justificativa}</pre></div>}
    {editable && version.numero !== currentVersion && <footer><button className="secondary-button" disabled={loading} onClick={() => onRequestRestore(version.numero)}><RotateCcw size={17} /> Restaurar esta versão</button></footer>}
  </div>;
}

function VersionComparison({ comparison }) {
  const labels = {
    titulo: "Título",
    conteudo: "Conteúdo",
    justificativa: "Justificativa",
    fundamentacaoNormativa: "Fundamentação normativa",
    trechosSemFundamentacao: "Pendências de fundamentação",
  };
  return <div className="version-comparison">
    <header><div><GitCompare size={18} /><strong>Versão {comparison.de} → versão {comparison.para}</strong></div><span><b>+{comparison.linhasAdicionadas}</b><b>−{comparison.linhasRemovidas}</b></span></header>
    {!comparison.camposAlterados.length && <p className="muted">As versões possuem o mesmo conteúdo.</p>}
    {comparison.camposAlterados.map((name) => {
      const field = comparison.campos[name];
      const changedLines = field.diferencas.filter((line) => line.tipo !== "IGUAL");
      return <section key={name}><div><strong>{labels[name] || name}</strong><small>+{field.linhasAdicionadas} · −{field.linhasRemovidas}</small></div><pre>{changedLines.map((line, index) => <span key={`${line.tipo}-${index}`} className={line.tipo === "ADICIONADA" ? "added" : "removed"}>{line.tipo === "ADICIONADA" ? "+" : "−"} {line.texto || " "}</span>)}</pre></section>;
    })}
  </div>;
}

function TramitationPanel({ draft, manager, onReload }) {
  const [movement, setMovement] = useState({
    status: "DISTRIBUIDA",
    etapa: "",
    destino: "",
    referenciaExterna: "",
    observacoes: "",
    ocorridaEm: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!movement.etapa.trim()) return;
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...movement,
        etapa: movement.etapa.trim(),
        ocorridaEm: movement.ocorridaEm
          ? new Date(movement.ocorridaEm).toISOString()
          : undefined,
      };
      await apiRequest(`/api/v1/legislativo/minutas/${draft.id}/tramitacoes`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMovement({
        status: "DISTRIBUIDA",
        etapa: "",
        destino: "",
        referenciaExterna: "",
        observacoes: "",
        ocorridaEm: "",
      });
      await onReload();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="tramitation-section">
    <header className="tramitation-header">
      <div><Milestone size={19} /><span><strong>Tramitação legislativa</strong><small>Protocolo {draft.protocolo}</small></span></div>
      <span className="tramitation-current">{TRAMITATION_STATUS_LABELS[draft.statusTramitacao] || draft.statusTramitacao}</span>
    </header>
    <div className="tramitation-timeline">
      {(draft.tramitacoes || []).map((item) => <article key={item.id}>
        <span className="tramitation-marker"><Clock3 size={14} /></span>
        <div className="tramitation-event-heading"><strong>{TRAMITATION_STATUS_LABELS[item.status] || item.status}</strong><time>{formatDateTime(item.ocorridaEm)}</time></div>
        <p>{item.etapa}</p>
        {(item.destino || item.referenciaExterna) && <small>{[item.destino, item.referenciaExterna].filter(Boolean).join(" · ")}</small>}
        {item.observacoes && <p className="tramitation-notes">{item.observacoes}</p>}
      </article>)}
    </div>
    {manager && <form className="tramitation-form" onSubmit={submit}>
      <h3>Registrar novo andamento</h3>
      <div className="tramitation-form-grid">
        <label>Status<select value={movement.status} onChange={(event) => setMovement({ ...movement, status: event.target.value })}>{Object.entries(TRAMITATION_STATUS_LABELS).filter(([value]) => value !== "PROTOCOLADA").map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Data e hora<input type="datetime-local" value={movement.ocorridaEm} onChange={(event) => setMovement({ ...movement, ocorridaEm: event.target.value })} /></label>
        <label className="full-width">Etapa<input value={movement.etapa} maxLength={160} onChange={(event) => setMovement({ ...movement, etapa: event.target.value })} placeholder="Ex.: Comissão de Constituição e Justiça" /></label>
        <label>Destino<input value={movement.destino} maxLength={180} onChange={(event) => setMovement({ ...movement, destino: event.target.value })} placeholder="Órgão ou comissão" /></label>
        <label>Referência externa<input value={movement.referenciaExterna} maxLength={180} onChange={(event) => setMovement({ ...movement, referenciaExterna: event.target.value })} placeholder="Número do movimento" /></label>
        <label className="full-width">Observações<textarea rows={3} value={movement.observacoes} onChange={(event) => setMovement({ ...movement, observacoes: event.target.value })} /></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="tramitation-form-actions"><button className="primary-button" disabled={saving || !movement.etapa.trim()}><Milestone size={17} /> {saving ? "Registrando..." : "Registrar andamento"}</button></div>
    </form>}
  </section>;
}

function StatusDot({ generation }) { return <span className={`generation-dot generation-${generation.toLowerCase()}`} title={generation} />; }
function typeLabel(value) { return TYPES.find(([type]) => type === value)?.[1] || value; }
function formatDateTime(value) { return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : ""; }
