import { Building2, Plus, Save, Search, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail } from "../contactValidation";

export function DirectoryPage() {
  const [tab, setTab] = useState("citizens");
  const [citizens, setCitizens] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState(null);
  const [selectedCitizen, setSelectedCitizen] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [citizenData, organizationData] = await Promise.all([
        apiRequest(`/api/v1/cidadaos?q=${encodeURIComponent(query)}`),
        apiRequest("/api/v1/organizacoes"),
      ]);
      setCitizens(citizenData.content);
      setOrganizations(organizationData.content);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const items = tab === "citizens" ? citizens : organizations;

  function closeModal() {
    setModal(null);
    setSelectedCitizen(null);
  }

  function createEntity() {
    setSelectedCitizen(null);
    setModal(tab);
  }

  function editCitizen(citizen) {
    setSelectedCitizen(citizen);
    setModal("citizens");
  }

  return (
    <>
      <section className="page-heading request-heading">
        <div>
          <p className="eyebrow">Relacionamento</p>
          <h1>Cidadãos e organizações</h1>
          <p>Cadastros mínimos, contatos, consentimentos e territórios.</p>
        </div>
        <button className="primary-button compact" onClick={createEntity}>
          <Plus size={18} /> {tab === "citizens" ? "Novo cidadão" : "Nova organização"}
        </button>
      </section>

      <section className="directory-controls">
        <div className="segmented-control" aria-label="Tipo de cadastro">
          <button className={tab === "citizens" ? "active" : ""} onClick={() => setTab("citizens")}><UserRound size={17} /> Cidadãos</button>
          <button className={tab === "organizations" ? "active" : ""} onClick={() => setTab("organizations")}><Building2 size={17} /> Organizações</button>
        </div>
        {tab === "citizens" && (
          <label className="toolbar-search">
            <Search size={18} />
            <input aria-label="Buscar cidadãos" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nome ou nome social" />
          </label>
        )}
      </section>

      <section className="directory-list">
        {loading ? <div className="table-message">Carregando cadastros...</div> : items.length === 0 ? (
          <div className="empty-state request-empty"><div className="empty-icon">{tab === "citizens" ? <UserRound size={27} /> : <Building2 size={27} />}</div><h2>Nenhum cadastro encontrado</h2><p>Use o botão acima para iniciar o diretório do gabinete.</p></div>
        ) : (
          <div className="entity-grid">
            {items.map((item) => (
              <article
                key={item.id}
                className={tab === "citizens" ? "interactive" : undefined}
                role={tab === "citizens" ? "button" : undefined}
                tabIndex={tab === "citizens" ? 0 : undefined}
                onClick={tab === "citizens" ? () => editCitizen(item) : undefined}
                onKeyDown={tab === "citizens" ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    editCitizen(item);
                  }
                } : undefined}
                aria-label={tab === "citizens" ? `Editar cidadão ${item.nome}` : undefined}
              >
                <span className="entity-icon">{tab === "citizens" ? <UserRound size={20} /> : <Building2 size={20} />}</span>
                <div><strong>{item.nome}</strong><small>{tab === "citizens" ? item.canalPreferencial || "Sem canal preferencial" : item.tipo}</small></div>
                <span className={tab === "citizens" && item.consentimentoContato ? "consent yes" : "consent"}>
                  {tab === "citizens" ? (item.consentimentoContato ? "Contato autorizado" : "Sem consentimento") : item.territorio || "Sem território"}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>

      {modal === "citizens" && <CitizenForm citizen={selectedCitizen} onClose={closeModal} onSaved={() => { closeModal(); load(); }} />}
      {modal === "organizations" && <OrganizationForm onClose={closeModal} onCreated={() => { closeModal(); load(); }} />}
    </>
  );
}

function CitizenForm({ citizen, onClose, onSaved }) {
  const isEditing = Boolean(citizen?.id);
  const [form, setForm] = useState(() => citizenFormValues(citizen));
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});

  function change(event) {
    const { name, type, checked } = event.target;
    let value = type === "checkbox" ? checked : event.target.value;
    if (name === "telefone") value = formatBrazilianPhone(value);
    setForm((current) => ({ ...current, [name]: value }));
    if (fieldErrors[name]) setFieldErrors((current) => ({ ...current, [name]: "" }));
  }

  function validateContacts() {
    const errors = {};
    if (form.telefone && !isValidBrazilianPhone(form.telefone)) {
      errors.telefone = "Informe um telefone válido com DDD, usando 10 ou 11 dígitos.";
    }
    if (form.email && !isValidEmail(form.email)) {
      errors.email = "Informe um e-mail válido, como nome@dominio.com.br.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!validateContacts()) return;
    try {
      await apiRequest(isEditing ? `/api/v1/cidadaos/${citizen.id}` : "/api/v1/cidadaos", {
        method: isEditing ? "PATCH" : "POST",
        body: JSON.stringify({
          nome: form.nome,
          nomeSocial: form.nomeSocial,
          contatos: updatedContacts(citizen, form),
          enderecos: updatedAddresses(citizen, form.endereco),
          canalPreferencial: form.canalPreferencial,
          baseLegal: form.baseLegal,
          consentimentoContato: form.consentimentoContato,
          consentimentoDivulgacao: form.consentimentoDivulgacao,
        }),
      });
      onSaved();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return <EntityModal title={isEditing ? "Editar cidadão" : "Cadastrar cidadão"} onClose={onClose}><form className="request-form" onSubmit={submit} noValidate>
    <div className="form-grid"><label>Nome<input required name="nome" value={form.nome} onChange={change} /></label><label>Nome social<input name="nomeSocial" value={form.nomeSocial} onChange={change} /></label></div>
    <div className="form-grid">
      <label>Telefone
        <input name="telefone" type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={form.telefone} onChange={change} aria-invalid={Boolean(fieldErrors.telefone)} aria-describedby={fieldErrors.telefone ? "citizen-phone-error" : undefined} />
        {fieldErrors.telefone && <small id="citizen-phone-error" className="field-error">{fieldErrors.telefone}</small>}
      </label>
      <label>E-mail
        <input type="email" name="email" inputMode="email" autoComplete="email" placeholder="nome@dominio.com.br" value={form.email} onChange={change} aria-invalid={Boolean(fieldErrors.email)} aria-describedby={fieldErrors.email ? "citizen-email-error" : undefined} />
        {fieldErrors.email && <small id="citizen-email-error" className="field-error">{fieldErrors.email}</small>}
      </label>
    </div>
    <label>Endereço<input name="endereco" value={form.endereco} onChange={change} /></label>
    <div className="form-grid"><label>Canal preferencial<select name="canalPreferencial" value={form.canalPreferencial} onChange={change}><option>WHATSAPP</option><option>TELEFONE</option><option>EMAIL</option><option>PRESENCIAL</option></select></label><label>Base legal<select name="baseLegal" value={form.baseLegal} onChange={change}><option value="EXECUCAO_POLITICA_PUBLICA">Execução de política pública</option><option value="CONSENTIMENTO">Consentimento</option><option value="LEGITIMO_INTERESSE">Legítimo interesse</option></select></label></div>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoContato" checked={form.consentimentoContato} onChange={change} /> Autoriza contato pelo gabinete</label>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoDivulgacao" checked={form.consentimentoDivulgacao} onChange={change} /> Autoriza divulgação pública</label>
    {error && <p className="form-error" role="alert">{error}</p>}<FormFooter onClose={onClose} isEditing={isEditing} />
  </form></EntityModal>;
}

function citizenFormValues(citizen) {
  const contacts = citizen?.contatos || [];
  const phone = contacts.find((item) => ["TELEFONE", "CELULAR", "WHATSAPP"].includes(String(item.tipo).toUpperCase()));
  const email = contacts.find((item) => String(item.tipo).toUpperCase() === "EMAIL");
  const address = citizen?.enderecos?.[0];
  return {
    nome: citizen?.nome || "",
    nomeSocial: citizen?.nomeSocial || "",
    telefone: formatBrazilianPhone(String(phone?.valor || "")),
    email: email?.valor || "",
    endereco: address?.endereco || address?.logradouro || "",
    canalPreferencial: citizen?.canalPreferencial || "WHATSAPP",
    baseLegal: citizen?.baseLegal || "EXECUCAO_POLITICA_PUBLICA",
    consentimentoContato: Boolean(citizen?.consentimentoContato),
    consentimentoDivulgacao: Boolean(citizen?.consentimentoDivulgacao),
  };
}

function updatedContacts(citizen, form) {
  const editableTypes = new Set(["TELEFONE", "CELULAR", "WHATSAPP", "EMAIL"]);
  const preserved = (citizen?.contatos || []).filter((item) => !editableTypes.has(String(item.tipo).toUpperCase()));
  return [
    ...preserved,
    ...(form.telefone ? [{ tipo: "TELEFONE", valor: form.telefone }] : []),
    ...(form.email ? [{ tipo: "EMAIL", valor: form.email.trim() }] : []),
  ];
}

function updatedAddresses(citizen, address) {
  const existing = citizen?.enderecos || [];
  if (!address.trim()) return existing.slice(1);
  return [{ ...(existing[0] || {}), endereco: address.trim() }, ...existing.slice(1)];
}

function OrganizationForm({ onClose, onCreated }) {
  const [form, setForm] = useState({ nome: "", tipo: "ASSOCIACAO", email: "", telefone: "", territorio: "" });
  const [error, setError] = useState("");
  function change(event) { setForm((current) => ({ ...current, [event.target.name]: event.target.value })); }
  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/organizacoes", { method: "POST", body: JSON.stringify({
        nome: form.nome, tipo: form.tipo, territorio: form.territorio,
        contatos: [...(form.email ? [{ tipo: "EMAIL", valor: form.email }] : []), ...(form.telefone ? [{ tipo: "TELEFONE", valor: form.telefone }] : [])],
      }) });
      onCreated();
    } catch (requestError) { setError(requestError.message); }
  }
  return <EntityModal title="Cadastrar organização" onClose={onClose}><form className="request-form" onSubmit={submit}>
    <div className="form-grid"><label>Nome<input required name="nome" value={form.nome} onChange={change} /></label><label>Tipo<select name="tipo" value={form.tipo} onChange={change}><option value="ASSOCIACAO">Associação</option><option value="ESCOLA">Escola</option><option value="EMPRESA">Empresa</option><option value="LIDERANCA">Liderança</option><option value="OUTRA">Outra</option></select></label></div>
    <div className="form-grid"><label>E-mail<input type="email" name="email" value={form.email} onChange={change} /></label><label>Telefone<input name="telefone" value={form.telefone} onChange={change} /></label></div>
    <label>Território<input name="territorio" value={form.territorio} onChange={change} placeholder="Bairro ou região" /></label>
    {error && <p className="form-error">{error}</p>}<FormFooter onClose={onClose} />
  </form></EntityModal>;
}

function EntityModal({ title, onClose, children }) {
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label={title}><header><div><p className="eyebrow">Diretório</p><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar"><X size={20} /></button></header>{children}</section></div>;
}

function FormFooter({ onClose, isEditing = false }) {
  return <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact">{isEditing ? <Save size={18} /> : <Plus size={18} />} {isEditing ? "Salvar alterações" : "Salvar"}</button></footer>;
}
