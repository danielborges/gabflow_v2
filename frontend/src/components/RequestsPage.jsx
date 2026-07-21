import {
  AudioLines,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Filter,
  Link2,
  RotateCcw,
  ScanText,
  ShieldAlert,
  Sparkles,
  MessageSquarePlus,
  Paperclip,
  PhoneCall,
  Plus,
  Search,
  Send,
  SquareCheckBig,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { apiRequest } from "../api";

const sources = [
  ["WHATSAPP", "WhatsApp"],
  ["PRESENCIAL", "Presencial"],
  ["TELEFONE", "Telefone"],
  ["EMAIL", "E-mail"],
  ["FORMULARIO", "Formulário"],
  ["REDE_SOCIAL", "Rede social"],
  ["VISITA", "Visita"],
];

const statuses = [
  ["", "Todos os status"],
  ["NOVA", "Nova"],
  ["TRIAGEM", "Triagem"],
  ["EM_ATENDIMENTO", "Em atendimento"],
  ["AGUARDANDO_ORGAO", "Aguardando órgão"],
  ["AGUARDANDO_CIDADAO", "Aguardando cidadão"],
  ["RESOLVIDA", "Resolvida"],
  ["ENCERRADA", "Encerrada"],
  ["CANCELADA", "Cancelada"],
];

const emptyReferences = {
  categories: [],
  citizens: [],
  organizations: [],
  users: [],
  territories: [],
  agencies: [],
  templates: [],
};

const attachmentMimeTypes = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "text/plain",
  "audio/mpeg",
  "audio/mp4",
  "audio/ogg",
  "audio/wav",
  "audio/webm",
  "audio/x-wav",
  "video/mp4",
];
const maximumAttachmentBytes = 15 * 1024 * 1024;

export function RequestsPage({ user, initialSearch = "" }) {
  const readOnly = user?.role === "representative";
  const [items, setItems] = useState([]);
  const [references, setReferences] = useState(emptyReferences);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (initialSearch) setSearch(initialSearch);
  }, [initialSearch]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ size: "50" });
    if (status) params.set("status", status);
    if (search.trim()) params.set("q", search.trim());
    try {
      const data = await apiRequest(`/api/v1/solicitacoes?${params}`);
      setItems(data.content);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  const loadReferences = useCallback(async () => {
    try {
      const [categories, citizens, organizations, users, territories, agencies, templates] = await Promise.all([
        apiRequest("/api/v1/admin/categorias"),
        apiRequest("/api/v1/cidadaos"),
        apiRequest("/api/v1/organizacoes"),
        apiRequest("/api/v1/usuarios"),
        apiRequest("/api/v1/admin/territorios"),
        apiRequest("/api/v1/admin/orgaos"),
        apiRequest("/api/v1/admin/templates-resposta"),
      ]);
      setReferences({
        categories: categories.content,
        citizens: citizens.content,
        organizations: organizations.content,
        users: users.content,
        territories: territories.content,
        agencies: agencies.content,
        templates: templates.content,
      });
    } catch {
      setReferences(emptyReferences);
    }
  }, []);

  useEffect(() => {
    loadReferences();
  }, [loadReferences]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function openDetails(id) {
    const details = await apiRequest(`/api/v1/solicitacoes/${id}`);
    setSelected(details);
  }

  return (
    <>
      <section className="page-heading request-heading">
        <div>
          <p className="eyebrow">Atendimento estruturado</p>
          <h1>Solicitações</h1>
          <p>Registre e acompanhe as demandas recebidas pelo gabinete.</p>
        </div>
        {!readOnly && <button className="primary-button compact" onClick={() => setShowCreate(true)}>
          <Plus size={18} /> Nova solicitação
        </button>}
      </section>

      <section className="request-toolbar" aria-label="Filtros de solicitações">
        <label className="toolbar-search">
          <Search size={18} aria-hidden="true" />
          <input
            aria-label="Buscar solicitações"
            placeholder="Protocolo, título ou descrição"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <label className="select-wrap">
          <Filter size={17} aria-hidden="true" />
          <select aria-label="Filtrar por status" value={status} onChange={(event) => setStatus(event.target.value)}>
            {statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <ChevronDown size={16} aria-hidden="true" />
        </label>
      </section>

      <section className="request-list" aria-live="polite">
        {error && <p className="form-error" role="alert">{error}</p>}
        {loading ? (
          <div className="table-message">Carregando solicitações...</div>
        ) : items.length === 0 ? (
          <div className="empty-state request-empty">
            <div className="empty-icon"><CircleDot size={28} /></div>
            <h2>Nenhuma solicitação encontrada</h2>
            <p>Registre uma nova demanda ou ajuste os filtros da consulta.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Protocolo</th><th>Solicitação</th><th>Origem</th>
                  <th>Prioridade</th><th>Status</th><th><span className="sr-only">Abrir</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex="0"
                    onClick={() => openDetails(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") openDetails(item.id);
                    }}
                  >
                    <td><strong>{item.protocolo}</strong><small>{formatDate(item.criadaEm)}</small></td>
                    <td><strong>{item.titulo || "Sem título"}</strong><small>{item.categoria || "Sem categoria"}</small></td>
                    <td>{sourceLabel(item.origem)}</td>
                    <td><span className={`priority priority-${item.prioridade.toLowerCase()}`}>{item.prioridade}</span></td>
                    <td><StatusBadge status={item.status} /></td>
                    <td><ArrowRight size={18} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showCreate && !readOnly && (
        <RequestForm
          references={references}
          onClose={() => setShowCreate(false)}
          onCreated={(created) => {
            setShowCreate(false);
            setSelected(created);
            load();
          }}
        />
      )}
      {selected && (
        <RequestDetails
          request={selected}
          references={references}
          readOnly={readOnly}
          onClose={() => setSelected(null)}
          onChanged={(updated) => {
            setSelected(updated);
            load();
          }}
        />
      )}
    </>
  );
}

function RequestForm({ references, onClose, onCreated }) {
  const [form, setForm] = useState({
    origem: "WHATSAPP",
    titulo: "",
    descricao: "",
    categoriaId: "",
    cidadaoId: "",
    organizacaoId: "",
    responsavelId: "",
    subcategoria: "",
    tema: "",
    territorioId: "",
    orgaoId: "",
    impacto: "",
    urgencia: "",
    endereco: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function change(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const created = await apiRequest("/api/v1/solicitacoes", {
        method: "POST",
        body: JSON.stringify(removeEmpty(form)),
      });
      onCreated(created);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-request-title">
        <header><div><p className="eyebrow">Novo atendimento</p><h2 id="new-request-title">Registrar solicitação</h2></div><CloseButton onClick={onClose} /></header>
        <form className="request-form" onSubmit={submit}>
          <div className="form-grid">
            <label>Origem<select name="origem" value={form.origem} onChange={change}>{sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>Categoria<select name="categoriaId" value={form.categoriaId} onChange={change}><option value="">Sem categoria</option>{references.categories.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome} ({item.slaHoras}h)</option>)}</select></label>
          </div>
          <div className="form-grid">
            <label>Subcategoria<input name="subcategoria" value={form.subcategoria} onChange={change} placeholder="Ex.: Pavimentação" /></label>
            <label>Tema<input name="tema" value={form.tema} onChange={change} placeholder="Ex.: Vias públicas" /></label>
          </div>
          <div className="form-grid">
            <label>Território<select name="territorioId" value={form.territorioId} onChange={change}><option value="">Não informado</option>{references.territories.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
            <label>Órgão responsável<select name="orgaoId" value={form.orgaoId} onChange={change}><option value="">Não informado</option>{references.agencies.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
          </div>
          <div className="form-grid">
            <label>Impacto<select name="impacto" value={form.impacto} onChange={change}><LevelOptions /></select></label>
            <label>Urgência<select name="urgencia" value={form.urgencia} onChange={change}><LevelOptions /></select></label>
          </div>
          <div className="form-grid">
            <label>Cidadão<select name="cidadaoId" value={form.cidadaoId} onChange={change}><option value="">Não informado</option>{references.citizens.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
            <label>Organização<select name="organizacaoId" value={form.organizacaoId} onChange={change}><option value="">Não informada</option>{references.organizations.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
          </div>
          <label>Responsável<select name="responsavelId" value={form.responsavelId} onChange={change}><option value="">Fila geral</option>{references.users.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
          <label>Título<input name="titulo" maxLength="180" value={form.titulo} onChange={change} placeholder="Resumo objetivo da demanda" /></label>
          <label>Descrição<textarea name="descricao" minLength="3" required rows="5" value={form.descricao} onChange={change} placeholder="Descreva o relato recebido e os fatos relevantes." /></label>
          <label>Endereço<input name="endereco" value={form.endereco} onChange={change} placeholder="Logradouro, número e referência" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact" disabled={saving}><Plus size={18} />{saving ? "Salvando..." : "Registrar"}</button></footer>
        </form>
      </section>
    </div>
  );
}

function RequestDetails({ request, references, readOnly = false, onClose, onChanged }) {
  const linkedCitizen = references.citizens.find((item) => item.id === request.cidadaoId);
  const preferredChannel = linkedCitizen?.canalPreferencial || "";
  const [status, setStatus] = useState(request.status);
  const [categoryId, setCategoryId] = useState(request.categoriaId || "");
  const [assigneeId, setAssigneeId] = useState(request.responsavelId || "");
  const [reason, setReason] = useState(request.motivoEncerramento || "");
  const [evidence, setEvidence] = useState(request.evidenciaEncerramento || "");
  const [interaction, setInteraction] = useState("");
  const [response, setResponse] = useState({
    templateId: "",
    canal: "WHATSAPP",
    assunto: "",
    conteudo: "",
  });
  const [responseDraftNotice, setResponseDraftNotice] = useState("");
  const responseFormRef = useRef(null);
  const responseMessageRef = useRef(null);
  const [scheduledReturn, setScheduledReturn] = useState({
    agendadoPara: "",
    responsavelId: request.responsavelId || "",
    observacoes: "",
    lembreteHabilitado: true,
    lembreteMinutos: 60,
  });
  const [taskTitle, setTaskTitle] = useState("");
  const [duplicateId, setDuplicateId] = useState("");
  const [duplicateReason, setDuplicateReason] = useState("");
  const [attachment, setAttachment] = useState(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [forwarding, setForwarding] = useState({ orgaoId: request.orgaoId || "", protocoloExterno: "", prazo: "" });
  const [externalResponse, setExternalResponse] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [publicAccess, setPublicAccess] = useState(
    request.chaveAcompanhamento
      ? { protocolo: request.protocolo, chave: request.chaveAcompanhamento }
      : null,
  );
  const [contactAttempt, setContactAttempt] = useState({
    canal: preferredChannel,
    destino: contactDestination(linkedCitizen, preferredChannel),
    resultado: "REALIZADO",
    observacoes: "",
    proximaTentativaEm: "",
    justificativaCanal: "",
  });
  const [error, setError] = useState("");

  useEffect(() => {
    setCategoryId(request.categoriaId || "");
  }, [request.categoriaId]);

  useEffect(() => {
    const triagePending = ["PENDENTE", "PROCESSANDO"].includes(request.triagemIA?.status);
    const assistancePending = ["PENDENTE", "PROCESSANDO"].includes(request.assistenciaIA?.status);
    const transcriptionPending = (request.anexos || []).some((item) =>
      ["PENDENTE", "PROCESSANDO"].includes(item.transcricao?.status),
    );
    const ocrPending = (request.anexos || []).some((item) =>
      ["PENDENTE", "PROCESSANDO"].includes(item.ocr?.status),
    );
    if (!triagePending && !assistancePending && !transcriptionPending && !ocrPending) return undefined;
    const timer = setInterval(async () => {
      try {
        onChanged(await apiRequest(`/api/v1/solicitacoes/${request.id}`));
      } catch {
        // The regular page error handling remains responsible for visible failures.
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [onChanged, request.anexos, request.assistenciaIA?.status, request.id, request.triagemIA?.status]);

  async function refresh() {
    onChanged(await apiRequest(`/api/v1/solicitacoes/${request.id}`));
  }

  async function updateRequest() {
    setError("");
    try {
      const updated = await apiRequest(`/api/v1/solicitacoes/${request.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          categoriaId: categoryId || null,
          responsavelId: assigneeId || null,
          motivoEncerramento: reason,
          evidenciaEncerramento: evidence,
        }),
      });
      onChanged(updated);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function addInteraction(event) {
    event.preventDefault();
    setError("");
    try {
      const updated = await apiRequest(`/api/v1/solicitacoes/${request.id}/interacoes`, {
        method: "POST",
        body: JSON.stringify({
          tipo: "ATUALIZACAO",
          canal: "INTERNO",
          direcao: "INTERNA",
          conteudo: interaction,
          visibilidade: "INTERNA",
        }),
      });
      setInteraction("");
      onChanged(updated);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function selectResponseTemplate(templateId) {
    setResponse((current) => ({ ...current, templateId }));
    if (!templateId) return;
    try {
      const preview = await apiRequest(`/api/v1/solicitacoes/${request.id}/respostas/preview`, {
        method: "POST",
        body: JSON.stringify({ templateId }),
      });
      setResponse({
        templateId,
        canal: preview.canal,
        assunto: preview.assunto || "",
        conteudo: preview.conteudo,
      });
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function sendResponse(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/respostas`, {
        method: "POST",
        body: JSON.stringify(response),
      });
      setResponse({ templateId: "", canal: "WHATSAPP", assunto: "", conteudo: "" });
      setResponseDraftNotice("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function useAssistantResponse(suggestion) {
    setResponse({
      templateId: "",
      canal: suggestion.canal || "WHATSAPP",
      assunto: suggestion.assunto || "",
      conteudo: suggestion.conteudo || "",
    });
    setResponseDraftNotice(
      "Resposta sugerida aplicada ao formulário. Revise o conteúdo antes de registrar a saída.",
    );
    requestAnimationFrame(() => {
      responseFormRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      responseMessageRef.current?.focus({ preventScroll: true });
    });
  }

  async function addScheduledReturn(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/retornos`, {
        method: "POST",
        body: JSON.stringify({
          ...scheduledReturn,
          lembreteMinutos: Number(scheduledReturn.lembreteMinutos),
        }),
      });
      setScheduledReturn({
        agendadoPara: "",
        responsavelId: request.responsavelId || "",
        observacoes: "",
        lembreteHabilitado: true,
        lembreteMinutos: 60,
      });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function updateScheduledReturn(returnId, payload) {
    setError("");
    try {
      await apiRequest(`/api/v1/retornos/${returnId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function addTask(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/tarefas`, {
        method: "POST",
        body: JSON.stringify({ titulo: taskTitle, responsavelId: assigneeId || null }),
      });
      setTaskTitle("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function toggleTask(task) {
    await apiRequest(`/api/v1/tarefas/${task.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: task.status === "CONCLUIDA" ? "PENDENTE" : "CONCLUIDA" }),
    });
    await refresh();
  }

  async function groupDuplicate(event) {
    event.preventDefault();
    if (!duplicateId) return;
    setError("");
    try {
      await apiRequest("/api/v1/solicitacoes/agrupar-duplicadas", {
        method: "POST",
        body: JSON.stringify({ solicitacaoIds: [request.id, duplicateId], motivo: duplicateReason }),
      });
      setDuplicateId("");
      setDuplicateReason("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function uploadAttachment(event) {
    event.preventDefault();
    if (!attachment) return;
    const formData = new FormData();
    formData.append("arquivo", attachment);
    setError("");
    setUploadingAttachment(true);
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/anexos`, {
        method: "POST",
        body: formData,
      });
      setAttachment(null);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploadingAttachment(false);
    }
  }

  async function addForwarding(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/encaminhamentos`, {
        method: "POST",
        body: JSON.stringify(removeEmpty(forwarding)),
      });
      setForwarding({ orgaoId: request.orgaoId || "", protocoloExterno: "", prazo: "" });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function registerAgencyResponse(event, forwardingId) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/encaminhamentos/${forwardingId}`, {
        method: "PATCH",
        body: JSON.stringify({ resposta: externalResponse }),
      });
      setExternalResponse("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function reopen(event) {
    event.preventDefault();
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/reabrir`, {
        method: "POST",
        body: JSON.stringify({ motivo: reopenReason }),
      });
      setReopenReason("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function generatePublicKey() {
    try {
      setPublicAccess(await apiRequest(`/api/v1/solicitacoes/${request.id}/chave-publica`, { method: "POST" }));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function changeContactChannel(channel) {
    setContactAttempt((current) => ({
      ...current,
      canal: channel,
      destino: contactDestination(linkedCitizen, channel),
      justificativaCanal: channel === preferredChannel ? "" : current.justificativaCanal,
    }));
  }

  async function addContactAttempt(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/tentativas-contato`, {
        method: "POST",
        body: JSON.stringify(removeEmpty(contactAttempt)),
      });
      setContactAttempt({
        canal: preferredChannel,
        destino: contactDestination(linkedCitizen, preferredChannel),
        resultado: "REALIZADO",
        observacoes: "",
        proximaTentativaEm: "",
        justificativaCanal: "",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const closing = ["RESOLVIDA", "ENCERRADA", "CANCELADA"].includes(status);
  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="request-drawer" role="dialog" aria-modal="true" aria-labelledby="request-title">
        <header><div><p className="eyebrow">{request.protocolo}</p><h2 id="request-title">{request.titulo || "Solicitação sem título"}</h2></div><CloseButton onClick={onClose} /></header>
        <div className="drawer-content">
          <div className="request-meta"><StatusBadge status={request.status} /><span>{sourceLabel(request.origem)}</span><span>{formatDate(request.criadaEm)}</span>{request.situacaoSla && <span className={`sla-status sla-${request.situacaoSla.toLowerCase()}`}>SLA {slaLabel(request.situacaoSla)}</span>}</div>
          <p className="request-description">{request.descricao}</p>
          {request.endereco && <p className="request-address">{request.endereco}</p>}
          <div className="classification-summary">
            {request.subcategoria && <span>{request.subcategoria}</span>}
            {request.tema && <span>{request.tema}</span>}
            {request.impacto && <span>Impacto {request.impacto.toLowerCase()}</span>}
            {request.urgencia && <span>Urgência {request.urgencia.toLowerCase()}</span>}
          </div>

          {!readOnly && <AITriagePanel
            request={request}
            categories={references.categories}
            agencies={references.agencies}
            onChanged={onChanged}
            onError={setError}
          />}

          {!readOnly && <section className="drawer-section">
            <h3>Acompanhamento</h3>
            <div className="form-grid">
              <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}>{statuses.slice(1).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label>Responsável<select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}><option value="">Fila geral</option>{references.users.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
            </div>
            <label>Categoria<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">Sem categoria</option>{references.categories.map((item) => <option key={item.id} value={item.id}>{item.nome} ({item.slaHoras}h)</option>)}</select></label>
            {request.prazo && <p className="muted-copy">Prazo de atendimento: <strong>{formatDate(request.prazo)}</strong></p>}
            {closing && <><label>Motivo do encerramento<textarea rows="2" value={reason} onChange={(event) => setReason(event.target.value)} /></label><label>Evidência ou justificativa<textarea rows="2" value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label></>}
            <button className="secondary-button action-button" onClick={updateRequest}><CheckCircle2 size={17} /> Atualizar acompanhamento</button>
          </section>}

          {!readOnly && <section className="drawer-section">
            <h3>Encaminhamentos</h3>
            {(request.encaminhamentos || []).map((item) => <article className="forwarding-item" key={item.id}><div><strong>{item.orgao}</strong><small>{item.protocoloExterno || "Sem protocolo externo"} · {item.status}</small></div>{item.resposta ? <p>{item.resposta}</p> : <form onSubmit={(event) => registerAgencyResponse(event, item.id)}><input required value={externalResponse} onChange={(event) => setExternalResponse(event.target.value)} placeholder="Registrar resposta do órgão" /><button className="secondary-button">Registrar</button></form>}</article>)}
            {(request.encaminhamentos || []).length === 0 && <p className="muted-copy">Nenhum encaminhamento registrado.</p>}
            <form className="duplicate-form" onSubmit={addForwarding}>
              <label>Órgão<select required value={forwarding.orgaoId} onChange={(event) => setForwarding((current) => ({ ...current, orgaoId: event.target.value }))}><option value="">Selecione</option>{references.agencies.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
              <div className="form-grid"><label>Protocolo externo<input value={forwarding.protocoloExterno} onChange={(event) => setForwarding((current) => ({ ...current, protocoloExterno: event.target.value }))} /></label><label>Prazo<input type="datetime-local" value={forwarding.prazo} onChange={(event) => setForwarding((current) => ({ ...current, prazo: event.target.value }))} /></label></div>
              <button className="secondary-button action-button"><Send size={17} /> Encaminhar</button>
            </form>
          </section>}

          {!readOnly && <section className="drawer-section">
            <h3>Tarefas</h3>
            <div className="task-list">
              {(request.tarefas || []).map((task) => <label key={task.id} className={task.status === "CONCLUIDA" ? "task-item completed" : "task-item"}><input type="checkbox" checked={task.status === "CONCLUIDA"} onChange={() => toggleTask(task)} /><span><strong>{task.titulo}</strong><small>{task.prazo ? `Prazo: ${formatDate(task.prazo)}` : task.prioridade}</small></span></label>)}
              {(request.tarefas || []).length === 0 && <p className="muted-copy">Nenhuma tarefa criada.</p>}
            </div>
            <form className="inline-form" onSubmit={addTask}><input required minLength="3" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Nova tarefa" /><button className="primary-button compact" title="Adicionar tarefa"><Plus size={17} /> Adicionar</button></form>
          </section>}

          <section className="drawer-section">
            <h3>Anexos</h3>
            <div className="attachment-list">
              {(request.anexos || []).map((item) => (
                <article className="attachment-item" key={item.id}>
                  <a href={item.downloadUrl} target="_blank" rel="noreferrer">
                    <Paperclip size={16} />
                    <span><strong>{item.nome}</strong><small>{formatBytes(item.tamanho)} · {item.statusVerificacao}</small></span>
                  </a>
                  {item.transcricao && (
                    <AudioTranscriptionPanel
                      attachment={item}
                      onRefresh={refresh}
                      onError={setError}
                    />
                  )}
                  {item.ocr && (
                    <DocumentOcrPanel
                      attachment={item}
                      onRefresh={refresh}
                      onError={setError}
                    />
                  )}
                </article>
              ))}
              {(request.anexos || []).length === 0 && <p className="muted-copy">Nenhum anexo enviado.</p>}
            </div>
            {!readOnly && <AttachmentDropzone
              file={attachment}
              uploading={uploadingAttachment}
              onFile={setAttachment}
              onError={setError}
              onSubmit={uploadAttachment}
            />}
          </section>

          <section className="drawer-section">
            <h3>Duplicidades</h3>
            {(request.duplicidades || []).length > 0 && <div className="duplicate-list">{request.duplicidades.map((item) => <span key={item.id}><Link2 size={15} /> {item.protocolo}</span>)}</div>}
            <form className="duplicate-form" onSubmit={groupDuplicate}>
              <RequestSearchSelect
                value={duplicateId}
                excludeId={request.id}
                onChange={setDuplicateId}
              />
              <label>Motivo<input required value={duplicateReason} onChange={(event) => setDuplicateReason(event.target.value)} placeholder="Mesmo relato, local e ocorrência" /></label>
              <button className="secondary-button action-button" disabled={!duplicateId}><Link2 size={17} /> Agrupar sem excluir</button>
            </form>
          </section>

          <section className="drawer-section">
            <h3>Resposta ao cidadão</h3>
            <AIAssistancePanel
              request={request}
              defaultChannel={response.canal}
              onChanged={onChanged}
              onUse={useAssistantResponse}
              onError={setError}
            />
            <form
              id="citizen-response-form"
              ref={responseFormRef}
              className={responseDraftNotice ? "communication-form response-draft-active" : "communication-form"}
              onSubmit={sendResponse}
            >
              {responseDraftNotice && <p className="response-draft-notice"><CheckCircle2 size={16} /> {responseDraftNotice}</p>}
              <label>Template<select value={response.templateId} onChange={(event) => selectResponseTemplate(event.target.value)}><option value="">Resposta livre</option>{references.templates.filter((item) => item.ativa && (!item.categoriaId || item.categoriaId === request.categoriaId)).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
              <label>Canal<select value={response.canal} onChange={(event) => setResponse((current) => ({ ...current, canal: event.target.value }))}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
              {response.canal === "EMAIL" && <label>Assunto<input required value={response.assunto} onChange={(event) => setResponse((current) => ({ ...current, assunto: event.target.value }))} placeholder={`Atualização da solicitação ${request.protocolo}`} /></label>}
              <label>Mensagem<textarea ref={responseMessageRef} required rows="5" value={response.conteudo} onChange={(event) => setResponse((current) => ({ ...current, conteudo: event.target.value }))} placeholder="Visualize e ajuste a mensagem antes de registrar." /></label>
              <button className="primary-button compact"><Send size={17} /> Registrar saída</button>
            </form>
          </section>

          <section className="drawer-section">
            <h3>Retornos agendados</h3>
            <div className="scheduled-return-list">
              {(request.retornos || []).map((item) => <ScheduledReturnItem key={item.id} item={item} onUpdate={updateScheduledReturn} />)}
              {(request.retornos || []).length === 0 && <p className="muted-copy">Nenhum retorno agendado.</p>}
            </div>
            <form className="communication-form" onSubmit={addScheduledReturn}>
              <div className="form-grid">
                <label>Data e hora<input required type="datetime-local" value={scheduledReturn.agendadoPara} onChange={(event) => setScheduledReturn((current) => ({ ...current, agendadoPara: event.target.value }))} /></label>
                <label>Responsável<select required value={scheduledReturn.responsavelId} onChange={(event) => setScheduledReturn((current) => ({ ...current, responsavelId: event.target.value }))}><option value="">Selecione</option>{references.users.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
              </div>
              <label>Observações<textarea rows="2" value={scheduledReturn.observacoes} onChange={(event) => setScheduledReturn((current) => ({ ...current, observacoes: event.target.value }))} /></label>
              <div className="reminder-controls">
                <label className="checkbox-label"><input type="checkbox" checked={scheduledReturn.lembreteHabilitado} onChange={(event) => setScheduledReturn((current) => ({ ...current, lembreteHabilitado: event.target.checked }))} /> Gerar lembrete</label>
                <label>Antecedência (min)<input type="number" min="0" max="10080" disabled={!scheduledReturn.lembreteHabilitado} value={scheduledReturn.lembreteMinutos} onChange={(event) => setScheduledReturn((current) => ({ ...current, lembreteMinutos: event.target.value }))} /></label>
              </div>
              <button className="secondary-button action-button"><CalendarClock size={17} /> Agendar retorno</button>
            </form>
          </section>

          <section className="drawer-section">
            <h3>Interações</h3>
            {request.interacoes.length === 0 ? <p className="muted-copy">Nenhuma interação registrada.</p> : <div className="timeline">{request.interacoes.map((item) => <article key={item.id}><MessageSquarePlus size={16} /><div><strong>{item.tipo}</strong><p>{item.conteudo}</p><small>{formatDate(item.criadaEm)}</small></div></article>)}</div>}
            <form className="interaction-form" onSubmit={addInteraction}><textarea aria-label="Nova interação" required rows="3" value={interaction} onChange={(event) => setInteraction(event.target.value)} placeholder="Registrar atualização interna" /><button className="primary-button compact"><Send size={17} /> Registrar</button></form>
          </section>
          <section className="drawer-section">
            <h3>Tentativas de contato</h3>
            {preferredChannel && <p className="preferred-channel"><PhoneCall size={15} /> Canal preferencial: <strong>{sourceLabel(preferredChannel)}</strong></p>}
            <div className="contact-attempt-list">
              {(request.tentativasContato || []).map((item) => <article key={item.id}><span className={`attempt-result result-${item.resultado.toLowerCase()}`} /><div><strong>{sourceLabel(item.canal)} · {contactResultLabel(item.resultado)}</strong><p>{item.observacoes || item.destino}</p><small>{formatDate(item.tentadaEm)}{item.proximaTentativaEm ? ` · Próxima: ${formatDate(item.proximaTentativaEm)}` : ""}</small></div></article>)}
              {(request.tentativasContato || []).length === 0 && <p className="muted-copy">Nenhuma tentativa registrada.</p>}
            </div>
            <form className="contact-attempt-form" onSubmit={addContactAttempt}>
              <div className="form-grid">
                <label>Canal<select required value={contactAttempt.canal} onChange={(event) => changeContactChannel(event.target.value)}><option value="">Selecione</option>{sources.filter(([value]) => ["WHATSAPP", "TELEFONE", "EMAIL", "PRESENCIAL"].includes(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>Resultado<select value={contactAttempt.resultado} onChange={(event) => setContactAttempt((current) => ({ ...current, resultado: event.target.value }))}><option value="REALIZADO">Contato realizado</option><option value="SEM_RESPOSTA">Sem resposta</option><option value="FALHOU">Falhou</option><option value="AGENDADO">Retorno agendado</option></select></label>
              </div>
              <label>Destino<input required value={contactAttempt.destino} onChange={(event) => setContactAttempt((current) => ({ ...current, destino: event.target.value }))} placeholder="Telefone, e-mail ou endereço" /></label>
              {preferredChannel && contactAttempt.canal && contactAttempt.canal !== preferredChannel && <label>Justificativa para outro canal<textarea required rows="2" value={contactAttempt.justificativaCanal} onChange={(event) => setContactAttempt((current) => ({ ...current, justificativaCanal: event.target.value }))} /></label>}
              {contactAttempt.resultado === "AGENDADO" && <label>Próxima tentativa<input required type="datetime-local" value={contactAttempt.proximaTentativaEm} onChange={(event) => setContactAttempt((current) => ({ ...current, proximaTentativaEm: event.target.value }))} /></label>}
              <label>Observações<textarea rows="2" value={contactAttempt.observacoes} onChange={(event) => setContactAttempt((current) => ({ ...current, observacoes: event.target.value }))} /></label>
              <button className="secondary-button action-button"><PhoneCall size={17} /> Registrar tentativa</button>
            </form>
          </section>
          <section className="drawer-section">
            <h3>Acompanhamento público</h3>
            <p className="muted-copy">Gere uma nova chave sempre que precisar compartilhar ou revogar o acesso anterior.</p>
            <button className="secondary-button action-button" onClick={generatePublicKey}><Link2 size={17} /> Gerar chave segura</button>
            {publicAccess && <div className="public-key-result"><strong>{publicAccess.protocolo}</strong><code>{publicAccess.chave}</code></div>}
            {["RESOLVIDA", "ENCERRADA", "CANCELADA"].includes(request.status) && <form className="inline-form" onSubmit={reopen}><input required minLength="3" value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} placeholder="Motivo da reabertura" /><button className="secondary-button"><RotateCcw size={17} /> Reabrir</button></form>}
          </section>
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
      </aside>
    </div>
  );
}

export function AttachmentDropzone({ file, uploading, onFile, onError, onSubmit }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function selectFile(selectedFile) {
    if (!selectedFile) return;
    if (selectedFile.size > maximumAttachmentBytes) {
      onError("O arquivo excede o limite de 15 MB.");
      return;
    }
    if (selectedFile.type && !attachmentMimeTypes.includes(selectedFile.type)) {
      onError("Tipo de arquivo não permitido.");
      return;
    }
    onError("");
    onFile(selectedFile);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  return (
    <form className="attachment-upload" onSubmit={onSubmit}>
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        value=""
        accept={attachmentMimeTypes.join(",")}
        onChange={(event) => selectFile(event.target.files?.[0])}
      />
      <div
        className={`attachment-dropzone ${dragging ? "is-dragging" : ""}`}
        role="button"
        tabIndex="0"
        aria-label="Selecionar ou arrastar arquivo para anexar"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
        }}
        onDrop={handleDrop}
      >
        <span className="attachment-drop-icon"><Upload size={21} /></span>
        <span><strong>Arraste o arquivo para cá</strong><small>ou clique para selecionar · máximo de 15 MB</small></span>
      </div>
      {file && (
        <div className="selected-attachment">
          <Paperclip size={17} />
          <span><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></span>
          <button
            type="button"
            className="icon-button"
            aria-label="Remover arquivo selecionado"
            title="Remover arquivo"
            onClick={() => onFile(null)}
          >
            <X size={17} />
          </button>
        </div>
      )}
      <button className="secondary-button attachment-submit" disabled={!file || uploading}>
        <Upload size={17} /> {uploading ? "Enviando..." : "Enviar anexo"}
      </button>
    </form>
  );
}

export function RequestSearchSelect({
  value,
  excludeId,
  excludeIds = [],
  label = "Solicitação relacionada",
  placeholder = "Busque por protocolo, título ou descrição",
  clearAfterSelect = false,
  onChange,
  onSelect,
}) {
  const inputId = useId();
  const listboxId = useId();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const excludedIdsKey = [excludeId, ...excludeIds].filter(Boolean).join("|");

  useEffect(() => {
    if (value) return;
    setSelected(null);
    setQuery("");
  }, [value]);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    setLoading(true);
    setSearchError("");
    const timer = setTimeout(async () => {
      const params = new URLSearchParams({ size: "8" });
      if (query.trim()) params.set("q", query.trim());
      try {
        const data = await apiRequest(`/api/v1/solicitacoes?${params}`);
        if (!active) return;
        const excluded = new Set(excludedIdsKey.split("|").filter(Boolean));
        setOptions(data.content.filter((item) => !excluded.has(item.id)));
        setActiveIndex(-1);
      } catch (requestError) {
        if (!active) return;
        setOptions([]);
        setSearchError(requestError.message);
      } finally {
        if (active) setLoading(false);
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [excludedIdsKey, open, query]);

  function selectOption(option) {
    setSelected(clearAfterSelect ? null : option);
    setQuery("");
    setOpen(false);
    setActiveIndex(-1);
    onChange(option.id);
    onSelect?.(option);
  }

  function changeQuery(event) {
    if (selected) {
      setSelected(null);
      onChange("");
    }
    setQuery(event.target.value);
    setOpen(true);
  }

  function handleKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.min(current + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && open && activeIndex >= 0) {
      event.preventDefault();
      selectOption(options[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  const displayValue = selected
    ? `${selected.protocolo} · ${selected.titulo || "Sem título"}`
    : query;

  return (
    <div
      className="request-search-select"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
          setActiveIndex(-1);
        }
      }}
    >
      <label htmlFor={inputId}>{label}</label>
      <div className={`search-select-control ${open ? "is-open" : ""}`}>
        <Search size={17} aria-hidden="true" />
        <input
          id={inputId}
          role="combobox"
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded={open}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
          autoComplete="off"
          placeholder={placeholder}
          value={displayValue}
          onChange={changeQuery}
          onFocus={(event) => {
            setOpen(true);
            if (selected) event.currentTarget.select();
          }}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          className="search-select-toggle"
          aria-label={open ? "Fechar opções" : "Abrir opções"}
          onClick={() => setOpen((current) => !current)}
        >
          <ChevronDown size={17} aria-hidden="true" />
        </button>
      </div>
      {open && (
        <div className="search-select-menu" id={listboxId} role="listbox">
          {loading ? (
            <p>Buscando solicitações...</p>
          ) : searchError ? (
            <p className="search-select-error">{searchError}</p>
          ) : options.length === 0 ? (
            <p>Nenhuma solicitação encontrada.</p>
          ) : options.map((option, index) => (
            <div
              id={`${listboxId}-${index}`}
              key={option.id}
              className={index === activeIndex ? "is-active" : ""}
              role="option"
              aria-selected={option.id === value}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => selectOption(option)}
            >
              <strong>{option.protocolo}</strong>
              <span>{option.titulo || "Sem título"}</span>
              <small>{statusLabel(option.status)}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AudioTranscriptionPanel({ attachment, onRefresh, onError }) {
  const transcription = attachment.transcricao;
  const reviewed = transcription.statusRevisao !== "PENDENTE";
  const [text, setText] = useState(
    transcription.textoRevisado || transcription.textoGerado || "",
  );
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setText(transcription.textoRevisado || transcription.textoGerado || "");
  }, [transcription.textoGerado, transcription.textoRevisado]);

  async function review(action) {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/transcricoes-audio/${transcription.id}/revisao`, {
        method: "POST",
        body: JSON.stringify({ acao: action, ...(action === "EDITAR" ? { texto: text } : {}) }),
      });
      await onRefresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function reprocess() {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/transcricoes-audio/${transcription.id}/reprocessar`, {
        method: "POST",
      });
      await onRefresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (["PENDENTE", "PROCESSANDO"].includes(transcription.status)) {
    return (
      <div className="audio-transcription is-processing">
        <div className="audio-transcription-heading">
          <AudioLines size={17} />
          <div><strong>Transcrevendo áudio</strong><small>Processamento local em andamento</small></div>
        </div>
        <div className="ai-progress" aria-label="Transcrição em processamento"><span /></div>
      </div>
    );
  }

  if (transcription.status === "FALHOU") {
    return (
      <div className="audio-transcription has-error">
        <div className="audio-transcription-heading">
          <AudioLines size={17} />
          <div><strong>Não foi possível transcrever</strong><small>{transcription.erro}</small></div>
        </div>
        <button className="secondary-button" onClick={reprocess} disabled={submitting}>
          <RotateCcw size={16} /> Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div className="audio-transcription">
      <div className="audio-transcription-heading">
        <AudioLines size={17} />
        <div>
          <strong>Transcrição local</strong>
          <small>{transcription.modelo} · {transcription.idioma || "idioma não identificado"} · {formatDuration(transcription.duracaoSegundos)}</small>
        </div>
      </div>
      <audio controls preload="metadata" src={attachment.downloadUrl}>
        Seu navegador não suporta a reprodução deste áudio.
      </audio>
      <label>
        Texto transcrito
        <textarea
          rows="6"
          value={text}
          disabled={reviewed}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      {reviewed ? (
        <div className={`audio-review-status review-${transcription.statusRevisao.toLowerCase()}`}>
          {transcription.statusRevisao === "REJEITADA" ? <X size={17} /> : <CheckCircle2 size={17} />}
          <span>{transcriptionReviewLabel(transcription.statusRevisao)}</span>
        </div>
      ) : (
        <div className="audio-review-actions">
          <button className="primary-button compact" onClick={() => review("ACEITAR")} disabled={submitting}>
            <CheckCircle2 size={16} /> Aceitar transcrição
          </button>
          <button className="secondary-button" onClick={() => review("EDITAR")} disabled={submitting || !text.trim()}>
            Aplicar correções
          </button>
          <button className="secondary-button danger-text" onClick={() => review("REJEITAR")} disabled={submitting}>
            <X size={16} /> Rejeitar
          </button>
        </div>
      )}
      <p className="audio-original-note">O arquivo de áudio original é preservado independentemente da revisão.</p>
    </div>
  );
}

export function DocumentOcrPanel({ attachment, onRefresh, onError }) {
  const ocr = attachment.ocr;
  const reviewed = ocr.statusRevisao !== "PENDENTE";
  const [text, setText] = useState(ocr.textoRevisado || ocr.textoGerado || "");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setText(ocr.textoRevisado || ocr.textoGerado || "");
  }, [ocr.textoGerado, ocr.textoRevisado]);

  async function review(action) {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/ocr-documentos/${ocr.id}/revisao`, {
        method: "POST",
        body: JSON.stringify({ acao: action, ...(action === "EDITAR" ? { texto: text } : {}) }),
      });
      await onRefresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function reprocess() {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/ocr-documentos/${ocr.id}/reprocessar`, { method: "POST" });
      await onRefresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (["PENDENTE", "PROCESSANDO"].includes(ocr.status)) {
    return (
      <div className="audio-transcription document-ocr is-processing">
        <div className="audio-transcription-heading">
          <ScanText size={17} />
          <div><strong>Extraindo texto</strong><small>OCR local em andamento</small></div>
        </div>
        <div className="ai-progress" aria-label="OCR em processamento"><span /></div>
      </div>
    );
  }

  if (ocr.status === "FALHOU") {
    return (
      <div className="audio-transcription document-ocr has-error">
        <div className="audio-transcription-heading">
          <ScanText size={17} />
          <div><strong>Não foi possível extrair o texto</strong><small>{ocr.erro}</small></div>
        </div>
        <button className="secondary-button" onClick={reprocess} disabled={submitting}>
          <RotateCcw size={16} /> Tentar novamente
        </button>
      </div>
    );
  }

  const confidence = ocr.confianca == null ? null : Math.round(ocr.confianca * 100);
  return (
    <div className="audio-transcription document-ocr">
      <div className="audio-transcription-heading">
        <ScanText size={17} />
        <div>
          <strong>OCR local</strong>
          <small>{ocr.modelo} · {ocr.idioma} · {ocr.paginas} {ocr.paginas === 1 ? "página" : "páginas"}</small>
        </div>
        {confidence != null && <span className="ocr-confidence">{confidence}% confiança</span>}
      </div>
      {(ocr.detalhesPaginas || []).length > 1 && (
        <div className="ocr-page-confidence" aria-label="Confiança por página">
          {ocr.detalhesPaginas.map((page) => (
            <span key={page.pagina}>Pág. {page.pagina}: {Math.round(page.confianca * 100)}%</span>
          ))}
        </div>
      )}
      <label>
        Texto extraído
        <textarea
          rows="8"
          value={text}
          disabled={reviewed}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      {reviewed ? (
        <div className={`audio-review-status review-${ocr.statusRevisao.toLowerCase()}`}>
          {ocr.statusRevisao === "REJEITADO" ? <X size={17} /> : <CheckCircle2 size={17} />}
          <span>{ocrReviewLabel(ocr.statusRevisao)}</span>
        </div>
      ) : (
        <div className="audio-review-actions ocr-review-actions">
          <button className="primary-button compact" onClick={() => review("ACEITAR")} disabled={submitting}>
            <CheckCircle2 size={16} /> Aceitar texto
          </button>
          <button className="secondary-button" onClick={() => review("EDITAR")} disabled={submitting || !text.trim()}>
            Aplicar correções
          </button>
          <button className="secondary-button danger-text" onClick={() => review("REJEITAR")} disabled={submitting}>
            <X size={16} /> Rejeitar
          </button>
        </div>
      )}
      <p className="audio-original-note">O documento original é preservado independentemente da revisão.</p>
    </div>
  );
}

export function AIAssistancePanel({ request, defaultChannel = "WHATSAPP", onChanged, onUse, onError }) {
  const assistance = request.assistenciaIA;
  const result = assistance?.resultado || {};
  const suggestion = result.respostaSugerida || {};
  const [tone, setTone] = useState("ACOLHEDOR");
  const [channel, setChannel] = useState(defaultChannel);
  const [draft, setDraft] = useState({ canal: defaultChannel, assunto: "", conteudo: "" });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!suggestion.conteudo) return;
    setDraft({
      canal: suggestion.canal || defaultChannel,
      assunto: suggestion.assunto || "",
      conteudo: suggestion.conteudo,
    });
    setChannel(suggestion.canal || defaultChannel);
    setTone(suggestion.tom || "ACOLHEDOR");
  }, [assistance?.id, defaultChannel, suggestion.assunto, suggestion.canal, suggestion.conteudo, suggestion.tom]);

  async function refresh() {
    onChanged(await apiRequest(`/api/v1/solicitacoes/${request.id}`));
  }

  async function generate() {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/assistencia-ia`, {
        method: "POST",
        body: JSON.stringify({ canal: channel, tom: tone }),
      });
      await refresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function useSuggestion() {
    setSubmitting(true);
    onError("");
    onUse(draft);
    try {
      if (assistance.statusRevisao === "PENDENTE") {
        await apiRequest(`/api/v1/assistencias-ia/${assistance.id}/revisao`, {
          method: "POST",
          body: JSON.stringify({ acao: "EDITAR", valores: draft }),
        });
        await refresh();
      }
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function rejectSuggestion() {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/assistencias-ia/${assistance.id}/revisao`, {
        method: "POST",
        body: JSON.stringify({ acao: "REJEITAR" }),
      });
      await refresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!assistance || assistance.status === "FALHOU") {
    return (
      <div className="ai-assistance-panel">
        <div className="ai-assistance-heading"><Sparkles size={18} /><div><strong>Assistência de resposta</strong><small>Resumo, perguntas, documentos e próximos passos</small></div></div>
        {assistance?.erro && <p className="form-error">Não foi possível gerar as sugestões. Tente novamente.</p>}
        <div className="ai-assistance-controls">
          <label>Tom<select value={tone} onChange={(event) => setTone(event.target.value)}><option value="ACOLHEDOR">Acolhedor</option><option value="CLARO">Claro</option><option value="FORMAL">Formal</option><option value="OBJETIVO">Objetivo</option></select></label>
          <label>Canal<select value={channel} onChange={(event) => setChannel(event.target.value)}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
        </div>
        <button type="button" className="secondary-button action-button" onClick={generate} disabled={submitting}><Sparkles size={17} /> Gerar sugestões</button>
      </div>
    );
  }

  if (["PENDENTE", "PROCESSANDO"].includes(assistance.status)) {
    return <div className="ai-assistance-panel ai-processing"><div className="ai-assistance-heading"><Sparkles size={18} /><div><strong>Preparando assistência</strong><small>O histórico está sendo analisado localmente</small></div></div><div className="ai-progress" aria-label="Assistência em processamento"><span /></div></div>;
  }

  const reviewed = assistance.statusRevisao !== "PENDENTE";
  return (
    <div className="ai-assistance-panel">
      <div className="ai-assistance-heading">
        <Sparkles size={18} />
        <div><strong>Assistência de resposta</strong><small>{assistance.modelo} · {Math.round((assistance.confianca || 0) * 100)}% de confiança</small></div>
      </div>
      <div className="ai-assistance-summary"><span>Resumo para atendimento</span><p>{result.resumoHistorico}</p></div>
      <div className="ai-assistance-grid">
        <div><strong>Perguntas que faltam</strong><ul>{(result.perguntasFaltantes || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div><strong>Documentos a confirmar</strong><ul>{(result.documentosNecessarios || []).map((item) => <li key={`${item.nome}-${item.motivo}`}><b>{item.nome}</b>: {item.motivo}</li>)}</ul></div>
      </div>
      <div className="ai-next-steps"><strong>Próximos passos sugeridos</strong><ol>{(result.proximosPassos || []).map((item) => <li key={`${item.ordem}-${item.acao}`}><span>{item.responsavel}</span><div><b>{item.acao}</b><small>{item.justificativa}</small></div></li>)}</ol></div>
      <div className="ai-response-draft">
        <div className="form-grid">
          <label>Canal<select value={draft.canal} disabled={reviewed} onChange={(event) => setDraft((current) => ({ ...current, canal: event.target.value }))}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
          {draft.canal === "EMAIL" && <label>Assunto<input value={draft.assunto} disabled={reviewed} onChange={(event) => setDraft((current) => ({ ...current, assunto: event.target.value }))} /></label>}
        </div>
        <label>Resposta sugerida<textarea rows="6" value={draft.conteudo} disabled={reviewed} onChange={(event) => setDraft((current) => ({ ...current, conteudo: event.target.value }))} /></label>
      </div>
      <p className="ai-no-autosend"><ShieldAlert size={16} /> Esta sugestão não será enviada automaticamente. Revise e use o botão Registrar saída abaixo.</p>
      {!reviewed ? <div className="ai-assistance-actions"><button type="button" className="primary-button compact" onClick={useSuggestion} disabled={submitting || !draft.conteudo.trim()}><ArrowRight size={17} /> Usar na resposta</button><button type="button" className="secondary-button compact danger" onClick={rejectSuggestion} disabled={submitting}><X size={17} /> Rejeitar</button></div> : <div className={`ai-review-status review-${assistance.statusRevisao.toLowerCase()}`}><CheckCircle2 size={16} /> Revisão concluída: {assistance.statusRevisao === "REJEITADA" ? "sugestão rejeitada" : "rascunho transferido para revisão"}</div>}
      <button type="button" className="text-button ai-regenerate" onClick={generate} disabled={submitting}><RotateCcw size={15} /> Gerar nova versão</button>
    </div>
  );
}

export function AITriagePanel({ request, categories, agencies = [], onChanged, onError }) {
  const triage = request.triagemIA;
  const suggestion = triage?.resultado || {};
  const [submitting, setSubmitting] = useState(false);
  const [values, setValues] = useState({
    categoriaId: suggestion.categoriaId || "",
    orgaoId: suggestion.orgaoId || "",
    subcategoria: suggestion.subcategoria || "",
    prioridadeSugerida: suggestion.prioridadeSugerida || "MEDIA",
    impacto: suggestion.impacto || "MEDIO",
    urgencia: suggestion.urgencia || "MEDIO",
  });

  useEffect(() => {
    setValues({
      categoriaId: suggestion.categoriaId || "",
      orgaoId: suggestion.orgaoId || "",
      subcategoria: suggestion.subcategoria || "",
      prioridadeSugerida: suggestion.prioridadeSugerida || "MEDIA",
      impacto: suggestion.impacto || "MEDIO",
      urgencia: suggestion.urgencia || "MEDIO",
    });
  }, [
    suggestion.categoriaId,
    suggestion.impacto,
    suggestion.orgaoId,
    suggestion.prioridadeSugerida,
    suggestion.subcategoria,
    suggestion.urgencia,
  ]);

  async function refresh() {
    onChanged(await apiRequest(`/api/v1/solicitacoes/${request.id}`));
  }

  async function runTriage() {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/classificacao-ia`, {
        method: "POST",
      });
      await refresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function review(action) {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest(`/api/v1/classificacoes-ia/${triage.id}/revisao`, {
        method: "POST",
        body: JSON.stringify({
          acao: action,
          ...(action === "EDITAR" ? { valores: values } : {}),
        }),
      });
      await refresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function groupSuggestedDuplicate(candidate) {
    setSubmitting(true);
    onError("");
    try {
      await apiRequest("/api/v1/solicitacoes/agrupar-duplicadas", {
        method: "POST",
        body: JSON.stringify({
          solicitacaoIds: [request.id, candidate.id],
          motivo: `Similaridade semântica confirmada pelo usuário (${Math.round(candidate.pontuacao * 100)}%).`,
        }),
      });
      await refresh();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!triage || triage.status === "FALHOU") {
    return (
      <section className="drawer-section ai-triage-panel">
        <div className="ai-section-title">
          <span className="entity-icon"><Sparkles size={19} /></span>
          <div><h3>Triagem assistida</h3><small>Classificação sujeita à revisão humana</small></div>
        </div>
        {triage?.erro && <p className="form-error">{triage.erro}</p>}
        <button className="secondary-button action-button" onClick={runTriage} disabled={submitting}>
          <Sparkles size={17} /> {submitting ? "Agendando..." : "Executar triagem"}
        </button>
      </section>
    );
  }

  if (["PENDENTE", "PROCESSANDO"].includes(triage.status)) {
    return (
      <section className="drawer-section ai-triage-panel ai-processing">
        <div className="ai-section-title">
          <span className="entity-icon"><Sparkles size={19} /></span>
          <div><h3>Triagem em processamento</h3><small>O worker está analisando o relato</small></div>
        </div>
        <div className="ai-progress" aria-label="Triagem em processamento"><span /></div>
      </section>
    );
  }

  const reviewed = triage.statusRevisao !== "PENDENTE";
  const confidence = Math.round((triage.confianca || 0) * 100);
  const groupedIds = new Set((request.duplicidades || []).map((item) => item.id));
  const duplicateAnalysis = suggestion.analiseDuplicidade || {};
  const duplicateCandidates = (duplicateAnalysis.candidatos || []).filter(
    (candidate) => !groupedIds.has(candidate.id),
  );
  return (
    <section className={`drawer-section ai-triage-panel ${suggestion.emergencia ? "ai-emergency" : ""}`}>
      <header className="ai-triage-header">
        <div className="ai-section-title">
          <span className="entity-icon"><Sparkles size={19} /></span>
          <div>
            <h3>Triagem assistida</h3>
            <small>{triage.modelo} · prompt {triage.versaoPrompt}</small>
          </div>
        </div>
        <div className="ai-confidence" aria-label={`Confiança da sugestão: ${confidence}%`}>
          <span>Confiança</span>
          <strong>{confidence}%</strong>
          <span className="ai-confidence-track" aria-hidden="true">
            <span style={{ width: `${confidence}%` }} />
          </span>
        </div>
      </header>
      {suggestion.emergencia && (
        <div className="emergency-alert">
          <ShieldAlert size={20} />
          <div><strong>Possível emergência</strong><p>{suggestion.orientacaoEmergencia}</p></div>
        </div>
      )}
      {suggestion.conteudoOfensivo && (
        <div className="content-warning">
          <ShieldAlert size={19} />
          <div>
            <strong>Linguagem sensível identificada</strong>
            <p>O relato foi preservado e não teve seu atendimento bloqueado.</p>
            {(suggestion.marcadoresConteudo || []).length > 0 && (
              <small>{suggestion.marcadoresConteudo.join(" · ")}</small>
            )}
          </div>
        </div>
      )}
      <div className="ai-result-copy">
        <div>
          <span className="ai-content-label">Resumo do relato</span>
          <p className="ai-summary">{suggestion.resumo}</p>
        </div>
        <div>
          <span className="ai-content-label">Motivo da sugestão</span>
          <p className="muted-copy">{suggestion.justificativa}</p>
        </div>
        {suggestion.resumoEstruturado && (
          <div className="ai-structured-summary">
            <span className="ai-content-label">Resumo estruturado</span>
            <dl>
              <div><dt>Situação</dt><dd>{suggestion.resumoEstruturado.situacao}</dd></div>
              <div><dt>Local</dt><dd>{suggestion.resumoEstruturado.local || "Não informado"}</dd></div>
              <div><dt>Afetados</dt><dd>{suggestion.resumoEstruturado.afetados || "Não informado"}</dd></div>
            </dl>
            {(suggestion.resumoEstruturado.informacoesAusentes || []).length > 0 && (
              <p className="ai-missing-info">
                <strong>Informações ausentes:</strong>{" "}
                {suggestion.resumoEstruturado.informacoesAusentes.join(", ")}
              </p>
            )}
          </div>
        )}
        {entityEntries(suggestion.entidades).length > 0 && (
          <div>
            <span className="ai-content-label">Entidades identificadas</span>
            <div className="ai-entities">
              {entityEntries(suggestion.entidades).map(([label, value]) => (
                <span key={`${label}-${value}`}><strong>{label}</strong>{value}</span>
              ))}
            </div>
          </div>
        )}
        {duplicateCandidates.length > 0 && (
          <div className="ai-duplicate-analysis">
            <div className="ai-duplicate-heading">
              <div>
                <span className="ai-content-label">Possíveis duplicidades</span>
                <p>Compare os relatos antes de confirmar o agrupamento.</p>
              </div>
              <small>{duplicateAnalysis.modelo}</small>
            </div>
            <div className="ai-duplicate-list">
              {duplicateCandidates.map((candidate) => {
                const score = Math.round(candidate.pontuacao * 100);
                return (
                  <article key={candidate.id} className="ai-duplicate-item">
                    <div className="ai-duplicate-copy">
                      <div><strong>{candidate.protocolo}</strong><span>{score}% compatível</span></div>
                      <p>{candidate.titulo}</p>
                      <small>{(candidate.justificativas || []).join(" · ")}</small>
                    </div>
                    <button
                      className="secondary-button"
                      disabled={submitting}
                      onClick={() => groupSuggestedDuplicate(candidate)}
                    >
                      <Link2 size={16} /> Confirmar duplicidade
                    </button>
                  </article>
                );
              })}
            </div>
            <p className="ai-duplicate-notice">Nenhum registro é excluído; a confirmação apenas relaciona as solicitações.</p>
          </div>
        )}
      </div>
      <div className={`ai-classification ${reviewed ? "is-reviewed" : ""}`}>
        <div className="ai-classification-heading">
          <strong>Classificação sugerida</strong>
          <small>{reviewed ? "Valores aplicados na solicitação" : "Revise os valores antes de aplicar"}</small>
        </div>
        <div className="form-grid ai-category-grid">
          <label>Categoria<select disabled={reviewed} value={values.categoriaId} onChange={(event) => setValues((current) => ({ ...current, categoriaId: event.target.value }))}><option value="">Sem categoria</option>{categories.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
          <label>Subcategoria<input disabled={reviewed} value={values.subcategoria} onChange={(event) => setValues((current) => ({ ...current, subcategoria: event.target.value }))} /></label>
        </div>
        <label>Órgão sugerido<select disabled={reviewed} value={values.orgaoId} onChange={(event) => setValues((current) => ({ ...current, orgaoId: event.target.value }))}><option value="">Sem órgão sugerido</option>{agencies.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
        <div className="form-grid ai-level-grid">
          <label>Prioridade<select disabled={reviewed} value={values.prioridadeSugerida} onChange={(event) => setValues((current) => ({ ...current, prioridadeSugerida: event.target.value }))}><option value="BAIXA">Baixa</option><option value="MEDIA">Média</option><option value="ALTA">Alta</option><option value="CRITICA">Crítica</option></select></label>
          <label>Impacto<select disabled={reviewed} value={values.impacto} onChange={(event) => setValues((current) => ({ ...current, impacto: event.target.value }))}><LevelOptions /></select></label>
          <label>Urgência<select disabled={reviewed} value={values.urgencia} onChange={(event) => setValues((current) => ({ ...current, urgencia: event.target.value }))}><LevelOptions /></select></label>
        </div>
      </div>
      {reviewed ? (
        <div className={`ai-review-status review-${triage.statusRevisao.toLowerCase()}`}>
          {triage.statusRevisao === "REJEITADA" ? <X size={18} /> : <CheckCircle2 size={18} />}
          <div>
            <span>Revisão humana concluída</span>
            <strong>{reviewLabel(triage.statusRevisao)}</strong>
          </div>
        </div>
      ) : (
        <div className="ai-review-actions">
          <button className="primary-button compact" onClick={() => review("ACEITAR")} disabled={submitting}><CheckCircle2 size={17} /> Aceitar sugestão</button>
          <button className="secondary-button" onClick={() => review("EDITAR")} disabled={submitting}>Aplicar ajustes</button>
          <button className="secondary-button danger-text" onClick={() => review("REJEITAR")} disabled={submitting}><X size={17} /> Rejeitar</button>
        </div>
      )}
    </section>
  );
}

function ScheduledReturnItem({ item, onUpdate }) {
  const [scheduledAt, setScheduledAt] = useState(toLocalDateTime(item.agendadoPara));
  const active = item.status === "AGENDADO";
  const overdue = active && new Date(item.agendadoPara) < new Date();

  return <article className={`scheduled-return-item ${overdue ? "overdue" : ""}`}>
    <div className="return-summary">
      <strong>{item.responsavel}</strong>
      <small>{formatDate(item.agendadoPara)} · {returnStatusLabel(item.status)}</small>
    </div>
    {active && <>
      <input aria-label="Nova data do retorno" type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
      <div className="return-actions">
        <button type="button" className="icon-button" title="Reagendar" onClick={() => onUpdate(item.id, { agendadoPara: scheduledAt })}><CalendarClock size={17} /></button>
        <button type="button" className="icon-button" title="Concluir" onClick={() => onUpdate(item.id, { status: "CONCLUIDO" })}><SquareCheckBig size={17} /></button>
        <button type="button" className="icon-button" title="Cancelar" onClick={() => onUpdate(item.id, { status: "CANCELADO" })}><X size={17} /></button>
      </div>
    </>}
    {item.observacoes && <p className="return-notes">{item.observacoes}</p>}
  </article>;
}

function CloseButton({ onClick }) {
  return <button className="icon-button" onClick={onClick} aria-label="Fechar" title="Fechar"><X size={20} /></button>;
}

function StatusBadge({ status }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{statusLabel(status)}</span>;
}

function statusLabel(status) {
  return statuses.find(([value]) => value === status)?.[1] || status;
}

function sourceLabel(source) {
  return sources.find(([value]) => value === source)?.[1] || source;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function toLocalDateTime(value) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function returnStatusLabel(value) {
  return { AGENDADO: "Agendado", CONCLUIDO: "Concluído", CANCELADO: "Cancelado" }[value] || value;
}

function formatBytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(value) {
  if (value == null) return "duração não informada";
  const total = Math.round(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes ? `${minutes}min ${seconds}s` : `${seconds}s`;
}

function transcriptionReviewLabel(value) {
  return {
    ACEITA: "Transcrição aceita",
    EDITADA: "Transcrição corrigida",
    REJEITADA: "Transcrição rejeitada",
  }[value] || value;
}

function ocrReviewLabel(value) {
  return {
    ACEITO: "Texto aceito",
    EDITADO: "Texto corrigido",
    REJEITADO: "Texto rejeitado",
  }[value] || value;
}

function slaLabel(value) {
  return {
    NO_PRAZO: "no prazo",
    PROXIMO_DO_PRAZO: "próximo",
    ATRASADO: "atrasado",
    CONCLUIDO_NO_PRAZO: "concluído no prazo",
    CONCLUIDO_ATRASADO: "concluído com atraso",
  }[value] || value;
}

function removeEmpty(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== ""));
}

function LevelOptions() {
  return <><option value="">Não informado</option><option value="BAIXO">Baixo</option><option value="MEDIO">Médio</option><option value="ALTO">Alto</option><option value="CRITICO">Crítico</option></>;
}

function contactDestination(citizen, channel) {
  if (!citizen || !channel) return "";
  const accepted = {
    WHATSAPP: ["WHATSAPP", "TELEFONE", "CELULAR"],
    TELEFONE: ["TELEFONE", "CELULAR", "WHATSAPP"],
    EMAIL: ["EMAIL"],
  }[channel] || [];
  const contact = (citizen.contatos || []).find((item) => accepted.includes(item.tipo));
  if (contact) return contact.valor;
  if (channel === "PRESENCIAL") {
    const address = citizen.enderecos?.[0];
    return address?.endereco || address?.logradouro || "";
  }
  return "";
}

function contactResultLabel(value) {
  return {
    REALIZADO: "Contato realizado",
    SEM_RESPOSTA: "Sem resposta",
    FALHOU: "Falhou",
    AGENDADO: "Retorno agendado",
  }[value] || value;
}

function reviewLabel(value) {
  return {
    ACEITA: "Sugestão aceita",
    EDITADA: "Sugestão ajustada",
    REJEITADA: "Sugestão rejeitada",
  }[value] || value;
}

function entityEntries(entities = {}) {
  const labels = {
    endereco: "Endereço",
    bairro: "Bairro",
    datas: "Data",
    pessoas: "Pessoa",
    protocolos: "Protocolo",
    servicos: "Serviço",
  };
  return Object.entries(entities).flatMap(([key, value]) => {
    const values = Array.isArray(value) ? value : [value];
    return values
      .filter(Boolean)
      .map((item) => [labels[key] || key, String(item)]);
  });
}
