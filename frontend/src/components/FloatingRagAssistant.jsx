import { ArrowUpRight, BookOpen, Send, Sparkles, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { RagAnswerResult, RagLoadingState } from "./RagAssistantPage";
import { useRagAssistantQuery } from "./useRagAssistantQuery";

const VIEW_CONTEXTS = {
  overview: {
    label: "Visão geral",
    suggestions: [
      "Quantas solicitações existem por status?",
      "Quais temas recorrentes aparecem nos relatos?",
    ],
  },
  requests: {
    label: "Solicitações",
    suggestions: [
      "Quantas solicitações estão em atendimento?",
      "Quantas solicitações estão aguardando o órgão?",
    ],
  },
  citizens: {
    label: "Cidadãos",
    suggestions: [
      "Quais temas aparecem com mais frequência nas solicitações?",
      "Quais documentos orientam o atendimento ao cidadão?",
    ],
  },
  documents: {
    label: "Documentos",
    suggestions: [
      "Quais documentos fundamentam a atuação do gabinete?",
      "Quais normas da base tratam de atendimento ao cidadão?",
    ],
  },
  agenda: {
    label: "Agenda",
    suggestions: [
      "Quantos compromissos foram realizados?",
      "Quais informações da base podem apoiar uma reunião institucional?",
    ],
  },
  oversight: {
    label: "Fiscalização",
    suggestions: [
      "Quantas fiscalizações estão em andamento?",
      "Quais documentos podem fundamentar uma ação de fiscalização?",
    ],
  },
  channels: {
    label: "Canais",
    suggestions: [
      "Quais orientações da base apoiam uma resposta ao cidadão?",
      "Quais temas recorrentes aparecem nos relatos?",
    ],
  },
  rag: {
    label: "Base RAG",
    suggestions: [
      "Quais documentos estão disponíveis para fundamentar respostas?",
      "Quais normas da base tratam de atendimento ao cidadão?",
    ],
  },
  "rag-assistant": {
    label: "Assistente RAG",
    suggestions: [
      "Quantas solicitações existem por status?",
      "Quais documentos orientam o trabalho do gabinete?",
    ],
  },
  "ai-quality": {
    label: "Qualidade da IA",
    suggestions: [
      "Quais fontes são usadas nas respostas atuais?",
      "Quais documentos da base tratam de atendimento ao cidadão?",
    ],
  },
  electoral: {
    label: "Inteligência Eleitoral",
    suggestions: [
      "Quais informações institucionais da base apoiam o planejamento do mandato?",
      "Quais temas recorrentes aparecem nos relatos?",
    ],
  },
};

const DEFAULT_CONTEXT = {
  label: "GabFlow",
  suggestions: [
    "Quantas solicitações existem por status?",
    "Quais documentos orientam o trabalho do gabinete?",
  ],
};

export function FloatingRagAssistant({ activeView, onOpenFullPage }) {
  const [open, setOpen] = useState(false);
  const {
    question,
    setQuestion,
    answer,
    setAnswer,
    busy,
    error,
    submitQuestion,
    cancelQuery,
  } = useRagAssistantQuery();
  const questionId = useId();
  const context = VIEW_CONTEXTS[activeView] || DEFAULT_CONTEXT;

  useEffect(() => {
    if (!open) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    await submitQuestion(question);
  }

  function openFullPage() {
    setOpen(false);
    onOpenFullPage();
  }

  return (
    <div className="floating-rag-assistant">
      <button
        type="button"
        className={`icon-button floating-rag-trigger${open ? " active" : ""}`}
        aria-label="Abrir Assistente RAG"
        aria-expanded={open}
        title="Assistente RAG"
        onClick={() => setOpen((current) => !current)}
      >
        <Sparkles size={20} />
      </button>

      <section
        className="floating-rag-panel"
        role="dialog"
        aria-label="Assistente RAG flutuante"
        hidden={!open}
      >
        <header>
          <div className="floating-rag-title">
            <span><Sparkles size={19} /></span>
            <div>
              <strong>Assistente RAG</strong>
              <small>Apoiando seu trabalho em {context.label}</small>
            </div>
          </div>
          <div className="floating-rag-header-actions">
            <button type="button" className="icon-button" onClick={openFullPage} aria-label="Abrir Assistente RAG em tela completa" title="Abrir em tela completa">
              <ArrowUpRight size={18} />
            </button>
            <button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Fechar Assistente RAG" title="Fechar">
              <X size={19} />
            </button>
          </div>
        </header>

        <div className="floating-rag-body">
          <form className="floating-rag-form" onSubmit={submit}>
            <label htmlFor={questionId}>Pergunta ao Assistente RAG</label>
            <div className="rag-question-input">
              <BookOpen size={18} />
              <textarea
                id={questionId}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Pergunte sobre documentos, normas, solicitações ou indicadores..."
                maxLength={2000}
              />
            </div>
            <div className="floating-rag-suggestions" aria-label="Perguntas sugeridas">
              {context.suggestions.map((suggestion) => (
                <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
            {error && <p className="form-error">{error}</p>}
            <div className="rag-question-actions">
              <small>{question.length}/2000</small>
              <button
                type={busy ? "button" : "submit"}
                className={busy ? "secondary-button" : "primary-button"}
                disabled={!busy && question.trim().length < 3}
                onClick={busy ? cancelQuery : undefined}
              >
                <Send size={16} /> {busy ? "Cancelar consulta" : "Consultar"}
              </button>
            </div>
          </form>

          <div className="floating-rag-answer" aria-live="polite">
            {answer ? (
              <RagAnswerResult answer={answer} onUpdate={setAnswer} compact />
            ) : busy ? (
              <RagLoadingState />
            ) : (
              <div className="floating-rag-empty">
                <Sparkles size={26} />
                <strong>Inteligência do gabinete sem sair desta tela</strong>
                <p>Faça uma pergunta ou use uma sugestão relacionada ao seu contexto de trabalho.</p>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
