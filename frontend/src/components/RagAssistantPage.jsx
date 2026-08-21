import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileText,
  MessageSquareWarning,
  Plus,
  PencilLine,
  Send,
  ShieldAlert,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";
import { FeatureHeader } from "./FeatureHeader";
import { useRagAssistantQuery } from "./useRagAssistantQuery";

export function RagAssistantPage() {
  const {
    question,
    setQuestion,
    setAnswer,
    turns,
    pendingQuestion,
    busy,
    elapsedSeconds,
    error,
    submitQuestion,
    cancelQuery,
    startNewConversation,
  } = useRagAssistantQuery();

  async function submit(event) {
    event.preventDefault();
    await submitQuestion(question);
  }

  return (
    <>
      <FeatureHeader className="rag-assistant-heading" eyebrow="Assistente RAG" title="Consulta institucional" description="Faça perguntas sobre a base documental vigente e revise as fontes antes de usar." />

      <section className="rag-assistant-workspace">
        <header className="rag-conversation-toolbar">
          <div>
            <strong>Conversa atual</strong>
            <small>{turns.length ? `${turns.length} ${turns.length === 1 ? "pergunta realizada" : "perguntas realizadas"}` : "Faça sua primeira pergunta"}</small>
          </div>
          <button type="button" className="secondary-button" disabled={busy || !turns.length} onClick={startNewConversation}>
            <Plus size={16} /> Nova conversa
          </button>
        </header>

        <div className="rag-conversation-feed" aria-live="polite">
          <RagConversationFeed
            turns={turns}
            pendingQuestion={pendingQuestion}
            busy={busy}
            elapsedSeconds={elapsedSeconds}
            onUpdate={setAnswer}
          />
        </div>

        <RagConversationComposer
          question={question}
          setQuestion={setQuestion}
          busy={busy}
          error={error}
          onSubmit={submit}
          onCancel={cancelQuery}
        />
      </section>
    </>
  );
}

export function RagConversationFeed({ turns, pendingQuestion, busy, elapsedSeconds, onUpdate, compact = false, empty }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [turns.length, busy]);
  if (!turns.length && !busy) return empty || <EmptyState />;
  return (
    <div className={`rag-conversation-turns${compact ? " compact" : ""}`}>
      {turns.map((turn) => (
        <div className="rag-conversation-turn" key={turn.id}>
          <div className="rag-user-message"><span>Você</span><p>{turn.question}</p></div>
          <div className="rag-assistant-message">
            <span>GabFlow</span>
            {turn.answer
              ? <RagAnswerResult answer={turn.answer} onUpdate={onUpdate} compact={compact} />
              : <p className="rag-turn-error" role="alert">{turn.error}</p>}
          </div>
        </div>
      ))}
      {busy && (
        <div className="rag-conversation-turn pending">
          <div className="rag-user-message"><span>Você</span><p>{pendingQuestion}</p></div>
          <div className="rag-assistant-message"><span>GabFlow</span><RagLoadingState elapsedSeconds={elapsedSeconds} /></div>
        </div>
      )}
      <div ref={endRef} aria-hidden="true" />
    </div>
  );
}

export function RagConversationComposer({ question, setQuestion, busy, error, onSubmit, onCancel, id = "rag-question", compact = false }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent?.isComposing) {
      event.preventDefault();
      if (!busy && question.trim().length >= 3) event.currentTarget.form?.requestSubmit();
    }
  }
  return (
    <form className={`rag-chat-composer${compact ? " compact" : ""}`} onSubmit={onSubmit}>
      <label htmlFor={id}>Pergunta</label>
      <div className="rag-question-input">
        <BookOpen size={19} />
        <textarea
          id={id}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Pergunte algo e continue a conversa com novas perguntas..."
          maxLength={2000}
          rows={compact ? 2 : 3}
        />
        <button
          type={busy ? "button" : "submit"}
          className={busy ? "secondary-button" : "primary-button"}
          disabled={!busy && question.trim().length < 3}
          onClick={busy ? onCancel : undefined}
        >
          <Send size={17} /> {busy ? "Cancelar consulta" : "Consultar"}
        </button>
      </div>
      <div className="rag-composer-meta">
        <small>{question.length}/2000 · Enter para enviar, Shift + Enter para nova linha</small>
        {error && <small className="rag-composer-error">A última pergunta não foi concluída. Você pode tentar novamente.</small>}
      </div>
    </form>
  );
}

export function RagLoadingState({ elapsedSeconds = 0 }) {
  const phase = elapsedSeconds < 5
    ? "Entendendo a pergunta"
    : elapsedSeconds < 15
      ? "Consultando os dados e as fontes aplicáveis"
      : "Preparando uma resposta fundamentada";
  return (
    <div className="rag-assistant-empty rag-assistant-loading" role="status">
      <div className="rag-loading-symbol" aria-hidden="true">
        <span /><Sparkles size={30} />
      </div>
      <h2>Consultando a inteligência do gabinete</h2>
      <p>{phase}.</p>
      <div className="rag-loading-progress" role="progressbar" aria-label="Consulta em andamento" aria-valuetext={`${elapsedSeconds} segundos decorridos`}><span /></div>
      <small>{elapsedSeconds} {elapsedSeconds === 1 ? "segundo decorrido" : "segundos decorridos"} · você pode cancelar a qualquer momento</small>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rag-assistant-empty">
      <Sparkles size={34} />
      <h2>Pronto para consultar a base</h2>
      <p>As respostas aparecem com decisão de evidência, citações e alertas de segurança.</p>
    </div>
  );
}

export function RagAnswerResult({ answer, onUpdate, compact = false }) {
  const safety = answer.seguranca || {};
  const refused = Boolean(answer.recusaConclusiva);
  const structured = answer.metodo === "ESTRUTURADO" || answer.modeloEmbedding === "NAO_APLICAVEL";
  const riskySources = (answer.fontes || []).filter((source) => source.riscoPromptInjection);
  return (
    <article className={`rag-answer-result ${refused ? "refused" : "grounded"}${compact ? " compact" : ""}`}>
      <header>
        <div>
          {refused ? <AlertTriangle size={21} /> : <CheckCircle2 size={21} />}
          <span>
            <strong>{refused ? "Evidência insuficiente" : "Resposta fundamentada"}</strong>
            <small>
              {structured
                ? "Resposta gerada com dados estruturados do GabFlow."
                : `${answer.modeloEmbedding} · limiar ${formatScore(answer.limiarEvidencia)}`}
            </small>
          </span>
        </div>
        <span className={`rag-answer-state ${refused ? "state-refused" : "state-grounded"}`}>
          {refused ? "Recusada" : "Fundamentada"}
        </span>
      </header>
      <p className="rag-answer-text">{answer.resposta}</p>

      {!compact && <RagFeedbackPanel answer={answer} onUpdate={onUpdate} />}

      {safety.promptInjectionDetectado && (
        <section className="rag-safety-warning" role="alert" aria-labelledby="rag-safety-title">
          <ShieldAlert size={18} />
          <div>
            <strong id="rag-safety-title">Alerta de segurança: possível prompt injection detectado</strong>
            <p>{safety.politica}</p>
            {riskySources.length > 0 && (
              <ul>
                {riskySources.map((source, index) => (
                  <li key={`${source.documentoId}-${source.versaoId}-${index}`}>
                    {securitySourceLabel(source)}
                  </li>
                ))}
              </ul>
            )}
            <small>As instruções suspeitas foram ignoradas e os trechos citados foram sanitizados. Revise as fontes antes de usar a resposta.</small>
          </div>
        </section>
      )}

      {(!structured || answer.fontes?.length > 0) && <section className="rag-source-list">
        <h2>Fontes citadas</h2>
        {answer.fontes?.length ? answer.fontes.map((source, index) => (
          <article key={`${source.documentoId}-${source.versaoId}-${source.paginaInicio || 0}-${index}`}>
            <header>
              <FileText size={17} />
              <span>
                <small className={`rag-source-scope scope-${(source.escopo || "PRIVADO").toLowerCase()}`}>
                  {source.rotuloFonte || (source.escopo === "GLOBAL" ? "Fonte GabFlow" : "Fonte do Gabinete")}
                </small>
                <strong>{source.titulo}</strong>
                <small>
                  {source.colecao ? `${source.colecao} · ` : ""}
                  {source.tipo || "Documento"}{source.orgao ? ` · ${source.orgao}` : ""}
                </small>
              </span>
            </header>
            <dl className="rag-source-meta">
              <div><dt>Documento</dt><dd>{source.titulo}</dd></div>
              <div><dt>Versão</dt><dd>{source.versao || "Não informada"}</dd></div>
              <div><dt>Página</dt><dd>{pageLabel(source)}</dd></div>
              <div><dt>Score</dt><dd>{formatScore(source.pontuacao)}</dd></div>
            </dl>
            <div className="rag-source-excerpt">
              <strong>Trecho</strong>
              <p>{source.trecho}</p>
            </div>
            {source.riscoPromptInjection && (
              <small className="rag-source-risk">Trecho sanitizado por risco de prompt injection.</small>
            )}
          </article>
        )) : <p className="table-message">Nenhuma fonte acima do limiar configurado.</p>}
      </section>}
    </article>
  );
}

function RagFeedbackPanel({ answer, onUpdate }) {
  const [mode, setMode] = useState("");
  const [correctedResponse, setCorrectedResponse] = useState(answer.respostaCorrigida || answer.resposta || "");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function sendFeedback(rating) {
    setBusy(true);
    setError("");
    try {
      const payload = { avaliacao: rating };
      if (comment.trim()) payload.comentario = comment.trim();
      if (rating === "CORRIGIDA") payload.respostaCorrigida = correctedResponse.trim();
      const updated = await apiRequest(`/api/v1/assistente/consultas/${answer.id}/avaliacao`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      onUpdate(updated);
      setMode("");
      setComment("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function chooseCorrected() {
    setMode("CORRIGIDA");
    setCorrectedResponse(answer.respostaCorrigida || answer.resposta || "");
    setError("");
  }

  return (
    <section className="rag-feedback-panel" aria-label="Avaliar resposta do assistente">
      <header>
        <div>
          <strong>Avaliação da resposta</strong>
          <small>{feedbackLabel(answer.avaliacao)}</small>
        </div>
        <div className="rag-feedback-buttons">
          <button type="button" className={answer.avaliacao === "POSITIVA" ? "active" : ""} disabled={busy} onClick={() => sendFeedback("POSITIVA")}>
            <ThumbsUp size={16} /> Positiva
          </button>
          <button type="button" className={answer.avaliacao === "NEGATIVA" ? "active danger" : "danger"} disabled={busy} onClick={() => sendFeedback("NEGATIVA")}>
            <ThumbsDown size={16} /> Negativa
          </button>
          <button type="button" className={answer.avaliacao === "CORRIGIDA" || mode === "CORRIGIDA" ? "active corrected" : "corrected"} disabled={busy} onClick={chooseCorrected}>
            <PencilLine size={16} /> Corrigida
          </button>
        </div>
      </header>

      <label className="rag-feedback-comment">
        Comentário opcional
        <input
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          maxLength={2000}
          placeholder="Ex.: fonte adequada, resposta incompleta ou ajuste necessário"
        />
      </label>

      {mode === "CORRIGIDA" && (
        <div className="rag-feedback-correction">
          <label>
            Resposta corrigida
            <textarea
              value={correctedResponse}
              onChange={(event) => setCorrectedResponse(event.target.value)}
              maxLength={10000}
              rows={5}
            />
          </label>
          <button className="primary-button" disabled={busy || correctedResponse.trim().length < 3} onClick={() => sendFeedback("CORRIGIDA")}>
            <PencilLine size={16} /> {busy ? "Registrando..." : "Registrar correção"}
          </button>
        </div>
      )}

      {answer.respostaCorrigida && (
        <div className="rag-feedback-corrected">
          <MessageSquareWarning size={16} />
          <p>{answer.respostaCorrigida}</p>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}
    </section>
  );
}

function formatScore(value) {
  return Number(value || 0).toLocaleString("pt-BR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

function pageLabel(source) {
  if (!source.paginaInicio) return "Não informada";
  if (source.paginaFim && source.paginaFim !== source.paginaInicio) {
    return `${source.paginaInicio}-${source.paginaFim}`;
  }
  return String(source.paginaInicio);
}

function securitySourceLabel(source) {
  const details = [
    source.versao ? `versão ${source.versao}` : null,
    source.paginaInicio ? `página ${pageLabel(source)}` : null,
  ].filter(Boolean);
  return details.length ? `${source.titulo} (${details.join(", ")})` : source.titulo;
}

function feedbackLabel(value) {
  if (value === "POSITIVA") return "Marcada como positiva.";
  if (value === "NEGATIVA") return "Marcada como negativa.";
  if (value === "CORRIGIDA") return "Resposta corrigida registrada.";
  return "Informe se a resposta foi útil, insuficiente ou precisa ser corrigida.";
}
