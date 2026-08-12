import { AlertTriangle, Bot, CheckCircle2, Clock3, Download, FileAudio, FileText, Image, Inbox, Link2, MessageCircle, MessageSquare, Plus, RotateCw, Search, Send, Settings2, ShieldCheck, Sparkles, UserCheck, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";
import { contactPlaceholderForChannel, formatBrazilianPhone, isValidContactByChannel } from "../contactValidation";

const emptyForm = {
  canal: "WHATSAPP",
  remetenteNome: "",
  remetenteContato: "",
  assunto: "",
  conteudo: "",
};

export function ChannelsPage({ user, onStartAssistedRegistration }) {
  const tenantId = user?.tenant?.id;
  const [messages, setMessages] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [conversationSummary, setConversationSummary] = useState({});
  const [conversationResponsibles, setConversationResponsibles] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [citizenName, setCitizenName] = useState("");
  const [requestDraft, setRequestDraft] = useState({ titulo: "", descricao: "", endereco: "", categoriaId: "" });
  const [requestConfirmed, setRequestConfirmed] = useState(false);
  const [flowBusy, setFlowBusy] = useState(false);
  const [flowLaunchNotice, setFlowLaunchNotice] = useState("");
  const [protocolAccess, setProtocolAccess] = useState(null);
  const confirmationKey = useRef(null);
  const [conversationFilters, setConversationFilters] = useState({ q: "", modo: "", naoLidas: false });
  const [reviews, setReviews] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [selectedCandidates, setSelectedCandidates] = useState({});
  const [reviewStatus, setReviewStatus] = useState("PENDENTE");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [summary, setSummary] = useState({});
  const [responsibles, setResponsibles] = useState([]);
  const [settings, setSettings] = useState({ baseLegalPadrao: "", slaHoras: 24, retencaoDias: 365 });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const conversationQuery = new URLSearchParams();
      if (conversationFilters.q.trim()) conversationQuery.set("q", conversationFilters.q.trim());
      if (conversationFilters.modo) conversationQuery.set("modo", conversationFilters.modo);
      if (conversationFilters.naoLidas) conversationQuery.set("naoLidas", "true");
      const [messageData, reviewData, settingsData, conversationData] = await Promise.all([
        apiRequest("/api/v1/canais/mensagens"),
        apiRequest(`/api/v1/canais/revisoes-identidade?status=${reviewStatus}${assigneeFilter ? `&responsavelId=${assigneeFilter}` : ""}`),
        apiRequest("/api/v1/canais/configuracao-cadastro-assistido"),
        tenantId ? apiRequest(`/api/v1/tenants/${tenantId}/conversations?${conversationQuery}`) : Promise.resolve({ content: [], resumo: {}, responsaveis: [] }),
      ]);
      setMessages(messageData.content);
      setReviews(reviewData.content);
      setSummary(reviewData.resumo || {});
      setResponsibles(reviewData.responsaveis || []);
      setSettings(settingsData);
      setConversations(conversationData.content || []);
      setConversationSummary(conversationData.resumo || {});
      setConversationResponsibles(conversationData.responsaveis || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [reviewStatus, assigneeFilter, tenantId, conversationFilters.q, conversationFilters.modo, conversationFilters.naoLidas]);

  useEffect(() => { load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (form.remetenteContato && !isValidContactByChannel(form.canal, form.remetenteContato)) {
      setError("Informe um contato válido para o canal selecionado.");
      return;
    }
    try {
      await apiRequest("/api/v1/canais/mensagens", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm(emptyForm);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function decideReview(review, decisao) {
    setError("");
    const citizenId = selectedCandidates[review.id] || review.candidatos[0]?.id;
    if (decisao === "VINCULAR" && !citizenId) {
      setError("Selecione um cidadão sugerido para concluir o vínculo.");
      return;
    }
    try {
      await apiRequest(`/api/v1/canais/revisoes-identidade/${review.id}/decisao`, {
        method: "POST",
        body: JSON.stringify({ decisao, cidadaoId: citizenId }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function assignReview(reviewId, responsibleId) {
    try {
      await apiRequest(`/api/v1/canais/revisoes-identidade/${reviewId}/atribuicao`, {
        method: "PUT",
        body: JSON.stringify({ responsavelId: responsibleId || null }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function prepareRegistration(review) {
    setError("");
    try {
      await apiRequest(`/api/v1/canais/revisoes-identidade/${review.id}/preparar-cadastro`, { method: "POST" });
      onStartAssistedRegistration?.(review.id);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function reopenReview(review) {
    const justification = window.prompt("Informe a justificativa para reabrir esta revisão:");
    if (!justification) return;
    try {
      await apiRequest(`/api/v1/canais/revisoes-identidade/${review.id}/reabrir`, {
        method: "POST",
        body: JSON.stringify({ justificativa: justification }),
      });
      setReviewStatus("PENDENTE");
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    try {
      const saved = await apiRequest("/api/v1/canais/configuracao-cadastro-assistido", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSettings(saved);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function executeRetention() {
    try {
      const result = await apiRequest("/api/v1/canais/revisoes-identidade/retencao/executar", { method: "POST" });
      setError(`Retenção executada: ${result.processadas} mensagem(ns) minimizada(s).`);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function convertMessage(item) {
    setError("");
    try {
      await apiRequest(`/api/v1/canais/mensagens/${item.id}/solicitacao`, {
        method: "POST",
        body: JSON.stringify({
          titulo: item.assunto || `Mensagem via ${channelLabel(item.canal)}`,
          descricao: item.conteudo,
        }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function openConversation(item) {
    try {
      if (selectedConversation?.id && selectedConversation.id !== item.id) {
        setProtocolAccess(null);
        setFlowLaunchNotice("");
      }
      const detail = await apiRequest(`/api/v1/tenants/${tenantId}/conversations/${item.id}`);
      setSelectedConversation(detail);
      const draft = detail.jornada?.rascunhoSolicitacao;
      setRequestDraft({
        titulo: draft?.titulo || "",
        descricao: draft?.descricao || "",
        endereco: draft?.endereco || "",
        categoriaId: draft?.categoriaId || "",
      });
      setRequestConfirmed(false);
      if (detail.naoLidas > 0) {
        await apiRequest(`/api/v1/tenants/${tenantId}/conversations/${item.id}/read`, { method: "POST" });
        setSelectedConversation((current) => ({ ...current, naoLidas: 0 }));
        setConversations((current) => current.map((conversation) => conversation.id === item.id ? { ...conversation, naoLidas: 0 } : conversation));
      }
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function changeConversationAssignment(responsavelId) {
    try {
      await apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/assignment`, {
        method: "PUT",
        body: JSON.stringify({ responsavelId: responsavelId || null }),
      });
      await load();
      await openConversation({ id: selectedConversation.id });
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function startConversationHandoff() {
    try {
      await apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/handoff`, {
        method: "POST",
        body: JSON.stringify({ assigneeId: selectedConversation.responsavel?.id || null, reason: "Atendimento assumido pela caixa de entrada." }),
      });
      await openConversation({ id: selectedConversation.id });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function resumeConversationBot() {
    try {
      await apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/resume-bot`, {
        method: "POST",
        body: JSON.stringify({ reason: "Automação retomada pelo gestor na caixa de entrada." }),
      });
      await openConversation({ id: selectedConversation.id });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function runConversationFlow(action) {
    setFlowBusy(true);
    setError("");
    try {
      await action();
      await openConversation({ id: selectedConversation.id });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setFlowBusy(false);
    }
  }

  function acknowledgeConversationPrivacy() {
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/privacy`, {
      method: "POST",
      body: JSON.stringify({
        baseLegal: settings.baseLegalPadrao || "EXECUCAO_POLITICA_PUBLICA",
        consentimentoNecessario: false,
      }),
    }));
  }

  function identifyConversationCitizen(cidadaoId) {
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/citizen`, {
      method: "POST",
      body: JSON.stringify(cidadaoId
        ? { cidadaoId, confirmado: true }
        : { nome: citizenName, confirmado: true }),
    })).then(() => setCitizenName(""));
  }

  function saveConversationRequestDraft(event) {
    event.preventDefault();
    confirmationKey.current = null;
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/request-draft`, {
      method: "PUT",
      body: JSON.stringify(requestDraft),
    }));
  }

  function confirmConversationRequest() {
    if (!confirmationKey.current) {
      confirmationKey.current = `whatsapp-${selectedConversation.id}-${Date.now()}`;
    }
    setFlowBusy(true);
    setError("");
    return apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/request-draft/confirm`, {
      method: "POST",
      headers: { "Idempotency-Key": confirmationKey.current },
      body: JSON.stringify({ confirmado: true }),
    }).then(async (result) => {
      if (result.chaveAcompanhamento) setProtocolAccess(result);
      await openConversation({ id: selectedConversation.id });
      await load();
    }).catch((requestError) => setError(requestError.message)).finally(() => setFlowBusy(false));
  }

  function launchConversationFlow(flowKey) {
    setFlowBusy(true);
    setError("");
    setFlowLaunchNotice("");
    return apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/flows/${flowKey}/launch`, {
      method: "POST",
    }).then(async (result) => {
      setFlowLaunchNotice(result.modo === "FLOW"
        ? "Envio do Flow solicitado. A resposta serÃ¡ validada e aplicada automaticamente."
        : "Flow indisponÃ­vel neste ambiente. A coleta guiada foi iniciada e o formulÃ¡rio manual permanece disponÃ­vel.");
      await openConversation({ id: selectedConversation.id });
      await load();
    }).catch((requestError) => setError(requestError.message)).finally(() => setFlowBusy(false));
  }

  function reviewConversationMedia(assetId, action, text = null) {
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/whatsapp/media/${assetId}/review`, {
      method: "POST",
      body: JSON.stringify({ acao: action, texto: text }),
    }));
  }

  function retryConversationMedia(assetId) {
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/whatsapp/media/${assetId}/retry`, { method: "POST" }));
  }

  function sendConversationMessage(payload) {
    return runConversationFlow(() => apiRequest(`/api/v1/tenants/${tenantId}/conversations/${selectedConversation.id}/messages`, {
      method: "POST",
      headers: { "Idempotency-Key": `inbox-${selectedConversation.id}-${Date.now()}` },
      body: JSON.stringify(payload),
    }));
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Ecossistema</p>
          <h1>Canais assistidos</h1>
          <p>Revise identidades recebidas por WhatsApp e e-mail antes de vinculá-las ao cadastro.</p>
        </div>
        <button className="secondary-button" onClick={load} disabled={loading}><RotateCw size={16} /> Atualizar</button>
      </section>

      {error && <p className="form-error channel-page-error" role="alert">{error}</p>}

      {tenantId && <section className="inbox-v2-shell" aria-label="Caixa de entrada WhatsApp">
        <header className="inbox-v2-header">
          <div><span className="inbox-v2-kicker"><MessageCircle size={15} /> Caixa de entrada 2.0</span><h2>Conversas do gabinete</h2><p>Atendimento contínuo, organizado por cidadão e com handoff seguro.</p></div>
          <div className="inbox-v2-metrics"><span><strong>{conversationSummary.total || 0}</strong> conversas</span><span><strong>{conversationSummary.naoLidas || 0}</strong> não lidas</span><span><strong>{conversationSummary.humanas || 0}</strong> humanas</span></div>
        </header>
        <div className="inbox-v2-grid">
          <aside className="inbox-v2-list-panel">
            <div className="inbox-v2-filters">
              <label className="inbox-v2-search"><Search size={16} /><input aria-label="Buscar conversas" value={conversationFilters.q} onChange={(event) => setConversationFilters((current) => ({ ...current, q: event.target.value }))} placeholder="Nome ou WhatsApp" /></label>
              <select aria-label="Filtrar modo da conversa" value={conversationFilters.modo} onChange={(event) => setConversationFilters((current) => ({ ...current, modo: event.target.value }))}><option value="">Todos os modos</option><option value="BOT">Automação</option><option value="HUMAN">Atendimento humano</option></select>
              <label className="inbox-v2-unread"><input type="checkbox" checked={conversationFilters.naoLidas} onChange={(event) => setConversationFilters((current) => ({ ...current, naoLidas: event.target.checked }))} /> Somente não lidas</label>
            </div>
            <div className="inbox-v2-conversations">
              {conversations.map((conversation) => <button type="button" key={conversation.id} className={`inbox-v2-conversation ${selectedConversation?.id === conversation.id ? "active" : ""}`} onClick={() => openConversation(conversation)}>
                <span className="inbox-v2-avatar">{initials(conversation.contato.nome)}</span>
                <span className="inbox-v2-conversation-copy"><strong>{conversation.contato.nome}</strong><small>{conversation.ultimaMensagem?.conteudo || "Conversa iniciada"}</small><em>{conversation.responsavel?.nome || "Sem responsável"} · {formatDate(conversation.ultimaMensagemEm)}</em></span>
                <span className="inbox-v2-conversation-state"><i className={`mode-${conversation.modo.toLowerCase()}`}>{conversation.modo === "HUMAN" ? "Humano" : "Bot"}</i>{conversation.naoLidas > 0 && <b>{conversation.naoLidas}</b>}</span>
              </button>)}
              {!loading && conversations.length === 0 && <p className="inbox-v2-empty">Nenhuma conversa corresponde aos filtros.</p>}
            </div>
          </aside>
          <article className="inbox-v2-detail">
            {!selectedConversation && <div className="inbox-v2-placeholder"><MessageSquare size={32} /><strong>Selecione uma conversa</strong><p>O histórico, o responsável e as ações de atendimento aparecerão aqui.</p></div>}
            {selectedConversation && <>
              <header className="inbox-v2-contact-header"><span className="inbox-v2-avatar large">{initials(selectedConversation.contato.nome)}</span><div><h3>{selectedConversation.contato.nome}</h3><p>{selectedConversation.contato.whatsappMascarado} · {stateLabel(selectedConversation.estado)}</p></div><span className={`inbox-v2-window ${selectedConversation.janelaAberta ? "open" : "closed"}`}><Clock3 size={14} /> {selectedConversation.janelaAberta ? `Janela até ${formatDate(selectedConversation.janelaExpiraEm)}` : "Janela encerrada"}</span></header>
              <div className="inbox-v2-toolbar"><label>Responsável<select value={selectedConversation.responsavel?.id || ""} onChange={(event) => changeConversationAssignment(event.target.value)}><option value="">Sem responsável</option>{conversationResponsibles.map((person) => <option key={person.id} value={person.id}>{person.nome}</option>)}</select></label>{selectedConversation.modo === "BOT" ? <button className="primary-button compact" type="button" onClick={startConversationHandoff}><UserCheck size={16} /> Assumir atendimento</button> : ["admin", "manager"].includes(user?.role) && <button className="secondary-button compact" type="button" onClick={resumeConversationBot}><Bot size={16} /> Retomar automação</button>}</div>
              {selectedConversation.modo === "HUMAN" && <p className="inbox-v2-human-lock"><ShieldCheck size={16} /> Automação pausada. Somente a equipe atende esta conversa.</p>}
              {selectedConversation.jornada && <ConversationServiceFlow
                conversation={selectedConversation}
                citizenName={citizenName}
                setCitizenName={setCitizenName}
                requestDraft={requestDraft}
                setRequestDraft={setRequestDraft}
                requestConfirmed={requestConfirmed}
                setRequestConfirmed={setRequestConfirmed}
                protocolAccess={protocolAccess}
                launchNotice={flowLaunchNotice}
                busy={flowBusy}
                onAcknowledgePrivacy={acknowledgeConversationPrivacy}
                onIdentifyCitizen={identifyConversationCitizen}
                onSaveDraft={saveConversationRequestDraft}
                onConfirmRequest={confirmConversationRequest}
                onLaunchFlow={launchConversationFlow}
              />}
              {selectedConversation.midias?.length > 0 && <ConversationMediaPanel assets={selectedConversation.midias} busy={flowBusy} onReview={reviewConversationMedia} onRetry={retryConversationMedia} />}
              <div className="inbox-v2-thread">{selectedConversation.mensagens.map((message) => <div key={message.id} className={`inbox-v2-bubble ${message.direcao.toLowerCase()}`}><p>{message.conteudo || `[${message.tipo}]`}</p><small>{formatDate(message.ocorridaEm)} · {message.status}</small></div>)}</div>
              <ConversationComposer conversation={selectedConversation} busy={flowBusy} onSend={sendConversationMessage} />
            </>}
          </article>
        </div>
      </section>}

      <section className="channel-operations-summary" aria-label="Resumo da fila">
        <article><strong>{summary.pendentes || 0}</strong><span>Pendentes</span></article>
        <article><strong>{summary.vencidas || 0}</strong><span>Vencidas</span></article>
        <article><strong>{summary.vinculadas || 0}</strong><span>Vinculadas</span></article>
        <article><strong>{summary.descartadas || 0}</strong><span>Descartadas</span></article>
      </section>

      {["admin", "manager"].includes(user?.role) && <form className="channel-settings-panel" onSubmit={saveSettings}>
        <div className="settings-title"><Settings2 size={20} /><div><strong>Operação do cadastro assistido</strong><small>Configuração aplicada somente a este gabinete.</small></div></div>
        <label>Base legal padrão<select value={settings.baseLegalPadrao || ""} onChange={(event) => setSettings((current) => ({ ...current, baseLegalPadrao: event.target.value }))} required><option value="">Selecione</option><option value="EXECUCAO_POLITICA_PUBLICA">Execução de política pública</option><option value="CONSENTIMENTO">Consentimento</option><option value="LEGITIMO_INTERESSE">Legítimo interesse</option></select></label>
        <label>SLA (horas)<input type="number" min="1" max="720" value={settings.slaHoras} onChange={(event) => setSettings((current) => ({ ...current, slaHoras: Number(event.target.value) }))} /></label>
        <label>Retenção (dias)<input type="number" min="30" max="3650" value={settings.retencaoDias} onChange={(event) => setSettings((current) => ({ ...current, retencaoDias: Number(event.target.value) }))} /></label>
        <button className="primary-button compact" type="submit">Salvar operação</button>
        <button className="secondary-button compact" type="button" onClick={executeRetention}>Executar retenção</button>
      </form>}

      <section className="channel-review-section">
        <header className="channel-review-header">
          <div className="settings-title"><ShieldCheck size={21} /><div><strong>Fila de revisão humana</strong><small>Nenhum cidadão é criado ou mesclado automaticamente.</small></div></div>
          <label>Status<select aria-label="Filtrar revisões por status" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
            <option value="PENDENTE">Pendentes</option>
            <option value="VINCULADA">Vinculadas</option>
            <option value="DESCARTADA">Descartadas</option>
          </select></label>
          <label>Responsável<select aria-label="Filtrar revisões por responsável" value={assigneeFilter} onChange={(event) => setAssigneeFilter(event.target.value)}><option value="">Todos</option><option value="SEM_RESPONSAVEL">Sem responsável</option>{responsibles.map((person) => <option value={person.id} key={person.id}>{person.nome}</option>)}</select></label>
        </header>
        <div className="channel-review-list">
          {!loading && reviews.length === 0 && <p className="muted-copy">Nenhuma revisão neste status.</p>}
          {reviews.map((review) => (
            <article className="channel-review-card" key={review.id}>
              <header>
                <span className="entity-icon"><Inbox size={19} /></span>
                <div>
                  <strong>{review.mensagem.assunto || review.mensagem.remetenteNome || channelLabel(review.mensagem.canal)}</strong>
                  <small>{channelLabel(review.mensagem.canal)} · {review.mensagem.remetenteContatoMascarado || "contato não informado"} · {formatDate(review.mensagem.recebidaEm)}</small>
                </div>
                <span className={`channel-review-status status-${review.status.toLowerCase()}`}>{review.status}</span>
              </header>
              <div className={`channel-review-operation ${review.vencida ? "overdue" : ""}`}><Clock3 size={15} /><span>{review.vencida ? "SLA vencido" : `Prazo: ${formatDate(review.prazoEm)}`}</span><label>Responsável<select aria-label={`Responsável por ${review.mensagem.assunto || review.id}`} value={review.responsavelId || ""} onChange={(event) => assignReview(review.id, event.target.value)}><option value="">Não atribuído</option>{responsibles.map((person) => <option value={person.id} key={person.id}>{person.nome}</option>)}</select></label></div>
              <p>{review.mensagem.conteudo}</p>
              <div className="channel-resolution-summary">
                <strong>{resolutionLabel(review.estadoResolucao)}</strong>
                {review.criterios.length > 0 && <small>Critério: contato normalizado exato no mesmo gabinete.</small>}
              </div>
              {review.status === "PENDENTE" && review.candidatos.length > 0 && <fieldset className="channel-candidates">
                <legend>Selecione o cidadão</legend>
                {review.candidatos.map((candidate) => <label key={candidate.id}>
                  <input
                    type="radio"
                    name={`candidate-${review.id}`}
                    checked={(selectedCandidates[review.id] || review.candidatos[0].id) === candidate.id}
                    onChange={() => setSelectedCandidates((current) => ({ ...current, [review.id]: candidate.id }))}
                  />
                  <span><strong>{candidate.nomeSocial || candidate.nome}</strong>{candidate.nomeSocial && <small>Cadastro: {candidate.nome}</small>}</span>
                </label>)}
              </fieldset>}
              {review.status === "PENDENTE" && review.candidatos.length === 0 && <div className="channel-no-match"><ShieldCheck size={17} /><span>Sem cadastro correspondente. O cadastro automático permanece bloqueado; faça o cadastro manual após validar a identidade.</span></div>}
              {review.status === "PENDENTE" && <div className="channel-review-actions">
                {review.candidatos.length > 0 && <button className="primary-button compact" type="button" onClick={() => decideReview(review, "VINCULAR")}><Link2 size={16} /> Vincular cidadão</button>}
                <button className="secondary-button compact" type="button" onClick={() => prepareRegistration(review)}><UserPlus size={16} /> Preparar novo cadastro</button>
                <button className="secondary-button compact danger" type="button" onClick={() => decideReview(review, "DESCARTAR")}><X size={16} /> Descartar sugestão</button>
              </div>}
              {review.status !== "PENDENTE" && <div className="channel-reviewed-by"><CheckCircle2 size={16} /> Revisada por {review.revisadoPor || "usuário autorizado"} em {formatDate(review.revisadaEm)}{["admin", "manager"].includes(user?.role) && <button className="secondary-button compact" type="button" onClick={() => reopenReview(review)}>Reabrir</button>}</div>}
            </article>
          ))}
        </div>
      </section>

      <section className="admin-layout agenda-layout channel-inbox-layout">
        <form className="settings-form" onSubmit={submit}>
          <div className="settings-title"><MessageSquare size={21} /><div><strong>Registrar mensagem</strong><small>Entrada manual para testes e atendimento assistido.</small></div></div>
          <div className="form-grid">
            <label>Canal<select value={form.canal} onChange={(event) => setForm((current) => ({ ...current, canal: event.target.value }))}>
              <option value="WHATSAPP">WhatsApp</option>
              <option value="EMAIL">E-mail</option>
              <option value="REDE_SOCIAL">Rede social</option>
            </select></label>
            <label>Contato<input type={form.canal === "EMAIL" ? "email" : "text"} inputMode={form.canal === "EMAIL" ? "email" : form.canal === "WHATSAPP" ? "numeric" : "text"} placeholder={contactPlaceholderForChannel(form.canal)} maxLength={form.canal === "WHATSAPP" ? 15 : undefined} value={form.remetenteContato} onChange={(event) => setForm((current) => ({ ...current, remetenteContato: form.canal === "WHATSAPP" ? formatBrazilianPhone(event.target.value) : event.target.value }))} /></label>
          </div>
          <label>Nome<input value={form.remetenteNome} onChange={(event) => setForm((current) => ({ ...current, remetenteNome: event.target.value }))} /></label>
          <label>Assunto<input value={form.assunto} onChange={(event) => setForm((current) => ({ ...current, assunto: event.target.value }))} /></label>
          <label>Mensagem<textarea required rows="5" value={form.conteudo} onChange={(event) => setForm((current) => ({ ...current, conteudo: event.target.value }))} /></label>
          <button className="primary-button compact"><Plus size={18} /> Registrar</button>
        </form>
        <div className="category-list agenda-list">
          {messages.map((item) => (
            <article key={item.id}>
              <span className="entity-icon"><Inbox size={19} /></span>
              <div>
                <strong>{item.assunto || item.remetenteNome || channelLabel(item.canal)}</strong>
                <small>{channelLabel(item.canal)} · {item.status} · {formatDate(item.recebidaEm)}</small>
                <p className="muted-copy">{item.conteudo}</p>
              </div>
              <button className="secondary-button compact" disabled={item.status !== "RECEBIDA"} onClick={() => convertMessage(item)}>Converter em solicitação</button>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function ConversationComposer({ conversation, busy, onSend }) {
  const [text, setText] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [parameters, setParameters] = useState([]);
  const templates = conversation.templatesSaida || [];
  const selected = templates.find((item) => item.id === templateId);
  const optedOut = conversation.contato?.optStatus === "OPTED_OUT";
  const requiresTemplate = !conversation.janelaAberta;

  async function submit(event) {
    event.preventDefault();
    await onSend(selected ? { templateId: selected.id, parametros: parameters } : { texto: text });
    setText("");
    setTemplateId("");
    setParameters([]);
  }

  return <form className="inbox-v2-composer" onSubmit={submit}>
    <div className="inbox-v2-composer-policy"><ShieldCheck size={15} /><span>{optedOut ? "Contato com opt-out: novas saídas estão bloqueadas." : requiresTemplate ? "Janela encerrada: somente template transacional aprovado." : "Janela aberta: mensagem livre ou template aprovado."}</span></div>
    {!optedOut && <>
      <label>Modelo de envio<select aria-label="Template de saída WhatsApp" value={templateId} onChange={(event) => { const id = event.target.value; const item = templates.find((template) => template.id === id); setTemplateId(id); setParameters((item?.variaveis || []).map(() => "")); }}><option value="">{requiresTemplate ? "Selecione um template aprovado" : "Mensagem livre"}</option>{templates.map((item) => <option value={item.id} key={item.id}>{item.nome} · {item.idioma}</option>)}</select></label>
      {selected ? <div className="inbox-v2-template-compose"><p>{selected.conteudo}</p>{selected.variaveis.map((variable, index) => <label key={`${selected.id}-${variable}-${index}`}>{variable}<input required value={parameters[index] || ""} onChange={(event) => setParameters((current) => current.map((value, position) => position === index ? event.target.value : value))} /></label>)}</div> : <textarea aria-label="Mensagem WhatsApp" rows="3" required={!requiresTemplate} disabled={requiresTemplate} value={text} maxLength={4096} onChange={(event) => setText(event.target.value)} placeholder={requiresTemplate ? "Selecione um template acima" : "Escreva uma resposta para o cidadão"} />}
      <button className="primary-button compact" disabled={busy || (requiresTemplate && !selected)}><Send size={16} /> Enviar pelo WhatsApp</button>
    </>}
  </form>;
}

function ConversationMediaPanel({ assets, busy, onReview, onRetry }) {
  const [edits, setEdits] = useState({});
  const icon = (type) => type === "audio" ? <FileAudio size={18} /> : type === "image" ? <Image size={18} /> : <FileText size={18} />;
  return <section className="conversation-media-panel" aria-label="Mídias recebidas">
    <header><div><Sparkles size={18} /><span><strong>Mídia e IA assistiva</strong><small>Arquivos privados, verificados e sujeitos à revisão humana.</small></span></div><b>{assets.length}</b></header>
    <div className="conversation-media-list">{assets.map((asset) => {
      const analysis = asset.analise || {};
      const failed = asset.status === "FAILED" || analysis.status === "FAILED";
      return <article key={asset.id} className={failed ? "failed" : ""}>
        <div className="conversation-media-heading"><span className="conversation-media-icon">{icon(asset.tipo)}</span><div><strong>{asset.nome || `${asset.tipo} do WhatsApp`}</strong><small>{asset.mimeType || asset.tipo} · {mediaStatusLabel(asset)}</small></div>{asset.downloadUrl && <a className="icon-button" href={asset.downloadUrl} title="Baixar mídia" aria-label={`Baixar ${asset.nome || asset.tipo}`}><Download size={16} /></a>}</div>
        {analysis.status === "COMPLETED" && <>
          <div className="conversation-media-confidence"><span>Confiança da {analysis.tipo === "TRANSCRIPTION" ? "transcrição" : "extração"}</span><strong>{analysis.confianca == null ? "Não informada" : `${Math.round(analysis.confianca * 100)}%`}</strong></div>
          <textarea aria-label={`Texto assistivo de ${asset.nome || asset.tipo}`} rows="3" value={edits[asset.id] ?? analysis.textoRevisado ?? analysis.textoGerado ?? ""} disabled={analysis.statusRevisao !== "PENDING"} onChange={(event) => setEdits((current) => ({ ...current, [asset.id]: event.target.value }))} />
          {analysis.statusRevisao === "PENDING" && <div className="conversation-media-actions"><button className="primary-button compact" type="button" disabled={busy} onClick={() => onReview(asset.id, edits[asset.id] == null ? "ACCEPT" : "EDIT", edits[asset.id])}><CheckCircle2 size={15} /> {edits[asset.id] == null ? "Aceitar" : "Aplicar correção"}</button><button className="secondary-button compact" type="button" disabled={busy} onClick={() => onReview(asset.id, "REJECT")}><X size={15} /> Rejeitar</button></div>}
          {analysis.statusRevisao !== "PENDING" && <small className="conversation-media-reviewed"><ShieldCheck size={14} /> Revisão: {mediaReviewLabel(analysis.statusRevisao)}</small>}
        </>}
        {failed && <div className="conversation-media-error"><AlertTriangle size={16} /><span>{asset.erro || analysis.erro || "Não foi possível processar esta mídia."}</span><button className="secondary-button compact" type="button" disabled={busy} onClick={() => onRetry(asset.id)}><RotateCw size={14} /> Tentar novamente</button></div>}
      </article>;
    })}</div>
  </section>;
}

function mediaStatusLabel(asset) {
  if (asset.status === "BLOCKED") return "bloqueada pela verificação";
  if (asset.status !== "READY") return { RECEIVED: "recebida", DOWNLOADING: "baixando com segurança", FAILED: "falha no download" }[asset.status] || asset.status;
  return { PENDING: "análise pendente", PROCESSING: "análise em andamento", COMPLETED: "análise concluída", FAILED: "falha na análise", NOT_APPLICABLE: "arquivo verificado" }[asset.analise?.status] || "arquivo verificado";
}

function mediaReviewLabel(status) {
  return { ACCEPTED: "aceita", EDITED: "corrigida", REJECTED: "rejeitada", NOT_REQUIRED: "não necessária" }[status] || status;
}

function ConversationServiceFlow({
  conversation,
  citizenName,
  setCitizenName,
  requestDraft,
  setRequestDraft,
  requestConfirmed,
  setRequestConfirmed,
  protocolAccess,
  launchNotice,
  busy,
  onAcknowledgePrivacy,
  onIdentifyCitizen,
  onSaveDraft,
  onConfirmRequest,
  onLaunchFlow,
}) {
  const flow = conversation.jornada;
  const privacyReady = flow.privacidade?.reconhecida;
  const citizenReady = Boolean(flow.cidadao);
  const draftReady = flow.rascunhoSolicitacao?.status === "READY";
  const protocolReady = Boolean(flow.solicitacao);
  const metaFlow = conversation.whatsappFlow || {};
  const activeSession = metaFlow.sessao?.status === "PENDING" ? metaFlow.sessao : null;
  const steps = [
    ["Privacidade", privacyReady],
    ["Cidadão", citizenReady],
    ["Solicitação", draftReady || protocolReady],
    ["Protocolo", protocolReady],
  ];

  return <section className="conversation-service-flow" aria-label="Jornada de atendimento">
    <ol className="conversation-flow-steps">
      {steps.map(([label, complete], index) => <li className={complete ? "complete" : ""} key={label}>
        <span>{complete ? <CheckCircle2 size={15} /> : index + 1}</span>
        <small>{label}</small>
      </li>)}
    </ol>

    {launchNotice && <p className="conversation-flow-notice" role="status">{launchNotice}</p>}
    {activeSession && <div className="conversation-flow-session"><MessageCircle size={17} /><span><strong>{activeSession.nome}</strong> com envio solicitado</span><small>expira em {formatDate(activeSession.expiraEm)}</small></div>}

    {!privacyReady && <article className="conversation-flow-card privacy">
      <div className="conversation-flow-card-title">
        <ShieldCheck size={19} />
        <div><strong>Transparência antes da coleta</strong><small>A ordem de envio do aviso já foi registrada. Confirme a apresentação ao cidadão.</small></div>
      </div>
      <p>O atendimento institucional é processado pelo GabFlow, pode usar automação com revisão humana e permite saída pelo comando PARAR.</p>
      <button className="primary-button compact" type="button" disabled={busy} onClick={onAcknowledgePrivacy}>Registrar aviso apresentado</button>
    </article>}

    {privacyReady && !citizenReady && <article className="conversation-flow-card">
      <div className="conversation-flow-card-title">
        <UserPlus size={19} />
        <div><strong>Identificação assistida</strong><small>CPF não é necessário. Todo vínculo ou cadastro exige confirmação humana.</small></div>
      </div>
      <button className="conversation-meta-flow-button" type="button" disabled={busy || Boolean(activeSession)} onClick={() => onLaunchFlow("citizen_registration")}><MessageCircle size={16} /> Coletar cadastro pelo WhatsApp Flow</button>
      {flow.sugestoesCidadao?.length > 0 && <div className="conversation-citizen-suggestions">
        <span>Cadastros com o mesmo WhatsApp</span>
        {flow.sugestoesCidadao.map((item) => <button className="secondary-button compact" type="button" disabled={busy} key={item.id} onClick={() => onIdentifyCitizen(item.id)}><Link2 size={15} /> Vincular {item.nome}</button>)}
      </div>}
      <label>Nome confirmado do cidadão<input value={citizenName} maxLength="180" onChange={(event) => setCitizenName(event.target.value)} placeholder="Nome informado e confirmado" /></label>
      <button className="primary-button compact" type="button" disabled={busy || citizenName.trim().length < 2} onClick={() => onIdentifyCitizen(null)}><UserPlus size={15} /> Cadastrar cidadão confirmado</button>
    </article>}

    {citizenReady && !protocolReady && <form className="conversation-flow-card request" onSubmit={onSaveDraft}>
      <div className="conversation-flow-card-title">
        <MessageSquare size={19} />
        <div><strong>Solicitação de {flow.cidadao.nome}</strong><small>Revise os dados estruturados antes de gerar o protocolo.</small></div>
      </div>
      <button className="conversation-meta-flow-button" type="button" disabled={busy || Boolean(activeSession)} onClick={() => onLaunchFlow(draftReady ? "request_complement" : "new_service_request")}><MessageCircle size={16} /> {draftReady ? "Solicitar complemento pelo Flow" : "Coletar solicitaÃ§Ã£o pelo WhatsApp Flow"}</button>
      <label>Título<input maxLength="180" value={requestDraft.titulo} onChange={(event) => setRequestDraft((current) => ({ ...current, titulo: event.target.value }))} placeholder="Resumo objetivo" /></label>
      <label>Descrição<textarea rows="3" required minLength="3" value={requestDraft.descricao} onChange={(event) => setRequestDraft((current) => ({ ...current, descricao: event.target.value }))} placeholder="O que aconteceu e qual apoio é necessário?" /></label>
      <div className="conversation-flow-fields">
        <label>Endereço<input maxLength="500" value={requestDraft.endereco} onChange={(event) => setRequestDraft((current) => ({ ...current, endereco: event.target.value }))} placeholder="Opcional" /></label>
        <label>Categoria<select value={requestDraft.categoriaId} onChange={(event) => setRequestDraft((current) => ({ ...current, categoriaId: event.target.value }))}><option value="">Triagem posterior</option>{conversation.categorias?.map((item) => <option value={item.id} key={item.id}>{item.nome}</option>)}</select></label>
      </div>
      <div className="conversation-flow-actions">
        <button className="secondary-button compact" disabled={busy} type="submit">Salvar para revisão</button>
        {draftReady && <label className="conversation-confirmation"><input type="checkbox" checked={requestConfirmed} onChange={(event) => setRequestConfirmed(event.target.checked)} /> Confirmo que o cidadão revisou os dados</label>}
        {draftReady && <button className="primary-button compact" type="button" disabled={busy || !requestConfirmed} onClick={onConfirmRequest}><CheckCircle2 size={15} /> Gerar protocolo</button>}
      </div>
    </form>}

    {protocolReady && <article className="conversation-flow-card protocol">
      <div className="conversation-flow-card-title"><CheckCircle2 size={21} /><div><strong>Solicitação protocolada</strong><small>Referência pública não sequencial, segura contra enumeração.</small></div></div>
      <code>{flow.solicitacao.protocoloPublico}</code>
      {protocolAccess?.chaveAcompanhamento && <div className="conversation-protocol-key"><span>Chave exibida uma única vez</span><code>{protocolAccess.chaveAcompanhamento}</code></div>}
    </article>}
  </section>;
}

function channelLabel(value) {
  return { WHATSAPP: "WhatsApp", EMAIL: "E-mail", REDE_SOCIAL: "Rede social", FORMULARIO: "Formulário" }[value] || value;
}

function resolutionLabel(value) {
  return {
    SEM_CORRESPONDENCIA: "Nenhuma correspondência encontrada",
    CORRESPONDENCIA_UNICA: "Uma correspondência sugerida",
    CORRESPONDENCIA_AMBIGUA: "Múltiplas correspondências — escolha obrigatória",
  }[value] || value;
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function initials(value) {
  return String(value || "W").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function stateLabel(value) {
  return {
    NEW: "Nova conversa",
    PRIVACY_NOTICE: "Aviso de privacidade",
    IDENTIFICATION: "Identificação",
    INTENT: "Entendimento da demanda",
    DATA_COLLECTION: "Coleta de dados",
    REVIEW: "Em revisão",
    PROTOCOL_CREATED: "Protocolo criado",
    FOLLOW_UP: "Acompanhamento",
    HUMAN_HANDOFF: "Atendimento humano",
    OPTED_OUT: "Descadastrado",
    BLOCKED: "Bloqueada",
    ERROR_RECOVERY: "Recuperação",
    CLOSED: "Encerrada",
  }[value] || value;
}
