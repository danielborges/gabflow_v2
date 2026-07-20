import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileText,
  MessageSquareWarning,
  PencilLine,
  Send,
  ShieldAlert,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useState } from "react";
import { apiRequest } from "../api";

export function RagAssistantPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const value = question.trim();
    if (value.length < 3) return;
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest("/api/v1/assistente/consultas", {
        method: "POST",
        body: JSON.stringify({ consulta: value, limite: 5 }),
      });
      setAnswer(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="page-heading rag-assistant-heading">
        <div>
          <p className="eyebrow">Assistente RAG</p>
          <h1>Consulta institucional</h1>
          <p>Faça perguntas sobre a base documental vigente e revise as fontes antes de usar.</p>
        </div>
      </section>

      <section className="rag-assistant-workspace">
        <form className="rag-question-panel" onSubmit={submit}>
          <label htmlFor="rag-question">Pergunta</label>
          <div className="rag-question-input">
            <BookOpen size={19} />
            <textarea
              id="rag-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ex.: Qual norma fundamenta a manutenção de iluminação pública?"
              maxLength={2000}
            />
          </div>
          {error && <p className="form-error">{error}</p>}
          <div className="rag-question-actions">
            <small>{question.length}/2000</small>
            <button className="primary-button" disabled={busy || question.trim().length < 3}>
              <Send size={17} /> {busy ? "Consultando..." : "Consultar"}
            </button>
          </div>
        </form>

        <div className="rag-answer-panel">
          {answer ? <RagAnswerResult answer={answer} onUpdate={setAnswer} /> : <EmptyState />}
        </div>
      </section>
    </>
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

function RagAnswerResult({ answer, onUpdate }) {
  const safety = answer.seguranca || {};
  const refused = Boolean(answer.recusaConclusiva);
  const riskySources = (answer.fontes || []).filter((source) => source.riscoPromptInjection);
  return (
    <article className={`rag-answer-result ${refused ? "refused" : "grounded"}`}>
      <header>
        <div>
          {refused ? <AlertTriangle size={21} /> : <CheckCircle2 size={21} />}
          <span>
            <strong>{refused ? "Evidência insuficiente" : "Resposta fundamentada"}</strong>
            <small>{answer.modeloEmbedding} · limiar {formatScore(answer.limiarEvidencia)}</small>
          </span>
        </div>
        <span className={`rag-answer-state ${refused ? "state-refused" : "state-grounded"}`}>
          {refused ? "Recusada" : "Fundamentada"}
        </span>
      </header>
      <p className="rag-answer-text">{answer.resposta}</p>

      <RagFeedbackPanel answer={answer} onUpdate={onUpdate} />

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

      <section className="rag-source-list">
        <h2>Fontes citadas</h2>
        {answer.fontes?.length ? answer.fontes.map((source, index) => (
          <article key={`${source.documentoId}-${source.versaoId}-${source.paginaInicio || 0}-${index}`}>
            <header>
              <FileText size={17} />
              <span>
                <strong>{source.titulo}</strong>
                <small>{source.tipo || "Documento"}{source.orgao ? ` · ${source.orgao}` : ""}</small>
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
      </section>
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
