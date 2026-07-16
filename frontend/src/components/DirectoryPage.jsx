import { Building2, Plus, Search, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

export function DirectoryPage() {
  const [tab, setTab] = useState("citizens");
  const [citizens, setCitizens] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState(null);
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

  return (
    <>
      <section className="page-heading request-heading">
        <div>
          <p className="eyebrow">Relacionamento</p>
          <h1>Cidadãos e organizações</h1>
          <p>Cadastros mínimos, contatos, consentimentos e territórios.</p>
        </div>
        <button className="primary-button compact" onClick={() => setModal(tab)}>
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
              <article key={item.id}>
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

      {modal === "citizens" && <CitizenForm onClose={() => setModal(null)} onCreated={() => { setModal(null); load(); }} />}
      {modal === "organizations" && <OrganizationForm onClose={() => setModal(null)} onCreated={() => { setModal(null); load(); }} />}
    </>
  );
}

function CitizenForm({ onClose, onCreated }) {
  const [form, setForm] = useState({
    nome: "", nomeSocial: "", telefone: "", email: "", endereco: "",
    canalPreferencial: "WHATSAPP", baseLegal: "EXECUCAO_POLITICA_PUBLICA",
    consentimentoContato: false, consentimentoDivulgacao: false,
  });
  const [error, setError] = useState("");

  function change(event) {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [event.target.name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/cidadaos", {
        method: "POST",
        body: JSON.stringify({
          nome: form.nome,
          nomeSocial: form.nomeSocial,
          contatos: [
            ...(form.telefone ? [{ tipo: "TELEFONE", valor: form.telefone }] : []),
            ...(form.email ? [{ tipo: "EMAIL", valor: form.email }] : []),
          ],
          enderecos: form.endereco ? [{ endereco: form.endereco }] : [],
          canalPreferencial: form.canalPreferencial,
          baseLegal: form.baseLegal,
          consentimentoContato: form.consentimentoContato,
          consentimentoDivulgacao: form.consentimentoDivulgacao,
        }),
      });
      onCreated();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return <EntityModal title="Cadastrar cidadão" onClose={onClose}><form className="request-form" onSubmit={submit}>
    <div className="form-grid"><label>Nome<input required name="nome" value={form.nome} onChange={change} /></label><label>Nome social<input name="nomeSocial" value={form.nomeSocial} onChange={change} /></label></div>
    <div className="form-grid"><label>Telefone<input name="telefone" value={form.telefone} onChange={change} /></label><label>E-mail<input type="email" name="email" value={form.email} onChange={change} /></label></div>
    <label>Endereço<input name="endereco" value={form.endereco} onChange={change} /></label>
    <div className="form-grid"><label>Canal preferencial<select name="canalPreferencial" value={form.canalPreferencial} onChange={change}><option>WHATSAPP</option><option>TELEFONE</option><option>EMAIL</option><option>PRESENCIAL</option></select></label><label>Base legal<select name="baseLegal" value={form.baseLegal} onChange={change}><option value="EXECUCAO_POLITICA_PUBLICA">Execução de política pública</option><option value="CONSENTIMENTO">Consentimento</option><option value="LEGITIMO_INTERESSE">Legítimo interesse</option></select></label></div>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoContato" checked={form.consentimentoContato} onChange={change} /> Autoriza contato pelo gabinete</label>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoDivulgacao" checked={form.consentimentoDivulgacao} onChange={change} /> Autoriza divulgação pública</label>
    {error && <p className="form-error">{error}</p>}<FormFooter onClose={onClose} />
  </form></EntityModal>;
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

function FormFooter({ onClose }) {
  return <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact"><Plus size={18} /> Salvar</button></footer>;
}

