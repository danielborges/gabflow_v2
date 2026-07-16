import { Building2, Clock3, FileText, MapPinned, Plus, Settings2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const sections = [
  ["categories", "Categorias"],
  ["territories", "Territórios"],
  ["agencies", "Órgãos"],
  ["templates", "Templates"],
];

const initialForm = {
  nome: "",
  slaHoras: 72,
  emailContato: "",
  canal: "WHATSAPP",
  categoriaId: "",
  assunto: "",
  conteudo: "",
};

export function AdministrationPage() {
  const [active, setActive] = useState("categories");
  const [data, setData] = useState({
    categories: [],
    territories: [],
    agencies: [],
    templates: [],
  });
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [categories, territories, agencies, templates] = await Promise.all([
      apiRequest("/api/v1/admin/categorias"),
      apiRequest("/api/v1/admin/territorios"),
      apiRequest("/api/v1/admin/orgaos"),
      apiRequest("/api/v1/admin/templates-resposta"),
    ]);
    setData({
      categories: categories.content,
      territories: territories.content,
      agencies: agencies.content,
      templates: templates.content,
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    const paths = {
      categories: "/api/v1/admin/categorias",
      territories: "/api/v1/admin/territorios",
      agencies: "/api/v1/admin/orgaos",
      templates: "/api/v1/admin/templates-resposta",
    };
    const payload = { nome: form.nome };
    if (active === "categories") payload.slaHoras = Number(form.slaHoras);
    if (active === "agencies") payload.emailContato = form.emailContato;
    if (active === "templates") {
      Object.assign(payload, {
        canal: form.canal,
        categoriaId: form.categoriaId || null,
        assunto: form.assunto || null,
        conteudo: form.conteudo,
      });
    }
    try {
      await apiRequest(paths[active], { method: "POST", body: JSON.stringify(payload) });
      setForm(initialForm);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const labels = {
    categories: ["Nova categoria", "O SLA será aplicado à solicitação.", Clock3],
    territories: ["Novo território", "Organize as demandas por bairro ou região.", MapPinned],
    agencies: ["Novo órgão", "Cadastre os destinatários dos encaminhamentos.", Building2],
    templates: ["Novo template", "Use somente as variáveis seguras indicadas.", FileText],
  };
  const [title, description, Icon] = labels[active];

  return <>
    <section className="page-heading"><div><p className="eyebrow">Parametrização</p><h1>Operação do gabinete</h1><p>Configure classificação, territórios, órgãos, SLA e respostas padronizadas.</p></div></section>
    <section className="admin-tabs segmented-control">
      {sections.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>{label}</button>)}
    </section>
    <section className="admin-layout">
      <form className="settings-form" onSubmit={submit}>
        <div className="settings-title"><Settings2 size={21} /><div><strong>{title}</strong><small>{description}</small></div></div>
        <label>Nome<input required value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} /></label>
        {active === "categories" && <label>SLA em horas<input required type="number" min="1" max="8760" value={form.slaHoras} onChange={(event) => setForm((current) => ({ ...current, slaHoras: event.target.value }))} /></label>}
        {active === "agencies" && <label>E-mail de contato<input type="email" value={form.emailContato} onChange={(event) => setForm((current) => ({ ...current, emailContato: event.target.value }))} /></label>}
        {active === "templates" && <>
          <div className="form-grid">
            <label>Canal<select value={form.canal} onChange={(event) => setForm((current) => ({ ...current, canal: event.target.value }))}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
            <label>Categoria<select value={form.categoriaId} onChange={(event) => setForm((current) => ({ ...current, categoriaId: event.target.value }))}><option value="">Todas</option>{data.categories.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
          </div>
          <label>Assunto<input value={form.assunto} onChange={(event) => setForm((current) => ({ ...current, assunto: event.target.value }))} /></label>
          <label>Conteúdo<textarea required rows="7" value={form.conteudo} onChange={(event) => setForm((current) => ({ ...current, conteudo: event.target.value }))} placeholder="Olá, {{cidadao}}. A solicitação {{protocolo}} está com status {{status}}." /></label>
          <small className="template-help">Variáveis permitidas: {"{{cidadao}}"}, {"{{protocolo}}"} e {"{{status}}"}</small>
        </>}
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button compact"><Plus size={18} /> Adicionar</button>
      </form>
      <div className="category-list">
        {data[active].map((item) => <article key={item.id}><span className="entity-icon"><Icon size={19} /></span><div><strong>{item.nome}</strong><small>{active === "templates" ? `${item.canal} · ${item.categoria || "Todas as categorias"} · v${item.versao}` : item.emailContato || (item.ativa ? "Ativo" : "Inativo")}</small></div>{active === "categories" && <span>{item.slaHoras}h</span>}</article>)}
      </div>
    </section>
  </>;
}
