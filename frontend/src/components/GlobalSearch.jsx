import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";

export function GlobalSearch({ onOpen }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setError("");
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ q: trimmed });
        const data = await apiRequest(`/api/v1/busca?${params}`, { signal: controller.signal });
        setResults(data.content || []);
        setOpen(true);
      } catch (requestError) {
        if (requestError.name !== "AbortError") setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  useEffect(() => {
    function close(event) {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function choose(item) {
    onOpen(item);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="global-search" ref={containerRef}>
      <label className="search-box">
        <Search size={18} aria-hidden="true" />
        <input
          aria-label="Pesquisar"
          placeholder="Pesquisar no GabFlow"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
        />
      </label>
      {open && query.trim().length >= 2 && (
        <div className="global-search-results">
          {loading ? (
            <p>Pesquisando...</p>
          ) : error ? (
            <p className="search-select-error">{error}</p>
          ) : results.length ? (
            results.map((item) => (
              <button type="button" key={`${item.tipo}-${item.id}`} onClick={() => choose(item)}>
                <span>{item.categoria}</span>
                <strong>{item.titulo}</strong>
                <small>{[item.meta, item.subtitulo].filter(Boolean).join(" · ")}</small>
              </button>
            ))
          ) : (
            <p>Nenhum resultado encontrado.</p>
          )}
        </div>
      )}
    </div>
  );
}
