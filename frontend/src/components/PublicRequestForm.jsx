import { useEffect, useState } from "react";
import { apiRequest } from "../api";

const emptyForm = {
  nome: "",
  contato: "",
  titulo: "",
  descricao: "",
  endereco: "",
};

export function PublicRequestForm({ tenant }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest(`/api/v1/publico/formularios/${tenant}`)
      .then(setConfig)
      .catch((requestError) => setError(requestError.message));
  }, [tenant]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      setResult(await apiRequest(`/api/v1/publico/formularios/${tenant}/solicitacoes`, {
        method: "POST",
        body: JSON.stringify(form),
      }));
      setForm(emptyForm);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  if (error) return <main className="public-form-shell"><p className="form-error">{error}</p></main>;
  if (!config) return <main className="public-form-shell"><div className="table-message">Carregando formulário...</div></main>;

  return (
    <main className="public-form-shell">
      <form className="public-request-form" onSubmit={submit}>
        <header>
          <img src="/images/logo.png" alt="GabFlow" />
          <div>
            <p className="eyebrow">Atendimento ao cidadão</p>
            <h1>{config.nome}</h1>
          </div>
        </header>
        {!config.ativo ? <p className="form-error">O formulário público está inativo.</p> : <>
          <label>Nome<input value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} /></label>
          <label>Contato<input value={form.contato} onChange={(event) => setForm((current) => ({ ...current, contato: event.target.value }))} /></label>
          <label>Título<input required value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} /></label>
          <label>Descrição<textarea required rows="6" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} /></label>
          <label>Endereço<input value={form.endereco} onChange={(event) => setForm((current) => ({ ...current, endereco: event.target.value }))} /></label>
          {result && <p className="form-success">Solicitação registrada: {result.protocolo}</p>}
          <button className="primary-button">Enviar solicitação</button>
        </>}
      </form>
    </main>
  );
}
