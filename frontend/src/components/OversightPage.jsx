import { ClipboardCheck, FileText, Plus, SearchCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const emptyForm = {
  titulo: "",
  descricao: "",
  local: "",
  achados: "",
  responsaveis: "",
  providencias: "",
};

export function OversightPage() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const data = await apiRequest("/api/v1/fiscalizacoes");
    setItems(data.content);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/fiscalizacoes", {
        method: "POST",
        body: JSON.stringify({
          titulo: form.titulo,
          descricao: form.descricao,
          local: form.local,
          achados: splitLines(form.achados),
          responsaveis: splitLines(form.responsaveis),
          providencias: splitLines(form.providencias),
        }),
      });
      setForm(emptyForm);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function openReport(item) {
    const data = await apiRequest(`/api/v1/fiscalizacoes/${item.id}/relatorio`);
    setReport(data);
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Fiscalização</p>
          <h1>Ações de fiscalização</h1>
          <p>Registre achados, responsáveis, relatórios e providências decorrentes.</p>
        </div>
      </section>
      <section className="admin-layout agenda-layout">
        <form className="settings-form" onSubmit={submit}>
          <div className="settings-title"><SearchCheck size={21} /><div><strong>Nova fiscalização</strong><small>Planeje ou registre uma vistoria do gabinete.</small></div></div>
          <label>Título<input required value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} /></label>
          <label>Descrição<textarea rows="3" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} /></label>
          <label>Local<input value={form.local} onChange={(event) => setForm((current) => ({ ...current, local: event.target.value }))} /></label>
          <label>Achados<textarea rows="3" value={form.achados} onChange={(event) => setForm((current) => ({ ...current, achados: event.target.value }))} /></label>
          <label>Responsáveis<textarea rows="2" value={form.responsaveis} onChange={(event) => setForm((current) => ({ ...current, responsaveis: event.target.value }))} /></label>
          <label>Providências<textarea rows="3" value={form.providencias} onChange={(event) => setForm((current) => ({ ...current, providencias: event.target.value }))} /></label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button compact"><Plus size={18} /> Adicionar</button>
        </form>
        <div className="category-list agenda-list">
          {items.map((item) => (
            <article key={item.id}>
              <span className="entity-icon"><ClipboardCheck size={19} /></span>
              <div><strong>{item.titulo}</strong><small>{item.status} · {item.local || "Sem local"} · {item.achados.length} achado(s)</small></div>
              <button className="secondary-button compact" onClick={() => openReport(item)}><FileText size={15} /> Relatório</button>
            </article>
          ))}
        </div>
        {report && (
          <section className="settings-form agenda-detail">
            <div className="settings-title"><FileText size={21} /><div><strong>{report.titulo}</strong><small>{report.status}</small></div></div>
            <pre className="report-preview">{report.relatorio}</pre>
          </section>
        )}
      </section>
    </>
  );
}

function splitLines(value) {
  return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
}
