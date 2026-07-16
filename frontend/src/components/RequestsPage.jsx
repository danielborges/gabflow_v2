import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Filter,
  Link2,
  RotateCcw,
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
import { useCallback, useEffect, useState } from "react";
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

export function RequestsPage() {
  const [items, setItems] = useState([]);
  const [references, setReferences] = useState(emptyReferences);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);

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
        <button className="primary-button compact" onClick={() => setShowCreate(true)}>
          <Plus size={18} /> Nova solicitação
        </button>
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

      {showCreate && (
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
          requests={items}
          references={references}
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

function RequestDetails({ request, requests, references, onClose, onChanged }) {
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
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    }
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
    try {
      await apiRequest(`/api/v1/solicitacoes/${request.id}/anexos`, {
        method: "POST",
        body: formData,
      });
      setAttachment(null);
      event.currentTarget.reset();
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
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
  const duplicateCandidates = requests.filter((item) => item.id !== request.id);
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

          <section className="drawer-section">
            <h3>Acompanhamento</h3>
            <div className="form-grid">
              <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}>{statuses.slice(1).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label>Responsável<select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}><option value="">Fila geral</option>{references.users.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
            </div>
            <label>Categoria<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">Sem categoria</option>{references.categories.map((item) => <option key={item.id} value={item.id}>{item.nome} ({item.slaHoras}h)</option>)}</select></label>
            {request.prazo && <p className="muted-copy">Prazo de atendimento: <strong>{formatDate(request.prazo)}</strong></p>}
            {closing && <><label>Motivo do encerramento<textarea rows="2" value={reason} onChange={(event) => setReason(event.target.value)} /></label><label>Evidência ou justificativa<textarea rows="2" value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label></>}
            <button className="secondary-button action-button" onClick={updateRequest}><CheckCircle2 size={17} /> Atualizar acompanhamento</button>
          </section>

          <section className="drawer-section">
            <h3>Encaminhamentos</h3>
            {(request.encaminhamentos || []).map((item) => <article className="forwarding-item" key={item.id}><div><strong>{item.orgao}</strong><small>{item.protocoloExterno || "Sem protocolo externo"} · {item.status}</small></div>{item.resposta ? <p>{item.resposta}</p> : <form onSubmit={(event) => registerAgencyResponse(event, item.id)}><input required value={externalResponse} onChange={(event) => setExternalResponse(event.target.value)} placeholder="Registrar resposta do órgão" /><button className="secondary-button">Registrar</button></form>}</article>)}
            {(request.encaminhamentos || []).length === 0 && <p className="muted-copy">Nenhum encaminhamento registrado.</p>}
            <form className="duplicate-form" onSubmit={addForwarding}>
              <label>Órgão<select required value={forwarding.orgaoId} onChange={(event) => setForwarding((current) => ({ ...current, orgaoId: event.target.value }))}><option value="">Selecione</option>{references.agencies.filter((item) => item.ativa).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
              <div className="form-grid"><label>Protocolo externo<input value={forwarding.protocoloExterno} onChange={(event) => setForwarding((current) => ({ ...current, protocoloExterno: event.target.value }))} /></label><label>Prazo<input type="datetime-local" value={forwarding.prazo} onChange={(event) => setForwarding((current) => ({ ...current, prazo: event.target.value }))} /></label></div>
              <button className="secondary-button action-button"><Send size={17} /> Encaminhar</button>
            </form>
          </section>

          <section className="drawer-section">
            <h3>Tarefas</h3>
            <div className="task-list">
              {(request.tarefas || []).map((task) => <label key={task.id} className={task.status === "CONCLUIDA" ? "task-item completed" : "task-item"}><input type="checkbox" checked={task.status === "CONCLUIDA"} onChange={() => toggleTask(task)} /><span><strong>{task.titulo}</strong><small>{task.prazo ? `Prazo: ${formatDate(task.prazo)}` : task.prioridade}</small></span></label>)}
              {(request.tarefas || []).length === 0 && <p className="muted-copy">Nenhuma tarefa criada.</p>}
            </div>
            <form className="inline-form" onSubmit={addTask}><input required minLength="3" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Nova tarefa" /><button className="primary-button compact" title="Adicionar tarefa"><Plus size={17} /> Adicionar</button></form>
          </section>

          <section className="drawer-section">
            <h3>Anexos</h3>
            <div className="attachment-list">
              {(request.anexos || []).map((item) => <a key={item.id} href={item.downloadUrl} target="_blank" rel="noreferrer"><Paperclip size={16} /><span><strong>{item.nome}</strong><small>{formatBytes(item.tamanho)} · {item.statusVerificacao}</small></span></a>)}
              {(request.anexos || []).length === 0 && <p className="muted-copy">Nenhum anexo enviado.</p>}
            </div>
            <form className="upload-form" onSubmit={uploadAttachment}><input aria-label="Selecionar anexo" type="file" onChange={(event) => setAttachment(event.target.files[0])} /><button className="secondary-button" disabled={!attachment}><Upload size={17} /> Enviar</button></form>
          </section>

          <section className="drawer-section">
            <h3>Duplicidades</h3>
            {(request.duplicidades || []).length > 0 && <div className="duplicate-list">{request.duplicidades.map((item) => <span key={item.id}><Link2 size={15} /> {item.protocolo}</span>)}</div>}
            <form className="duplicate-form" onSubmit={groupDuplicate}>
              <label>Solicitação relacionada<select required value={duplicateId} onChange={(event) => setDuplicateId(event.target.value)}><option value="">Selecione</option>{duplicateCandidates.map((item) => <option key={item.id} value={item.id}>{item.protocolo} · {item.titulo}</option>)}</select></label>
              <label>Motivo<input required value={duplicateReason} onChange={(event) => setDuplicateReason(event.target.value)} placeholder="Mesmo relato, local e ocorrência" /></label>
              <button className="secondary-button action-button"><Link2 size={17} /> Agrupar sem excluir</button>
            </form>
          </section>

          <section className="drawer-section">
            <h3>Resposta ao cidadão</h3>
            <form className="communication-form" onSubmit={sendResponse}>
              <label>Template<select value={response.templateId} onChange={(event) => selectResponseTemplate(event.target.value)}><option value="">Resposta livre</option>{references.templates.filter((item) => item.ativa && (!item.categoriaId || item.categoriaId === request.categoriaId)).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
              <label>Canal<select value={response.canal} onChange={(event) => setResponse((current) => ({ ...current, canal: event.target.value }))}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
              {response.canal === "EMAIL" && <label>Assunto<input required value={response.assunto} onChange={(event) => setResponse((current) => ({ ...current, assunto: event.target.value }))} placeholder={`Atualização da solicitação ${request.protocolo}`} /></label>}
              <label>Mensagem<textarea required rows="5" value={response.conteudo} onChange={(event) => setResponse((current) => ({ ...current, conteudo: event.target.value }))} placeholder="Visualize e ajuste a mensagem antes de registrar." /></label>
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

function ScheduledReturnItem({ item, onUpdate }) {
  const [scheduledAt, setScheduledAt] = useState(toLocalDateTime(item.agendadoPara));
  const active = item.status === "AGENDADO";
  const overdue = active && new Date(item.agendadoPara) < new Date();

  return <article className={`scheduled-return-item ${overdue ? "overdue" : ""}`}>
    <div>
      <strong>{item.responsavel}</strong>
      <small>{formatDate(item.agendadoPara)} · {returnStatusLabel(item.status)}</small>
      {item.observacoes && <p>{item.observacoes}</p>}
    </div>
    {active && <>
      <input aria-label="Nova data do retorno" type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
      <div className="return-actions">
        <button type="button" className="icon-button" title="Reagendar" onClick={() => onUpdate(item.id, { agendadoPara: scheduledAt })}><CalendarClock size={17} /></button>
        <button type="button" className="icon-button" title="Concluir" onClick={() => onUpdate(item.id, { status: "CONCLUIDO" })}><SquareCheckBig size={17} /></button>
        <button type="button" className="icon-button" title="Cancelar" onClick={() => onUpdate(item.id, { status: "CANCELADO" })}><X size={17} /></button>
      </div>
    </>}
  </article>;
}

function CloseButton({ onClick }) {
  return <button className="icon-button" onClick={onClick} aria-label="Fechar" title="Fechar"><X size={20} /></button>;
}

function StatusBadge({ status }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{statuses.find(([value]) => value === status)?.[1] || status}</span>;
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
