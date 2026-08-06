import { CheckCircle2, Clock3, Inbox, Link2, MessageSquare, Plus, RotateCw, Settings2, ShieldCheck, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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
  const [messages, setMessages] = useState([]);
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
      const [messageData, reviewData, settingsData] = await Promise.all([
        apiRequest("/api/v1/canais/mensagens"),
        apiRequest(`/api/v1/canais/revisoes-identidade?status=${reviewStatus}${assigneeFilter ? `&responsavelId=${assigneeFilter}` : ""}`),
        apiRequest("/api/v1/canais/configuracao-cadastro-assistido"),
      ]);
      setMessages(messageData.content);
      setReviews(reviewData.content);
      setSummary(reviewData.resumo || {});
      setResponsibles(reviewData.responsaveis || []);
      setSettings(settingsData);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [reviewStatus, assigneeFilter]);

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
