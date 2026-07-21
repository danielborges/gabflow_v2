import { Building2, Clock3, FileText, MapPinned, PlugZap, Plus, Settings2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const sections = [
  ["jurisdiction", "Jurisdição"],
  ["categories", "Categorias"],
  ["territories", "Territórios"],
  ["agencies", "Órgãos"],
  ["templates", "Templates"],
  ["integrations", "Integracoes"],
];

const initialForm = {
  nome: "",
  slaHoras: 72,
  emailContato: "",
  canal: "WHATSAPP",
  categoriaId: "",
  assunto: "",
  conteudo: "",
  tipoIntegracao: "WHATSAPP",
  statusIntegracao: "RASCUNHO",
  configuracao: "",
  segredo: "",
};

export function AdministrationPage() {
  const [active, setActive] = useState("categories");
  const [data, setData] = useState({
    categories: [],
    territories: [],
    agencies: [],
    templates: [],
    integrations: [],
    jurisdiction: null,
  });
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [categories, territories, agencies, templates, jurisdiction, integrations] = await Promise.all([
      apiRequest("/api/v1/admin/categorias"),
      apiRequest("/api/v1/admin/territorios"),
      apiRequest("/api/v1/admin/orgaos"),
      apiRequest("/api/v1/admin/templates-resposta"),
      apiRequest("/api/v1/admin/jurisdicao"),
      apiRequest("/api/v1/admin/integracoes"),
    ]);
    setData({
      categories: categories.content,
      territories: territories.content,
      agencies: agencies.content,
      templates: templates.content,
      integrations: integrations.content.map((item) => ({
        ...item,
        emailContato: `${item.tipo} · ${item.status} · ${item.segredosConfigurados ? "segredo configurado" : "sem segredo"}`,
        ativa: item.status === "ATIVA",
      })),
      jurisdiction,
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
      integrations: "/api/v1/admin/integracoes",
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
    if (active === "integrations") {
      Object.assign(payload, {
        tipo: form.tipoIntegracao,
        status: form.statusIntegracao,
        configuracao: integrationConfig(form.configuracao, form.segredo),
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
    jurisdiction: ["Jurisdição territorial", "Defina a área institucional do gabinete.", MapPinned],
  };
  labels.integrations = ["Nova integracao", "Configure canais e sistemas externos por tenant.", PlugZap];
  const [title, description, Icon] = labels[active];

  return <>
    <section className="page-heading"><div><p className="eyebrow">Parametrização</p><h1>Operação do gabinete</h1><p>Configure classificação, territórios, órgãos, SLA e respostas padronizadas.</p></div></section>
    <section className="admin-tabs segmented-control">
      {sections.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>{label}</button>)}
    </section>
    <section className="admin-layout">
      {active === "jurisdiction" ? <JurisdictionSettings data={data.jurisdiction} onSaved={load} /> : <>
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
        {active === "integrations" && <>
          <div className="form-grid">
            <label>Tipo<select value={form.tipoIntegracao} onChange={(event) => setForm((current) => ({ ...current, tipoIntegracao: event.target.value }))}>
              <option value="WHATSAPP">WhatsApp Business</option>
              <option value="EMAIL">E-mail</option>
              <option value="FORMULARIO_PUBLICO">Formulario publico</option>
              <option value="REDE_SOCIAL">Rede social</option>
              <option value="SISTEMA_LEGISLATIVO">Sistema legislativo</option>
              <option value="PROTOCOLO_EXTERNO">Protocolo externo</option>
            </select></label>
            <label>Status<select value={form.statusIntegracao} onChange={(event) => setForm((current) => ({ ...current, statusIntegracao: event.target.value }))}>
              <option value="RASCUNHO">Rascunho</option>
              <option value="ATIVA">Ativa</option>
              <option value="INATIVA">Inativa</option>
            </select></label>
          </div>
          <label>Configuracao publica<textarea rows="4" value={form.configuracao} onChange={(event) => setForm((current) => ({ ...current, configuracao: event.target.value }))} placeholder="numero=+5532999999999&#10;webhook=https://..." /></label>
          <label>Token ou segredo<input value={form.segredo} onChange={(event) => setForm((current) => ({ ...current, segredo: event.target.value }))} /></label>
        </>}
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button compact"><Plus size={18} /> Adicionar</button>
      </form>
      <div className="category-list">
        {data[active].map((item) => <article key={item.id}><span className="entity-icon"><Icon size={19} /></span><div><strong>{item.nome}</strong><small>{active === "templates" ? `${item.canal} · ${item.categoria || "Todas as categorias"} · v${item.versao}` : item.emailContato || (item.ativa ? "Ativo" : "Inativo")}</small></div>{active === "categories" && <span>{item.slaHoras}h</span>}</article>)}
      </div>
      </>}
    </section>
  </>;
}

function integrationConfig(value, secret) {
  const config = {};
  String(value || "").split("\n").forEach((line) => {
    const [key, ...rest] = line.split("=");
    if (key?.trim() && rest.length) config[key.trim()] = rest.join("=").trim();
  });
  if (secret) config.token = secret;
  return config;
}

function JurisdictionSettings({ data, onSaved }) {
  const [form, setForm] = useState(() => jurisdictionForm(data));
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    setForm(jurisdictionForm(data));
  }, [data]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/admin/jurisdicao", {
        method: "PATCH",
        body: JSON.stringify({
          tipoCasa: form.tipoCasa,
          nome: form.nome,
          municipio: form.municipio,
          uf: form.uf,
          codigoIbge: form.codigoIbge,
          centro: {
            latitude: form.latitude ? Number(form.latitude) : null,
            longitude: form.longitude ? Number(form.longitude) : null,
          },
          limites: {
            minLatitude: Number(form.minLatitude),
            maxLatitude: Number(form.maxLatitude),
            minLongitude: Number(form.minLongitude),
            maxLongitude: Number(form.maxLongitude),
          },
        }),
      });
      await onSaved();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function importFromIbge() {
    setError("");
    setImporting(true);
    try {
      await apiRequest("/api/v1/admin/jurisdicao/ibge", {
        method: "POST",
        body: JSON.stringify({
          tipoCasa: form.tipoCasa,
          codigoIbge: form.codigoIbge,
          nome: form.nome,
        }),
      });
      await onSaved();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setImporting(false);
    }
  }

  return (
    <form className="settings-form jurisdiction-form" onSubmit={submit}>
      <div className="settings-title"><MapPinned size={21} /><div><strong>Jurisdição territorial</strong><small>Escopo usado pelo mapa de calor e alertas territoriais.</small></div></div>
      <div className="form-grid">
        <label>Tipo<select value={form.tipoCasa} onChange={(event) => setForm((current) => ({ ...current, tipoCasa: event.target.value }))}><option value="CAMARA_MUNICIPAL">Câmara Municipal</option><option value="ASSEMBLEIA_LEGISLATIVA">Assembleia Legislativa</option></select></label>
        <label>UF<input required maxLength="2" value={form.uf} onChange={(event) => setForm((current) => ({ ...current, uf: event.target.value.toUpperCase() }))} /></label>
      </div>
      <label>Nome da jurisdição<input value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} placeholder="Ex.: Juiz de Fora/MG" /></label>
      <label>Município<input value={form.municipio} onChange={(event) => setForm((current) => ({ ...current, municipio: event.target.value }))} placeholder="Obrigatório para Câmara Municipal" /></label>
      <div className="form-grid">
        <label>Código IBGE<input value={form.codigoIbge} onChange={(event) => setForm((current) => ({ ...current, codigoIbge: event.target.value.replace(/\D/g, "") }))} placeholder="Ex.: 3136702" /></label>
        <button type="button" className="secondary-button jurisdiction-import-button" disabled={importing || !form.codigoIbge} onClick={importFromIbge}>{importing ? "Carregando malha..." : "Carregar malha do IBGE"}</button>
      </div>
      <div className="form-grid">
        <label>Latitude central<input type="number" step="0.000001" value={form.latitude} onChange={(event) => setForm((current) => ({ ...current, latitude: event.target.value }))} /></label>
        <label>Longitude central<input type="number" step="0.000001" value={form.longitude} onChange={(event) => setForm((current) => ({ ...current, longitude: event.target.value }))} /></label>
      </div>
      <div className="form-grid">
        <label>Latitude mínima<input required type="number" step="0.000001" value={form.minLatitude} onChange={(event) => setForm((current) => ({ ...current, minLatitude: event.target.value }))} /></label>
        <label>Latitude máxima<input required type="number" step="0.000001" value={form.maxLatitude} onChange={(event) => setForm((current) => ({ ...current, maxLatitude: event.target.value }))} /></label>
        <label>Longitude mínima<input required type="number" step="0.000001" value={form.minLongitude} onChange={(event) => setForm((current) => ({ ...current, minLongitude: event.target.value }))} /></label>
        <label>Longitude máxima<input required type="number" step="0.000001" value={form.maxLongitude} onChange={(event) => setForm((current) => ({ ...current, maxLongitude: event.target.value }))} /></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      {data?.geojson && <p className="form-success">Malha oficial carregada para o mapa territorial.</p>}
      <button className="primary-button compact">Salvar jurisdição</button>
    </form>
  );
}

function jurisdictionForm(data) {
  const bounds = data?.limites || {};
  return {
    tipoCasa: data?.tipoCasa || "CAMARA_MUNICIPAL",
    nome: data?.nome || "",
    municipio: data?.municipio || "",
    uf: data?.uf || "",
    codigoIbge: data?.codigoIbge || "",
    latitude: data?.centro?.latitude ?? "",
    longitude: data?.centro?.longitude ?? "",
    minLatitude: bounds.minLatitude ?? "",
    maxLatitude: bounds.maxLatitude ?? "",
    minLongitude: bounds.minLongitude ?? "",
    maxLongitude: bounds.maxLongitude ?? "",
  };
}
