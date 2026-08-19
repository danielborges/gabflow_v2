import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileText,
  History,
  Info,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api";
import { FeatureHeader } from "./FeatureHeader";

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
const PAGE_SIZES = [5, 10, 20, 50];
const MEMORY_STATES = {
  PENDENTE: "Sincronizando", ATIVA: "Disponível", QUARENTENA: "Requer revisão",
  INELEGIVEL: "Não elegível", EXPIRADA: "Expirada", ERRO: "Falha na sincronização",
  EXCLUIDA: "Descartada",
};
const MEMORY_PURPOSES = {
  ATENDIMENTO_E_PLANEJAMENTO_LEGISLATIVO: "Apoiar o atendimento ao cidadão e o planejamento de iniciativas legislativas.",
  ACOMPANHAMENTO_DE_ENCAMINHAMENTOS_E_RESPOSTAS_OFICIAIS: "Acompanhar encaminhamentos realizados pelo gabinete e as respostas oficiais recebidas.",
  ACOMPANHAMENTO_DA_TRAMITACAO_LEGISLATIVA: "Acompanhar a tramitação de proposições e identificar avanços, prazos e pendências.",
  EVIDENCIA_DOCUMENTAL_REVISADA_DE_ATENDIMENTO: "Disponibilizar documentos de atendimento revisados como evidências para consultas e decisões.",
  EVIDENCIA_DE_AUDIO_REVISADA_DE_ATENDIMENTO: "Disponibilizar transcrições de áudio revisadas como evidências dos atendimentos realizados.",
  MEMORIA_DE_COMPROMISSOS_E_VISITAS_REALIZADOS: "Registrar compromissos e visitas realizados para apoiar o acompanhamento das ações do gabinete.",
  MEMORIA_DE_FISCALIZACAO_E_CONTROLE: "Apoiar o acompanhamento de fiscalizações, providências e resultados de controle.",
  PLANEJAMENTO_TEMATICO_AGREGADO: "Reunir informações relacionadas por tema para apoiar o planejamento e a definição de prioridades.",
  MEMORIA_E_PRODUCAO_LEGISLATIVA: "Preservar o contexto da produção legislativa para apoiar análises e novas iniciativas.",
};

export function RagKnowledgeBasePage() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [catalogType, setCatalogType] = useState("documents");
  const [memories, setMemories] = useState([]);
  const [selectedMemory, setSelectedMemory] = useState(null);
  const [memoriesLoaded, setMemoriesLoaded] = useState(false);
  const [loadingMemories, setLoadingMemories] = useState(false);
  const [query, setQuery] = useState("");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [sort, setSort] = useState({ key: "titulo", direction: "asc" });
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [creating, setCreating] = useState(false);
  const [addingVersion, setAddingVersion] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
      const result = await apiRequest(`/api/v1/rag/documentos${suffix}`);
      setItems(result.content);
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }, [query]);
  const loadDetail = useCallback(async (id, { silent = false } = {}) => {
    if (!silent) setLoadingDetail(true);
    try {
      const value = await apiRequest(`/api/v1/rag/documentos/${id}`);
      setSelected(value);
      setItems((current) => current.map((item) => item.id === id ? { ...item, ...value } : item));
      return value;
    } catch (requestError) {
      setError(requestError.message);
      return null;
    } finally { if (!silent) setLoadingDetail(false); }
  }, []);
  const loadMemories = useCallback(async () => {
    setLoadingMemories(true);
    try {
      const result = await apiRequest("/api/v1/rag/fontes-operacionais");
      setMemories(result.content || []);
      setMemoriesLoaded(true);
    } catch (requestError) { setError(requestError.message); }
    finally { setLoadingMemories(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(0); }, [query, memoryQuery, pageSize, catalogType]);
  useEffect(() => {
    if (!selected?.versoes?.some((item) => ["PENDENTE", "PROCESSANDO"].includes(item.statusIngestao))) return undefined;
    const timer = setInterval(() => loadDetail(selected.id, { silent: true }), 2500);
    return () => clearInterval(timer);
  }, [loadDetail, selected]);

  function startNew() { setCatalogType("documents"); setCreating(true); setAddingVersion(false); setSelected(null); setSelectedMemory(null); setForm(EMPTY_FORM); setFile(null); setError(""); }
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

  async function reprocessMemory(memory) {
    setBusy(true); setError("");
    try {
      const value = await apiRequest(`/api/v1/rag/fontes-operacionais/${memory.id}/reprocessar`, { method: "POST" });
      setMemories((current) => current.map((item) => item.id === value.id ? value : item));
      setSelectedMemory(value);
    } catch (requestError) { setError(requestError.message); } finally { setBusy(false); }
  }

  const filteredMemories = useMemo(() => {
    const normalized = memoryQuery.trim().toLocaleLowerCase("pt-BR");
    if (!normalized) return memories;
    return memories.filter((item) => [
      item.titulo, item.origem?.moduloNome, item.origem?.entidadeNome,
      item.estadoNome, item.finalidade,
    ].some((value) => String(value || "").toLocaleLowerCase("pt-BR").includes(normalized)));
  }, [memories, memoryQuery]);
  const catalogItems = catalogType === "documents" ? items : filteredMemories;
  const sortedItems = useMemo(() => [...catalogItems].sort((left, right) => {
    const leftValue = catalogSortValue(left, sort.key, catalogType);
    const rightValue = catalogSortValue(right, sort.key, catalogType);
    const comparison = typeof leftValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue), "pt-BR", { sensitivity: "base" });
    return sort.direction === "asc" ? comparison : -comparison;
  }), [catalogItems, sort, catalogType]);
  const totalPages = Math.max(1, Math.ceil(sortedItems.length / pageSize));
  const visibleItems = sortedItems.slice(page * pageSize, (page + 1) * pageSize);

  useEffect(() => {
    if (page >= totalPages) setPage(totalPages - 1);
  }, [page, totalPages]);

  function changeSort(key) {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
      : { key, direction: "asc" });
    setPage(0);
  }

  function openDocument(id) {
    setCreating(false);
    setAddingVersion(false);
    setSelectedMemory(null);
    loadDetail(id);
  }

  function openMemory(memory) {
    setCreating(false);
    setAddingVersion(false);
    setSelected(null);
    setSelectedMemory(memory);
  }

  function changeCatalog(nextType) {
    setCatalogType(nextType);
    setCreating(false);
    setAddingVersion(false);
    if (nextType === "documents") setSelectedMemory(null);
    else setSelected(null);
    setSort({ key: "titulo", direction: "asc" });
    if (nextType === "memories" && !memoriesLoaded) loadMemories();
  }

  return <>
    <FeatureHeader className="rag-heading" eyebrow="Inteligência do gabinete" title="Base de conhecimento" description="Documentos do gabinete e memórias geradas pelo GabFlow, com origem e vigência controladas."><button className="primary-button" onClick={startNew}><Plus size={18} /> Novo documento</button></FeatureHeader>
    {error && <div className="rag-error-banner" role="alert"><AlertTriangle size={18} /><span><strong>Ação não concluída</strong><small>{error}</small></span></div>}
    <section className="rag-workspace">
      <div className={`rag-content ${creating || addingVersion ? "rag-content-form" : ""}`} aria-live="polite">{creating || addingVersion ? <RagUploadForm form={form} setForm={setForm} file={file} setFile={selectFile} busy={busy} addingVersion={addingVersion} document={selected} onCancel={() => { setCreating(false); setAddingVersion(false); }} onSubmit={submit} /> : loadingDetail ? <div className="rag-empty rag-workspace-loading"><RefreshCw className="spin" size={28} /><h2>Carregando documento</h2><p>Buscando revisões e informações de proveniência.</p></div> : selected ? <RagDocumentDetail document={selected} busy={busy} onAddVersion={startVersion} onChangeState={changeState} onReprocess={reprocess} /> : selectedMemory ? <RagMemoryDetail memory={selectedMemory} busy={busy} onReprocess={reprocessMemory} /> : <div className="rag-empty">{catalogType === "documents" ? <Database size={36} /> : <BrainCircuit size={36} />}<h2>{catalogType === "documents" ? "Área de trabalho documental" : "Memória automática do GabFlow"}</h2><p>{catalogType === "documents" ? "Selecione um documento abaixo para consultar revisões, vigência e proveniência." : "Selecione uma memória para consultar sua origem, disponibilidade e prazo de retenção."}</p></div>}</div>
      <section className="rag-catalog" aria-labelledby="rag-catalog-title">
        <nav className="rag-catalog-tabs" aria-label="Fontes da base de conhecimento">
          <button type="button" className={catalogType === "documents" ? "active" : ""} aria-pressed={catalogType === "documents"} onClick={() => changeCatalog("documents")}><Database size={17} /><span><strong>Documentos do gabinete</strong><small>Arquivos adicionados e revisados pelo gabinete</small></span></button>
          <button type="button" className={catalogType === "memories" ? "active" : ""} aria-pressed={catalogType === "memories"} onClick={() => changeCatalog("memories")}><BrainCircuit size={17} /><span><strong>Memórias do GabFlow</strong><small>Conhecimento gerado automaticamente pelos módulos</small></span></button>
        </nav>
        <header className="rag-catalog-header">
          <div><p className="eyebrow">{catalogType === "documents" ? "Base documental" : "Conhecimento automático"}</p><h2 id="rag-catalog-title">{catalogType === "documents" ? "Documentos do gabinete" : "Memórias geradas pelo GabFlow"}</h2><span>{sortedItems.length} {sortedItems.length === 1 ? "item encontrado" : "itens encontrados"}</span></div>
          <div className="rag-table-controls">
            <label className="rag-search"><Search size={17} /><span className="sr-only">Pesquisar</span><input aria-label={catalogType === "documents" ? "Pesquisar documentos RAG" : "Pesquisar memórias do GabFlow"} value={catalogType === "documents" ? query : memoryQuery} onChange={(event) => catalogType === "documents" ? setQuery(event.target.value) : setMemoryQuery(event.target.value)} placeholder={catalogType === "documents" ? "Buscar por título, tipo ou órgão" : "Buscar por título, origem ou estado"} /></label>
            <button className="icon-button" type="button" aria-label="Atualizar catálogo" title="Atualizar catálogo" onClick={catalogType === "documents" ? load : loadMemories}><RefreshCw size={17} /></button>
          </div>
        </header>
        <div className="rag-table-wrap">
          <table className={`rag-table ${catalogType === "memories" ? "rag-memory-table" : ""}`}>
            <thead><tr>{catalogType === "documents" ? <>
              <SortableRagHeader label="Documento" sortKey="titulo" sort={sort} onSort={changeSort} /><SortableRagHeader label="Tipo" sortKey="tipo" sort={sort} onSort={changeSort} /><SortableRagHeader label="Órgão" sortKey="orgao" sort={sort} onSort={changeSort} /><SortableRagHeader label="Revisões" sortKey="quantidadeVersoes" sort={sort} onSort={changeSort} /><SortableRagHeader label="Processamento" sortKey="status" sort={sort} onSort={changeSort} />
            </> : <>
              <SortableRagHeader label="Memória" sortKey="titulo" sort={sort} onSort={changeSort} /><SortableRagHeader label="Origem" sortKey="origem" sort={sort} onSort={changeSort} /><SortableRagHeader label="Estado" sortKey="estado" sort={sort} onSort={changeSort} /><SortableRagHeader label="Última atualização" sortKey="atualizadaEm" sort={sort} onSort={changeSort} /><SortableRagHeader label="Retenção" sortKey="retencaoAte" sort={sort} onSort={changeSort} />
            </>}
              <th><span className="sr-only">Ação</span></th>
            </tr></thead>
            <tbody>
              {(catalogType === "documents" ? loading : loadingMemories) ? <tr><td className="rag-table-message" colSpan="6"><RefreshCw className="spin" size={19} /> Carregando catálogo...</td></tr>
                : visibleItems.length ? visibleItems.map((item) => catalogType === "documents" ? <tr key={item.id} className={selected?.id === item.id ? "selected" : ""} onClick={() => openDocument(item.id)}>
                  <td><button type="button" className="rag-document-link" onClick={(event) => { event.stopPropagation(); openDocument(item.id); }}><span className="rag-table-icon"><Database size={17} /></span><span><strong>{item.titulo}</strong><small>{item.nivelAcesso === "RESTRITO" ? "Restrito a gestores" : "Acesso interno"}</small></span></button></td>
                  <td>{typeLabel(item.tipo)}</td><td>{item.orgao || "Não informado"}</td><td><strong>{item.quantidadeVersoes || 0}</strong></td>
                  <td>{item.ultimaVersao ? <i className={`rag-status status-${item.ultimaVersao.statusIngestao.toLowerCase()}`}>{INGESTION[item.ultimaVersao.statusIngestao]}</i> : <span className="rag-muted">Sem versão</span>}</td>
                  <td><button type="button" className="rag-row-action" aria-label="Abrir detalhes" onClick={(event) => { event.stopPropagation(); openDocument(item.id); }}><ChevronRight size={18} /></button></td>
                </tr> : <tr key={item.id} className={selectedMemory?.id === item.id ? "selected" : ""} onClick={() => openMemory(item)}>
                  <td><button type="button" className="rag-document-link" onClick={(event) => { event.stopPropagation(); openMemory(item); }}><span className="rag-table-icon memory"><BrainCircuit size={17} /></span><span><strong>{item.titulo}</strong><small>Gerada automaticamente pelo GabFlow</small></span></button></td>
                  <td><strong>{item.origem?.moduloNome || item.modulo}</strong><small className="rag-cell-note">{item.origem?.entidadeNome}</small></td>
                  <td><i className={`rag-memory-status memory-${item.estado.toLowerCase()}`}>{item.estadoNome || MEMORY_STATES[item.estado]}</i></td>
                  <td>{formatDateTime(item.atualizadaEm)}</td><td>{item.retencaoAte ? formatDate(item.retencaoAte) : "Conforme fonte"}</td>
                  <td><button type="button" className="rag-row-action" aria-label="Abrir detalhes" onClick={(event) => { event.stopPropagation(); openMemory(item); }}><ChevronRight size={18} /></button></td>
                </tr>) : <tr><td className="rag-table-empty" colSpan="6">{catalogType === "documents" ? <Database size={26} /> : <BrainCircuit size={26} />}<strong>Nenhum item encontrado</strong><span>{catalogType === "documents" ? (query ? "Revise os termos da busca ou limpe o filtro." : "Adicione o primeiro documento para começar a construir a base.") : (memoryQuery ? "Revise os termos da busca ou limpe o filtro." : "As memórias aparecerão conforme os módulos produzirem conhecimento elegível.")}</span></td></tr>}
            </tbody>
          </table>
        </div>
        <footer className="rag-pagination">
          <label>Itens por página<select aria-label="Itens por página" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>{PAGE_SIZES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <span>{sortedItems.length ? `${page * pageSize + 1}-${Math.min((page + 1) * pageSize, sortedItems.length)} de ${sortedItems.length}` : "0 itens"}</span>
          <nav aria-label="Paginação do catálogo"><button type="button" className="icon-button" aria-label="Página anterior" disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}><ChevronLeft size={18} /></button><span>Página {page + 1} de {totalPages}</span><button type="button" className="icon-button" aria-label="Próxima página" disabled={page + 1 >= totalPages} onClick={() => setPage((current) => current + 1)}><ChevronRight size={18} /></button></nav>
        </footer>
      </section>
    </section>
  </>;
}

function SortableRagHeader({ label, sortKey, sort, onSort }) {
  const active = sort.key === sortKey;
  const Icon = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
  return <th aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => onSort(sortKey)}>{label}<Icon size={14} /></button></th>;
}

function RagUploadForm({ form, setForm, file, setFile, busy, addingVersion, document, onCancel, onSubmit }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  return <form className="rag-upload-form" onSubmit={onSubmit}><header><div><p className="eyebrow">{addingVersion ? "Adicionar revisão" : "Novo documento"}</p><h2>{addingVersion ? document.titulo : "Adicionar à base documental"}</h2></div></header><div className="rag-form-grid">{!addingVersion && <><label className="full-width">Título<input aria-label="Título do documento" value={form.titulo} maxLength={240} onChange={(event) => setForm({ ...form, titulo: event.target.value })} /></label><label>Tipo<select aria-label="Tipo documental" value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Nível de acesso<select aria-label="Nível de acesso" value={form.nivelAcesso} onChange={(event) => setForm({ ...form, nivelAcesso: event.target.value })}><option value="INTERNO">Interno</option><option value="RESTRITO">Restrito a gestores</option></select></label><label className="full-width">Órgão responsável <span className="rag-field-optional">Opcional</span><input aria-label="Órgão responsável" value={form.orgao} maxLength={180} placeholder="Ex.: Câmara Municipal, Prefeitura ou Gabinete" onChange={(event) => setForm({ ...form, orgao: event.target.value })} /><small>Informe quem publicou ou responde pelo documento. Se não souber, deixe em branco.</small></label></>}<label>Identificação da revisão<input aria-label="Identificação da revisão" value={form.versao} maxLength={80} onChange={(event) => setForm({ ...form, versao: event.target.value })} /></label><label>Link da fonte oficial <span className="rag-field-optional">Opcional</span><input type="url" aria-label="Link da fonte oficial" value={form.urlFonte} placeholder="https://..." onChange={(event) => setForm({ ...form, urlFonte: event.target.value })} /><small>Use o endereço da publicação original para conferência e proveniência.</small></label><label>Vigente desde<input type="date" value={form.vigenteDesde} onChange={(event) => setForm({ ...form, vigenteDesde: event.target.value })} /></label><label>Vigente até<input type="date" value={form.vigenteAte} onChange={(event) => setForm({ ...form, vigenteAte: event.target.value })} /></label></div><input ref={inputRef} hidden type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={(event) => setFile(event.target.files[0] || null)} /><button type="button" className={`rag-dropzone ${dragging ? "dragging" : ""}`} onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0] || null); }}><Upload size={24} /><span><strong>{file ? file.name : "Arraste o documento para cá"}</strong><small>PDF, DOCX, TXT, PNG ou JPEG · máximo de 25 MB</small></span></button><div className="rag-form-actions"><button type="button" className="secondary-button" onClick={onCancel}>Cancelar</button><button className="primary-button" disabled={busy || !file || (!addingVersion && !form.titulo.trim())}><Upload size={17} /> {busy ? "Enviando..." : "Enviar para ingestão"}</button></div></form>;
}

function RagDocumentDetail({ document, busy, onAddVersion, onChangeState, onReprocess }) {
  return <div className="rag-detail"><header><div><span className="rag-document-icon"><Database size={22} /></span><span><p className="eyebrow">{typeLabel(document.tipo)}</p><h2>{document.titulo}</h2><small>{document.orgao || "Sem órgão"} · {document.nivelAcesso === "RESTRITO" ? "Restrito a gestores" : "Interno"}</small></span></div><button className="secondary-button" onClick={onAddVersion}><Plus size={17} /> Adicionar revisão</button></header><section className="rag-governance"><ShieldCheck size={19} /><p>Somente a revisão vigente fundamenta respostas atuais. Revisões anteriores preservam proveniência, auditoria e possibilidade de recuperação.</p></section><div className="rag-versions"><h3><History size={18} /> Histórico de revisões</h3>{document.versoes.map((version) => <article key={version.id}><header><div><FileText size={18} /><span><strong>Revisão {version.versao}</strong><small>{version.arquivo} · {formatBytes(version.tamanhoBytes)}</small></span></div><div><span className={`rag-lifecycle lifecycle-${version.estado.toLowerCase()}`}>{LIFECYCLE[version.estado]}</span><span className={`rag-status status-${version.statusIngestao.toLowerCase()}`}>{INGESTION[version.statusIngestao]}</span></div></header><dl><div><dt>Checksum</dt><dd title={version.checksum}>{version.checksum.slice(0, 16)}…</dd></div><div><dt>Vigência</dt><dd>{[version.vigenteDesde, version.vigenteAte].filter(Boolean).join(" a ") || "Não informada"}</dd></div><div><dt>Indexação</dt><dd>{version.fragmentos} fragmentos · {version.paginas || 0} página(s)</dd></div><div><dt>Modelo</dt><dd>{version.modeloEmbedding || "Aguardando"}</dd></div></dl>{version.erro && <p className="rag-version-error"><AlertTriangle size={15} /> {version.erro}</p>}<footer>{version.downloadUrl && <a className="secondary-button compact" href={version.downloadUrl}><Download size={16} /> Arquivo</a>}{version.statusIngestao === "FALHOU" && <button className="secondary-button compact" disabled={busy} onClick={() => onReprocess(version)}><RefreshCw size={16} /> Reprocessar</button>}{version.statusIngestao === "INDEXADO" && version.estado !== "VIGENTE" && <button className="primary-button compact" disabled={busy} onClick={() => onChangeState(version, "VIGENTE")}><CheckCircle2 size={16} /> Tornar vigente</button>}{version.estado === "VIGENTE" && <button className="secondary-button danger compact" disabled={busy} onClick={() => onChangeState(version, "REVOGADO")}>Revogar</button>}</footer></article>)}</div></div>;
}

function RagMemoryDetail({ memory, busy, onReprocess }) {
  const available = memory.disponivelParaInteligencia;
  return <div className="rag-detail rag-memory-detail"><header><div><span className="rag-document-icon memory"><BrainCircuit size={22} /></span><span><p className="eyebrow">Memória automática · {memory.origem?.sistema || "GabFlow"}</p><h2>{memory.titulo}</h2><small>{memory.origem?.moduloNome} · {memory.origem?.entidadeNome}</small></span></div><i className={`rag-memory-status memory-${memory.estado.toLowerCase()}`}>{memory.estadoNome || MEMORY_STATES[memory.estado]}</i></header><section className={`rag-memory-availability ${available ? "available" : "unavailable"}`}>{available ? <Sparkles size={20} /> : <Info size={20} />}<div><strong>{available ? "Disponível para a inteligência do gabinete" : "Não participa das respostas atuais"}</strong><p>{available ? "O GabFlow pode recuperar o snapshot vigente desta memória para gerar decisões, insights, sugestões e avisos." : memory.motivoElegibilidade ? eligibilityLabel(memory.motivoElegibilidade) : "A memória aguarda sincronização, revisão ou nova condição de elegibilidade."}</p></div></section><dl className="rag-memory-facts"><div><dt>Origem</dt><dd>{memory.origem?.moduloNome || memory.modulo}</dd><small>{memory.origem?.entidadeNome} · ID {shortId(memory.origem?.entidadeId || memory.entidadeId)}</small></div><div><dt>Última atualização</dt><dd>{formatDateTime(memory.atualizadaEm)}</dd><small>Sincronizada automaticamente</small></div><div><dt>Retenção</dt><dd>{memory.retencaoAte ? `Até ${formatDate(memory.retencaoAte)}` : "Conforme a fonte"}</dd><small>Após o prazo, o conteúdo é descartado</small></div><div><dt>Acesso</dt><dd>{memory.nivelAcesso === "RESTRITO" ? "Restrito a gestores" : "Interno"}</dd><small>Aplicado antes da recuperação</small></div></dl><section className="rag-memory-policy"><CalendarClock size={19} /><div><strong>Histórico com retenção controlada</strong><p>O GabFlow mantém somente os snapshots recentes materializados. Dos mais antigos, preserva metadados de proveniência até o prazo de retenção; depois, elimina o conteúdo da memória.</p></div></section><section className="rag-memory-purpose"><strong>Finalidade desta memória</strong><p>{memory.finalidadeNome || MEMORY_PURPOSES[memory.finalidade] || "Apoiar a inteligência e o trabalho diário do gabinete."}</p></section>{memory.estado === "ERRO" && <footer><button type="button" className="secondary-button" disabled={busy} onClick={() => onReprocess(memory)}><RefreshCw size={17} /> {busy ? "Solicitando..." : "Tentar sincronizar novamente"}</button></footer>}</div>;
}

function typeLabel(value) { return TYPES.find(([id]) => id === value)?.[1] || value; }
function catalogSortValue(item, key, catalogType) {
  if (catalogType === "memories") {
    if (key === "origem") return item.origem?.moduloNome || item.modulo;
    if (key === "estado") return item.estadoNome || MEMORY_STATES[item.estado] || item.estado;
    return item[key] ?? "";
  }
  if (key === "status") return INGESTION[item.ultimaVersao?.statusIngestao] || "";
  if (key === "tipo") return typeLabel(item.tipo);
  return item[key] ?? "";
}
function shortId(value) { return value ? String(value).slice(0, 8) : "não informado"; }
function formatDate(value) { return value ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR") : "Não informado"; }
function formatDateTime(value) { return value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "Ainda não sincronizada"; }
function eligibilityLabel(value) {
  return ({ RETENTION_EXPIRED: "O prazo de retenção desta memória expirou.", ENTITY_CANCELLED: "A entidade de origem foi cancelada.", CONTENT_NOT_REVIEWED: "O conteúdo ainda precisa de revisão humana.", INSUFFICIENT_AGGREGATION: "Ainda não há dados suficientes para formar conhecimento confiável." })[value] || "Esta memória não atende aos critérios atuais para uso na inteligência.";
}
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
