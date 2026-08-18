import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";

const RAG_QUERY_TIMEOUT_MS = 150000;

export function useRagAssistantQuery() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(null);

  useEffect(() => () => {
    requestRef.current?.abort("unmount");
  }, []);

  async function submitQuestion(value) {
    const normalized = value.trim();
    if (normalized.length < 3 || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort("timeout"), RAG_QUERY_TIMEOUT_MS);
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      const result = await apiRequest("/api/v1/assistente/consultas", {
        method: "POST",
        body: JSON.stringify({ consulta: normalized, limite: 5 }),
        signal: controller.signal,
      });
      setAnswer(result);
    } catch (requestError) {
      if (controller.signal.reason === "unmount") return;
      if (controller.signal.aborted) {
        setError(controller.signal.reason === "timeout"
          ? "A consulta excedeu 60 segundos e foi interrompida. Tente novamente."
          : "Consulta cancelada.");
      } else {
        setError(requestError.message);
      }
    } finally {
      window.clearTimeout(timeout);
      if (requestRef.current === controller) {
        requestRef.current = null;
        if (controller.signal.reason !== "unmount") setBusy(false);
      }
    }
  }

  function cancelQuery() {
    requestRef.current?.abort("user");
  }

  return {
    question,
    setQuestion,
    answer,
    setAnswer,
    busy,
    error,
    submitQuestion,
    cancelQuery,
  };
}
