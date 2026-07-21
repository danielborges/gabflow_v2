import {
  Building2,
  Clock3,
  FileText,
  MapPinned,
  PlugZap,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const sections = [
  ["office", "Gabinete"],
  ["users", "Usuarios"],
  ["jurisdiction", "Jurisdicao"],
  ["categories", "Categorias"],
  ["territories", "Territorios"],
  ["agencies", "Orgaos"],
  ["templates", "Templates"],
  ["integrations", "Integracoes"],
  ["audit", "Auditoria"],
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
  nomeUsuario: "",
  emailUsuario: "",
  senhaUsuario: "",
  perfilUsuario: "staff",
};

const emptyOffice = {
  vereador: {},
  mandato: {},
  identidadeVisual: {},
  chefeGabineteId: "",
};

export function AdministrationPage() {
  const [active, setActive] = useState("office");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPerPage, setAuditPerPage] = useState(10);
  const [data, setData] = useState({
    categories: [],
    territories: [],
    agencies: [],
    templates: [],
    integrations: [],
    jurisdiction: null,
    office: emptyOffice,
    users: [],
    audit: [],
    auditPagination: { page: 1, perPage: 10, total: 0, totalPages: 1 },
  });
  const [form, setForm] = useState(initialForm);
  const [officeForm, setOfficeForm] = useState(emptyOffice);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [categories, territories, agencies, templates, jurisdiction, integrations, office, users, audit] =
      await Promise.all([
        apiRequest("/api/v1/admin/categorias"),
        apiRequest("/api/v1/admin/territorios"),
        apiRequest("/api/v1/admin/orgaos"),
        apiRequest("/api/v1/admin/templates-resposta"),
        apiRequest("/api/v1/admin/jurisdicao"),
        apiRequest("/api/v1/admin/integracoes"),
        apiRequest("/api/v1/admin/perfil-gabinete"),
        apiRequest("/api/v1/admin/usuarios"),
        apiRequest(`/api/v1/admin/auditoria?page=${auditPage}&perPage=${auditPerPage}`),
      ]);
    const mappedOffice = normalizeOffice(office);
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
      office: mappedOffice,
      users: users.content,
      audit: audit.content,
      auditPagination: {
        page: audit.page,
        perPage: audit.perPage,
        total: audit.total,
        totalPages: audit.totalPages,
      },
    });
    setOfficeForm(mappedOffice);
  }, [auditPage, auditPerPage]);

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

  async function saveOffice(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/admin/perfil-gabinete", {
        method: "PATCH",
        body: JSON.stringify(officeForm),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function createUser(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/admin/usuarios", {
        method: "POST",
        body: JSON.stringify({
          nome: form.nomeUsuario,
          email: form.emailUsuario,
          senha: form.senhaUsuario,
          perfil: form.perfilUsuario,
        }),
      });
      setForm((current) => ({ ...current, nomeUsuario: "", emailUsuario: "", senhaUsuario: "" }));
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function updateUser(user, patch) {
    await apiRequest(`/api/v1/admin/usuarios/${user.id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    await load();
  }

  const labels = {
    categories: ["Nova categoria", "O SLA sera aplicado a solicitacao.", Clock3],
    territories: ["Novo territorio", "Organize as demandas por bairro ou regiao.", MapPinned],
    agencies: ["Novo orgao", "Cadastre os destinatarios dos encaminhamentos.", Building2],
    templates: ["Novo template", "Use somente as variaveis seguras indicadas.", FileText],
    integrations: ["Nova integracao", "Configure canais e sistemas externos autorizados.", PlugZap],
  };
  const [title, description, Icon] = labels[active] || [];
  const wideLayout = ["audit", "office", "jurisdiction"].includes(active);

  return <>
    <section className="page-heading"><div><p className="eyebrow">Administrador do Gabinete</p><h1>Configuracao administrativa</h1><p>Gerencie identidade institucional, equipe, usuarios, parametros, canais, documentos, privacidade e auditoria interna.</p></div></section>
    <section className="admin-tabs segmented-control">
      {sections.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>{label}</button>)}
    </section>
    <section className={wideLayout ? "admin-layout admin-layout-wide" : "admin-layout"}>
      {active === "office" && (
        <OfficeSettings
          data={officeForm}
          users={data.users}
          onChange={setOfficeForm}
          onSubmit={saveOffice}
          error={error}
        />
      )}
      {active === "users" && (
        <UsersSettings
          form={form}
          users={data.users}
          onForm={setForm}
          onSubmit={createUser}
          onUpdate={updateUser}
          error={error}
        />
      )}
      {active === "audit" && (
        <AuditSettings
          items={data.audit}
          pagination={data.auditPagination}
          perPage={auditPerPage}
          onPage={setAuditPage}
          onPerPage={(value) => {
            setAuditPerPage(value);
            setAuditPage(1);
          }}
        />
      )}
      {active === "jurisdiction" && <JurisdictionSettings data={data.jurisdiction} onSaved={load} />}
      {!["office", "users", "audit", "jurisdiction"].includes(active) && <>
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
            <label>Conteudo<textarea required rows="7" value={form.conteudo} onChange={(event) => setForm((current) => ({ ...current, conteudo: event.target.value }))} placeholder="Ola, {{cidadao}}. A solicitacao {{protocolo}} esta com status {{status}}." /></label>
            <small className="template-help">Variaveis permitidas: {"{{cidadao}}"}, {"{{protocolo}}"} e {"{{status}}"}</small>
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

function OfficeSettings({ data, users, onChange, onSubmit, error }) {
  const update = (section, key, value) => onChange({ ...data, [section]: { ...data[section], [key]: value } });
  const chiefOptions = users.filter((user) => user.status === "active" && !["representative", "platform_admin"].includes(user.perfil));
  return (
    <form className="settings-form office-settings-form" onSubmit={onSubmit}>
      <div className="settings-title"><ShieldCheck size={21} /><div><strong>Dados do gabinete</strong><small>Identidade institucional, vereador, mandato e chefe de gabinete.</small></div></div>
      <div className="form-grid">
        <label>Nome parlamentar<input value={data.vereador.nomeParlamentar || ""} onChange={(event) => update("vereador", "nomeParlamentar", event.target.value)} /></label>
        <label>Nome civil<input value={data.vereador.nomeCivil || ""} onChange={(event) => update("vereador", "nomeCivil", event.target.value)} /></label>
        <label>Partido<input value={data.vereador.partido || ""} onChange={(event) => update("vereador", "partido", event.target.value)} /></label>
        <label>E-mail institucional<input type="email" value={data.vereador.email || ""} onChange={(event) => update("vereador", "email", event.target.value)} /></label>
      </div>
      <div className="form-grid">
        <label>Legislatura<input value={data.mandato.legislatura || ""} onChange={(event) => update("mandato", "legislatura", event.target.value)} placeholder="2025-2028" /></label>
        <label>Cargo<input value={data.mandato.cargo || ""} onChange={(event) => update("mandato", "cargo", event.target.value)} placeholder="Vereador" /></label>
        <label>Inicio<input type="date" value={data.mandato.inicio || ""} onChange={(event) => update("mandato", "inicio", event.target.value)} /></label>
        <label>Fim<input type="date" value={data.mandato.fim || ""} onChange={(event) => update("mandato", "fim", event.target.value)} /></label>
      </div>
      <div className="form-grid">
        <label>Cor primaria<input type="color" value={data.identidadeVisual.corPrimaria || "#2563eb"} onChange={(event) => update("identidadeVisual", "corPrimaria", event.target.value)} /></label>
        <label>Cor secundaria<input type="color" value={data.identidadeVisual.corSecundaria || "#0f766e"} onChange={(event) => update("identidadeVisual", "corSecundaria", event.target.value)} /></label>
        <label>URL do logo<input value={data.identidadeVisual.logoUrl || ""} onChange={(event) => update("identidadeVisual", "logoUrl", event.target.value)} /></label>
        <label>Chefe de gabinete<select value={data.chefeGabineteId || ""} onChange={(event) => onChange({ ...data, chefeGabineteId: event.target.value })}><option value="">Nao definido</option>{chiefOptions.map((user) => <option key={user.id} value={user.id}>{user.nome}</option>)}</select></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button compact"><Save size={18} /> Salvar gabinete</button>
    </form>
  );
}

function UsersSettings({ form, users, onForm, onSubmit, onUpdate, error }) {
  return <>
    <form className="settings-form" onSubmit={onSubmit}>
      <div className="settings-title"><Users size={21} /><div><strong>Novo usuario</strong><small>Crie assessores e atribua perfis internos.</small></div></div>
      <label>Nome<input required value={form.nomeUsuario} onChange={(event) => onForm((current) => ({ ...current, nomeUsuario: event.target.value }))} /></label>
      <label>E-mail<input required type="email" value={form.emailUsuario} onChange={(event) => onForm((current) => ({ ...current, emailUsuario: event.target.value }))} /></label>
      <label>Senha inicial<input required type="password" minLength={8} value={form.senhaUsuario} onChange={(event) => onForm((current) => ({ ...current, senhaUsuario: event.target.value }))} /></label>
      <label>Perfil<select value={form.perfilUsuario} onChange={(event) => onForm((current) => ({ ...current, perfilUsuario: event.target.value }))}><option value="admin">Administrador do Gabinete</option><option value="representative">Vereador / Deputado Estadual</option><option value="manager">Gestor</option><option value="staff">Operacional</option></select></label>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button compact"><Plus size={18} /> Criar usuario</button>
    </form>
    <div className="category-list">
      {users.map((user) => <article key={user.id}><span className="entity-icon"><Users size={19} /></span><div><strong>{user.nome}{user.chefeGabinete ? " · Chefe de Gabinete" : ""}</strong><small>{user.email} · {user.perfil} · {user.status}</small></div><select value={user.status} onChange={(event) => onUpdate(user, { status: event.target.value })}><option value="active">active</option><option value="blocked">blocked</option></select></article>)}
    </div>
  </>;
}

function AuditSettings({ items, pagination, perPage, onPage, onPerPage }) {
  return (
    <div className="audit-admin-panel">
      <header className="audit-admin-toolbar">
        <div>
          <strong>Trilha de auditoria interna</strong>
          <span>{pagination.total} registro(s)</span>
        </div>
        <label>Itens por pagina<select value={perPage} onChange={(event) => onPerPage(Number(event.target.value))}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
      </header>
      <div className="audit-admin-table">
        <table>
          <thead>
            <tr>
              <th>Acao</th>
              <th>Entidade</th>
              <th>ID da entidade</th>
              <th>Usuario</th>
              <th>Data e hora</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td><strong>{item.acao}</strong></td>
                <td>{item.entidade}</td>
                <td><code>{item.entidadeId || "-"}</code></td>
                <td><code>{item.usuarioId || "-"}</code></td>
                <td>{new Date(item.criadoEm).toLocaleString("pt-BR")}</td>
              </tr>
            ))}
            {!items.length && (
              <tr><td colSpan="5" className="audit-empty">Nenhum evento encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="audit-admin-pagination">
        <span>Pagina {pagination.page} de {pagination.totalPages}</span>
        <div>
          <button className="secondary-button compact" type="button" disabled={pagination.page <= 1} onClick={() => onPage(pagination.page - 1)}>Anterior</button>
          <button className="secondary-button compact" type="button" disabled={pagination.page >= pagination.totalPages} onClick={() => onPage(pagination.page + 1)}>Proxima</button>
        </div>
      </footer>
    </div>
  );
}

// eslint-disable-next-line no-unused-vars
function LegacyAuditSettings({ items }) {
  return (
    <div className="category-list">
      {items.map((item) => <article key={item.id}><span className="entity-icon"><ShieldCheck size={19} /></span><div><strong>{item.acao}</strong><small>{item.entidade} · {item.entidadeId || "sem entidade"} · {new Date(item.criadoEm).toLocaleString("pt-BR")}</small></div></article>)}
    </div>
  );
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
      <div className="settings-title"><MapPinned size={21} /><div><strong>Jurisdicao territorial</strong><small>Escopo usado por mapa, indicadores e autocomplete.</small></div></div>
      <div className="form-grid">
        <label>Tipo<select value={form.tipoCasa} onChange={(event) => setForm((current) => ({ ...current, tipoCasa: event.target.value }))}><option value="CAMARA_MUNICIPAL">Camara Municipal</option><option value="ASSEMBLEIA_LEGISLATIVA">Assembleia Legislativa</option></select></label>
        <label>UF<input required maxLength="2" value={form.uf} onChange={(event) => setForm((current) => ({ ...current, uf: event.target.value.toUpperCase() }))} /></label>
      </div>
      <label>Nome da jurisdicao<input value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} placeholder="Ex.: Juiz de Fora/MG" /></label>
      <label>Municipio<input value={form.municipio} onChange={(event) => setForm((current) => ({ ...current, municipio: event.target.value }))} /></label>
      <div className="form-grid">
        <label>Codigo IBGE<input value={form.codigoIbge} onChange={(event) => setForm((current) => ({ ...current, codigoIbge: event.target.value.replace(/\D/g, "") }))} placeholder="Ex.: 3136702" /></label>
        <button type="button" className="secondary-button jurisdiction-import-button" disabled={importing || !form.codigoIbge} onClick={importFromIbge}>{importing ? "Carregando malha..." : "Carregar malha do IBGE"}</button>
      </div>
      <div className="form-grid">
        <label>Latitude central<input type="number" step="0.000001" value={form.latitude} onChange={(event) => setForm((current) => ({ ...current, latitude: event.target.value }))} /></label>
        <label>Longitude central<input type="number" step="0.000001" value={form.longitude} onChange={(event) => setForm((current) => ({ ...current, longitude: event.target.value }))} /></label>
        <label>Latitude minima<input required type="number" step="0.000001" value={form.minLatitude} onChange={(event) => setForm((current) => ({ ...current, minLatitude: event.target.value }))} /></label>
        <label>Latitude maxima<input required type="number" step="0.000001" value={form.maxLatitude} onChange={(event) => setForm((current) => ({ ...current, maxLatitude: event.target.value }))} /></label>
        <label>Longitude minima<input required type="number" step="0.000001" value={form.minLongitude} onChange={(event) => setForm((current) => ({ ...current, minLongitude: event.target.value }))} /></label>
        <label>Longitude maxima<input required type="number" step="0.000001" value={form.maxLongitude} onChange={(event) => setForm((current) => ({ ...current, maxLongitude: event.target.value }))} /></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      {data?.geojson && <p className="form-success">Malha oficial carregada para o mapa territorial.</p>}
      <button className="primary-button compact">Salvar jurisdicao</button>
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

function normalizeOffice(data) {
  return {
    vereador: data?.vereador || {},
    mandato: data?.mandato || {},
    identidadeVisual: data?.identidadeVisual || {},
    chefeGabineteId: data?.chefeGabineteId || "",
  };
}
