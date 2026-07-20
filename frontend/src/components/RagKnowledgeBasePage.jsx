import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  FileText,
  History,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";

const TYPES = [
  ["LEGISLACAO", "Legislação"], ["ATO", "Ato"], ["ATA", "Ata"],
  ["RESPOSTA_ORGAO", "Resposta de órgão"], ["CONTRATO", "Contrato"],
  ["PROCESSO", "Processo"], ["PROCEDIMENTO_INTERNO", "Procedimento interno"],
  ["OUTRO", "Outro"],
];
const INGESTION = { PENDENTE: "Na fila", PROCESSANDO: "Processando", INDEXADO: "Indexado", FALHOU: "Falhou" };
const LIFECYCLE = { RASCUNHO: "Rascunho", VIGENTE: "Vigente", HISTORICO: "Histórico", REVOGADO: "Revogado" };
const EMPTY_FORM = { titulo: "", tipo: "LEGISLACAO", orgao: "", nivelAcesso: "INTERNO", versao: "1", vigenteDesde: "", vigenteAte: "", urlFonte: "" };
const RAG_MAX_FILE_BYTES = 25 * 1024 * 1024;
const RAG_ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"];

export function RagKnowledgeBasePage() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [addingVersion, setAddingVersion] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
      const result = await apiRequest(`/api/v1/rag/documentos${suffix}`);
      setItems(result.content);
    } catch (requestError) { setError(requestError.message); }
  }, [query]);
  const loadDetail = useCallback(async (id) => {
    const value = await apiRequest(`/api/v1/rag/documentos/${id}`);
    setSelected(value);
    setItems((current) => current.map((item) => item.id === id ? { ...item, ...value } : item));
    return value;
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!selected?.versoes?.some((item) => ["PENDENTE", "PROCESSANDO"].includes(item.statusIngestao))) return undefined;
    const timer = setInterval(() => loadDetail(selected.id), 2500);
    return () => clearInterval(timer);
  }, [loadDetail, selected]);

  function startNew() { setCreating(true); setAddingVersion(false); setSelected(null); setForm(EMPTY_FORM); setFile(null); setError(""); }
  function startVersion() { setAddingVersion(true); setCreating(false); setForm({ ...EMPTY_FORM, versao: String((selected?.quantidadeVersoes || 0) + 1) }); setFile(null); }
  function selectFile(nextFile) {
    if (!nextFile) { setFile(null); return; }
    const validationError = validateRagFile(nextFile);
    if (validationError) {
      setFile(null);
      setError(validationError);
      return;
    }
    setError("");
    setFile(nextFile);
  }

  async function submit(event) {
    event.preventDefault();
    const validationError = validateRagFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy(true); setError("");
    try {
      const body = new FormData();
      Object.entries(form).forEach(([key, value]) => value && body.append(key, value));
      body.append("arquivo", file);
      const path = addingVersion ? `/api/v1/rag/documentos/${selected.id}/versoes` : "/api/v1/rag/documentos";
      const value = await apiRequest(path, { method: "POST", body });
      if (addingVersion) await loadDetail(selected.id);
      else {
        setSelected(value);
        setItems((current) => current.some((item) => item.id === value.id)
          ? current.map((item) => item.id === value.id ? value : item)
          : [value, ...current]);
      }
      setCreating(false); setAddingVersion(false); setFile(null);
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  async function changeState(version, state) {
    setBusy(true); setError("");
    try {
      await apiRequest(`/api/v1/rag/documentos/${selected.id}/versoes/${version.id}/estado`, { method: "PATCH", body: JSON.stringify({ estado: state }) });
      await loadDetail(selected.id);
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  async function reprocess(version) {
    setBusy(true); setError("");
    try {
      await apiRequest(`/api/v1/rag/documentos/${selected.id}/versoes/${version.id}/reprocessar`, { method: "POST" });
      await loadDetail(selected.id);
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  return <>
    <section className="page-heading rag-heading"><div><p className="eyebrow">Assistente RAG</p><h1>Base documental</h1><p>Ingestão versionada, rastreável e isolada por gabinete.</p></div><button className="primary-button" onClick={startNew}><Plus size={18} /> Novo documento</button></section>
    {error && <div className="rag-error-banner" role="alert"><AlertTriangle size={18} /><span><strong>Ação não concluída</strong><small>{error}</small></span></div>}
    <section className="rag-workspace">
      <aside className="rag-list"><div className="rag-search"><Search size={17} /><input aria-label="Pesquisar documentos RAG" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Título, tipo ou órgão" /><button className="icon-button" title="Atualizar" onClick={load}><RefreshCw size={17} /></button></div>{items.map((item) => <button key={item.id} className={selected?.id === item.id ? "rag-list-item active" : "rag-list-item"} onClick={() => { setCreating(false); setAddingVersion(false); loadDetail(item.id); }}><Database size={18} /><span><strong>{item.titulo}</strong><small>{typeLabel(item.tipo)} · {item.quantidadeVersoes} versão(ões)</small></span>{item.ultimaVersao && <i className={`rag-status status-${item.ultimaVersao.statusIngestao.toLowerCase()}`}>{INGESTION[item.ultimaVersao.statusIngestao]}</i>}</button>)}{!items.length && <div className="rag-empty-list"><Database size={26} /><p>Nenhum documento cadastrado.</p></div>}</aside>
      <div className="rag-content">{creating || addingVersion ? <RagUploadForm form={form} setForm={setForm} file={file} setFile={selectFile} busy={busy} addingVersion={addingVersion} document={selected} onCancel={() => { setCreating(false); setAddingVersion(false); }} onSubmit={submit} /> : selected ? <RagDocumentDetail document={selected} busy={busy} onAddVersion={startVersion} onChangeState={changeState} onReprocess={reprocess} /> : <div className="rag-empty"><Database size={36} /><h2>Selecione um documento</h2><p>Consulte versões, processamento e proveniência.</p></div>}</div>
    </section>
  </>;
}

function RagUploadForm({ form, setForm, file, setFile, busy, addingVersion, document, onCancel, onSubmit }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  return <form className="rag-upload-form" onSubmit={onSubmit}><header><div><p className="eyebrow">{addingVersion ? "Nova versão" : "Novo documento"}</p><h2>{addingVersion ? document.titulo : "Adicionar à base documental"}</h2></div></header><div className="rag-form-grid">{!addingVersion && <><label className="full-width">Título<input aria-label="Título do documento" value={form.titulo} maxLength={240} onChange={(event) => setForm({ ...form, titulo: event.target.value })} /></label><label>Tipo<select aria-label="Tipo documental" value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Nível de acesso<select aria-label="Nível de acesso" value={form.nivelAcesso} onChange={(event) => setForm({ ...form, nivelAcesso: event.target.value })}><option value="INTERNO">Interno</option><option value="RESTRITO">Restrito a gestores</option></select></label><label className="full-width">Órgão<input aria-label="Órgão" value={form.orgao} maxLength={180} onChange={(event) => setForm({ ...form, orgao: event.target.value })} /></label></>}<label>Versão<input aria-label="Versão documental" value={form.versao} maxLength={80} onChange={(event) => setForm({ ...form, versao: event.target.value })} /></label><label>URL oficial<input type="url" aria-label="URL da fonte" value={form.urlFonte} onChange={(event) => setForm({ ...form, urlFonte: event.target.value })} /></label><label>Vigente desde<input type="date" value={form.vigenteDesde} onChange={(event) => setForm({ ...form, vigenteDesde: event.target.value })} /></label><label>Vigente até<input type="date" value={form.vigenteAte} onChange={(event) => setForm({ ...form, vigenteAte: event.target.value })} /></label></div><input ref={inputRef} hidden type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={(event) => setFile(event.target.files[0] || null)} /><button type="button" className={`rag-dropzone ${dragging ? "dragging" : ""}`} onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0] || null); }}><Upload size={24} /><span><strong>{file ? file.name : "Arraste o documento para cá"}</strong><small>PDF, DOCX, TXT, PNG ou JPEG · máximo de 25 MB</small></span></button><div className="rag-form-actions"><button type="button" className="secondary-button" onClick={onCancel}>Cancelar</button><button className="primary-button" disabled={busy || !file || (!addingVersion && !form.titulo.trim())}><Upload size={17} /> {busy ? "Enviando..." : "Enviar para ingestão"}</button></div></form>;
}

function RagDocumentDetail({ document, busy, onAddVersion, onChangeState, onReprocess }) {
  return <div className="rag-detail"><header><div><span className="rag-document-icon"><Database size={22} /></span><span><p className="eyebrow">{typeLabel(document.tipo)}</p><h2>{document.titulo}</h2><small>{document.orgao || "Sem órgão"} · {document.nivelAcesso === "RESTRITO" ? "Restrito a gestores" : "Interno"}</small></span></div><button className="secondary-button" onClick={onAddVersion}><Plus size={17} /> Nova versão</button></header><section className="rag-governance"><ShieldCheck size={19} /><p>Arquivos são tratados como dados. Cada versão preserva checksum, vigência, origem e modelo de embeddings.</p></section><div className="rag-versions"><h3><History size={18} /> Histórico de versões</h3>{document.versoes.map((version) => <article key={version.id}><header><div><FileText size={18} /><span><strong>Versão {version.versao}</strong><small>{version.arquivo} · {formatBytes(version.tamanhoBytes)}</small></span></div><div><span className={`rag-lifecycle lifecycle-${version.estado.toLowerCase()}`}>{LIFECYCLE[version.estado]}</span><span className={`rag-status status-${version.statusIngestao.toLowerCase()}`}>{INGESTION[version.statusIngestao]}</span></div></header><dl><div><dt>Checksum</dt><dd title={version.checksum}>{version.checksum.slice(0, 16)}…</dd></div><div><dt>Vigência</dt><dd>{[version.vigenteDesde, version.vigenteAte].filter(Boolean).join(" a ") || "Não informada"}</dd></div><div><dt>Indexação</dt><dd>{version.fragmentos} fragmentos · {version.paginas || 0} página(s)</dd></div><div><dt>Modelo</dt><dd>{version.modeloEmbedding || "Aguardando"}</dd></div></dl>{version.erro && <p className="rag-version-error"><AlertTriangle size={15} /> {version.erro}</p>}<footer><a className="secondary-button compact" href={version.downloadUrl}><Download size={16} /> Arquivo</a>{version.statusIngestao === "FALHOU" && <button className="secondary-button compact" disabled={busy} onClick={() => onReprocess(version)}><RefreshCw size={16} /> Reprocessar</button>}{version.statusIngestao === "INDEXADO" && version.estado !== "VIGENTE" && <button className="primary-button compact" disabled={busy} onClick={() => onChangeState(version, "VIGENTE")}><CheckCircle2 size={16} /> Publicar</button>}{version.estado === "VIGENTE" && <button className="secondary-button danger compact" disabled={busy} onClick={() => onChangeState(version, "REVOGADO")}>Revogar</button>}</footer></article>)}</div></div>;
}

function typeLabel(value) { return TYPES.find(([id]) => id === value)?.[1] || value; }
function validateRagFile(nextFile) {
  if (!nextFile) return "Selecione um arquivo para enviar à base documental.";
  const fileName = nextFile.name?.toLowerCase() || "";
  if (!RAG_ACCEPTED_EXTENSIONS.some((extension) => fileName.endsWith(extension))) {
    return "Formato não permitido. Envie um arquivo PDF, DOCX, TXT, PNG ou JPEG.";
  }
  if (nextFile.size > RAG_MAX_FILE_BYTES) {
    return `O arquivo selecionado tem ${formatBytes(nextFile.size)}. O limite da base documental RAG é 25 MB. Reduza, compacte ou divida o documento antes de enviar.`;
  }
  return "";
}
function formatBytes(value) {
  const bytes = value || 0;
  if (bytes >= 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
