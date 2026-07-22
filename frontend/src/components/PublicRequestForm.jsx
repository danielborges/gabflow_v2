import { useEffect, useState } from "react";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail } from "../contactValidation";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

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
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    apiRequest(`/api/v1/publico/formularios/${tenant}`)
      .then(setConfig)
      .catch((requestError) => setError(requestError.message));
  }, [tenant]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!validateContact(form.contato)) return;
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

  function updateContact(value) {
    const nextValue = /^[\d\s()+-]*$/.test(value) ? formatBrazilianPhone(value) : value;
    setForm((current) => ({ ...current, contato: nextValue }));
    if (fieldErrors.contato) setFieldErrors({});
  }

  function validateContact(value) {
    const trimmed = value.trim();
    if (!trimmed) {
      setFieldErrors({});
      return true;
    }
    const valid = trimmed.includes("@") ? isValidEmail(trimmed) : isValidBrazilianPhone(trimmed);
    setFieldErrors(valid ? {} : { contato: "Informe um e-mail válido ou telefone com DDD." });
    return valid;
  }

  if (error) return <main className="public-form-shell"><p className="form-error">{error}</p></main>;
  if (!config) return <main className="public-form-shell"><div className="table-message">Carregando formulário...</div></main>;

  return (
    <main className="public-form-shell">
      <form className="public-request-form" onSubmit={submit} noValidate>
        <header>
          <img src="/images/logo.png" alt="GabFlow" />
          <div>
            <p className="eyebrow">Atendimento ao cidadão</p>
            <h1>{config.nome}</h1>
          </div>
        </header>
        {!config.ativo ? <p className="form-error">O formulário público está inativo.</p> : <>
          <label>Nome<input value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} /></label>
          <label>Contato<input type={form.contato.includes("@") ? "email" : "tel"} inputMode={form.contato.includes("@") ? "email" : "text"} placeholder="E-mail ou telefone" value={form.contato} onChange={(event) => updateContact(event.target.value)} aria-invalid={Boolean(fieldErrors.contato)} />{fieldErrors.contato && <small className="field-error">{fieldErrors.contato}</small>}</label>
          <label>Título<input required value={form.titulo} onChange={(event) => setForm((current) => ({ ...current, titulo: event.target.value }))} /></label>
          <label>Descrição<textarea required rows="6" value={form.descricao} onChange={(event) => setForm((current) => ({ ...current, descricao: event.target.value }))} /></label>
          <label>Endereço<GooglePlaceAutocompleteInput value={form.endereco} onChange={(endereco) => setForm((current) => ({ ...current, endereco }))} placeholder="Digite o endereço da solicitação" territoryBounds={config.jurisdicao?.limites} inputProps={{ "aria-label": "Endereço" }} /></label>
          {result && <p className="form-success">Solicitação registrada: {result.protocolo}</p>}
          <button className="primary-button">Enviar solicitação</button>
        </>}
      </form>
    </main>
  );
}
