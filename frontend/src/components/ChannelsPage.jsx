import { Inbox, MessageSquare, Plus, RotateCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const emptyForm = {
  canal: "WHATSAPP",
  remetenteNome: "",
  remetenteContato: "",
  assunto: "",
  conteudo: "",
};

export function ChannelsPage() {
  const [messages, setMessages] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const data = await apiRequest("/api/v1/canais/mensagens");
    setMessages(data.content);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    setError("");
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
          <h1>Canais</h1>
          <p>Caixa de entrada para WhatsApp, e-mail, redes sociais e formulários públicos.</p>
        </div>
        <button className="secondary-button" onClick={load}><RotateCw size={16} /> Atualizar</button>
      </section>
      <section className="admin-layout agenda-layout">
        <form className="settings-form" onSubmit={submit}>
          <div className="settings-title"><MessageSquare size={21} /><div><strong>Registrar mensagem</strong><small>Use para entradas manuais ou simulações de webhook.</small></div></div>
          <div className="form-grid">
            <label>Canal<select value={form.canal} onChange={(event) => setForm((current) => ({ ...current, canal: event.target.value }))}>
              <option value="WHATSAPP">WhatsApp</option>
              <option value="EMAIL">E-mail</option>
              <option value="REDE_SOCIAL">Rede social</option>
            </select></label>
            <label>Contato<input value={form.remetenteContato} onChange={(event) => setForm((current) => ({ ...current, remetenteContato: event.target.value }))} /></label>
          </div>
          <label>Nome<input value={form.remetenteNome} onChange={(event) => setForm((current) => ({ ...current, remetenteNome: event.target.value }))} /></label>
          <label>Assunto<input value={form.assunto} onChange={(event) => setForm((current) => ({ ...current, assunto: event.target.value }))} /></label>
          <label>Mensagem<textarea required rows="5" value={form.conteudo} onChange={(event) => setForm((current) => ({ ...current, conteudo: event.target.value }))} /></label>
          {error && <p className="form-error">{error}</p>}
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
              <button className="secondary-button compact" disabled={item.status !== "RECEBIDA"} onClick={() => convertMessage(item)}>
                Converter
              </button>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function channelLabel(value) {
  return {
    WHATSAPP: "WhatsApp",
    EMAIL: "E-mail",
    REDE_SOCIAL: "Rede social",
    FORMULARIO: "Formulário",
  }[value] || value;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
