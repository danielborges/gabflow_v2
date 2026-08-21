import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";

const RAG_QUERY_TIMEOUT_MS = 150000;

export function useRagAssistantQuery() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState("");
  const requestRef = useRef(null);

  useEffect(() => () => {
    requestRef.current?.abort("unmount");
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const startedAt = Date.now();
    setElapsedSeconds(0);
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [busy]);

  async function submitQuestion(value) {
    const normalized = value.trim();
    if (normalized.length < 3 || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort("timeout"), RAG_QUERY_TIMEOUT_MS);
    setBusy(true);
    setError("");
    setPendingQuestion(normalized);
    setQuestion("");
    try {
      const result = await apiRequest("/api/v1/assistente/consultas", {
        method: "POST",
        body: JSON.stringify({
          consulta: normalized,
          limite: 5,
          ...(conversationId ? { conversaId: conversationId } : {}),
        }),
        signal: controller.signal,
      });
      setConversationId(result.conversaId || conversationId);
      setTurns((current) => [...current, {
        id: result.id || `turn-${current.length + 1}`,
        question: normalized,
        answer: result,
      }]);
    } catch (requestError) {
      if (controller.signal.reason === "unmount") return;
      let message;
      if (controller.signal.aborted) {
        message = controller.signal.reason === "timeout"
          ? `A consulta excedeu ${Math.round(RAG_QUERY_TIMEOUT_MS / 1000)} segundos e foi interrompida. Tente novamente.`
          : "Consulta cancelada.";
      } else {
        message = requestError.message;
      }
      setError(message);
      setQuestion(normalized);
      setTurns((current) => [...current, {
        id: `failed-${Date.now()}`,
        question: normalized,
        error: message,
      }]);
    } finally {
      window.clearTimeout(timeout);
      if (requestRef.current === controller) {
        requestRef.current = null;
        if (controller.signal.reason !== "unmount") {
          setBusy(false);
          setPendingQuestion("");
        }
      }
    }
  }

  function cancelQuery() {
    requestRef.current?.abort("user");
  }

  function updateAnswer(updatedAnswer) {
    setTurns((current) => current.map((turn) => (
      turn.answer?.id === updatedAnswer.id ? { ...turn, answer: updatedAnswer } : turn
    )));
  }

  function startNewConversation() {
    if (requestRef.current) return;
    setTurns([]);
    setConversationId(null);
    setPendingQuestion("");
    setQuestion("");
    setError("");
  }

  const answer = [...turns].reverse().find((turn) => turn.answer)?.answer || null;

  return {
    question,
    setQuestion,
    turns,
    conversationId,
    pendingQuestion,
    answer,
    setAnswer: updateAnswer,
    busy,
    elapsedSeconds,
    error,
    submitQuestion,
    cancelQuery,
    startNewConversation,
  };
}
