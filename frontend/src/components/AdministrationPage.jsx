import {
  Building2,
  Clock3,
  ExternalLink,
  FileText,
  MapPinned,
  PlugZap,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  UserCheck,
  UserX,
  Users,
  X,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const sections = [
  ["office", "Gabinete"],
  ["parliamentarian", "Parlamentar"],
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
  dadosInstitucionais: {},
  redesSociais: {},
  identidadeVisual: {},
  chefeGabineteId: "",
};

const emptyParliamentarian = {
  nomeCompleto: "",
  nomeParlamentar: "",
  fotografiaUrl: "",
  partidoId: "",
  partido: "",
  partidoNome: "",
  partidoNumero: "",
  partidoLogoUrl: "",
  partidoFonteUrl: "",
  coligacaoFederacao: "",
  email: "",
  telefoneInstitucional: "",
  biografia: "",
  areasPrioritarias: [],
  redesSociais: {},
  statusMandato: "ATIVO",
  mandatos: [],
  insightsOficiais: {},
};

const userRoleLabels = {
  admin: "Administrador do Gabinete",
  representative: "Vereador / Deputado Estadual",
  manager: "Gestor",
  staff: "Operacional",
};

const userStatusLabels = {
  active: "Ativo",
  blocked: "Bloqueado",
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
    parliamentarian: emptyParliamentarian,
    users: [],
    parties: [],
    audit: [],
    auditPagination: { page: 1, perPage: 10, total: 0, totalPages: 1 },
  });
  const [form, setForm] = useState(initialForm);
  const [officeForm, setOfficeForm] = useState(emptyOffice);
  const [parliamentarianForm, setParliamentarianForm] = useState(emptyParliamentarian);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [categories, territories, agencies, templates, jurisdiction, integrations, office, parliamentarian, users, parties, audit] =
      await Promise.all([
        apiRequest("/api/v1/admin/categorias"),
        apiRequest("/api/v1/admin/territorios"),
        apiRequest("/api/v1/admin/orgaos"),
        apiRequest("/api/v1/admin/templates-resposta"),
        apiRequest("/api/v1/admin/jurisdicao"),
        apiRequest("/api/v1/admin/integracoes"),
        apiRequest("/api/v1/admin/perfil-gabinete"),
        apiRequest("/api/v1/admin/parlamentar"),
        apiRequest("/api/v1/admin/usuarios"),
        apiRequest("/api/v1/admin/partidos"),
        apiRequest(`/api/v1/admin/auditoria?page=${auditPage}&perPage=${auditPerPage}`),
      ]);
    const mappedOffice = normalizeOffice(office);
    const mappedParliamentarian = normalizeParliamentarian(parliamentarian);
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
      parliamentarian: mappedParliamentarian,
      users: users.content,
      parties: parties.content,
      audit: audit.content,
      auditPagination: {
        page: audit.page,
        perPage: audit.perPage,
        total: audit.total,
        totalPages: audit.totalPages,
      },
    });
    setOfficeForm(mappedOffice);
    setParliamentarianForm(mappedParliamentarian);
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
      const officePayload = {
        ...officeForm,
        identidadeVisual: {
          ...officeForm.identidadeVisual,
          dadosInstitucionais: officeForm.dadosInstitucionais,
          redesSociais: officeForm.redesSociais,
        },
      };
      await apiRequest("/api/v1/admin/perfil-gabinete", {
        method: "PATCH",
        body: JSON.stringify(officePayload),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function saveParliamentarian(event) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/v1/admin/parlamentar", {
        method: "PATCH",
        body: JSON.stringify(parliamentarianForm),
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
    setError("");
    try {
      await apiRequest(`/api/v1/admin/usuarios/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const labels = {
    categories: ["Nova categoria", "O SLA sera aplicado a solicitacao.", Clock3],
    territories: ["Novo territorio", "Organize as demandas por bairro ou regiao.", MapPinned],
    agencies: ["Novo orgao", "Cadastre os destinatarios dos encaminhamentos.", Building2],
    templates: ["Novo template", "Use somente as variaveis seguras indicadas.", FileText],
    integrations: ["Nova integracao", "Configure canais e sistemas externos autorizados.", PlugZap],
  };
  const [title, description, Icon] = labels[active] || [];
  const wideLayout = ["audit", "office", "parliamentarian", "jurisdiction"].includes(active);

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
      {active === "parliamentarian" && (
        <ParliamentarianSettings
          data={parliamentarianForm}
          parties={data.parties}
          onChange={setParliamentarianForm}
          onSubmit={saveParliamentarian}
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
      {!["office", "parliamentarian", "users", "audit", "jurisdiction"].includes(active) && <>
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
  const institutional = data.dadosInstitucionais || {};
  const social = data.redesSociais || {};
  const chiefOptions = users.filter((user) => user.status === "active" && !["representative", "platform_admin"].includes(user.perfil));
  return (
    <form className="settings-form office-settings-form" onSubmit={onSubmit}>
      <div className="settings-title"><ShieldCheck size={21} /><div><strong>Dados do gabinete</strong><small>Identidade institucional, canais oficiais, redes sociais, logotipo e chefia administrativa.</small></div></div>
      <div className="form-grid">
        <label>Nome do gabinete<input value={institutional.nomeGabinete || ""} onChange={(event) => update("dadosInstitucionais", "nomeGabinete", event.target.value)} /></label>
        <label>Câmara Municipal<input value={institutional.camaraMunicipal || ""} onChange={(event) => update("dadosInstitucionais", "camaraMunicipal", event.target.value)} /></label>
        <label>Município<input value={institutional.municipio || ""} onChange={(event) => update("dadosInstitucionais", "municipio", event.target.value)} /></label>
        <label>Estado<input maxLength="2" value={institutional.estado || ""} onChange={(event) => update("dadosInstitucionais", "estado", event.target.value.toUpperCase())} /></label>
      </div>
      <div className="form-grid">
        <label>Endereço institucional<input value={institutional.enderecoInstitucional || ""} onChange={(event) => update("dadosInstitucionais", "enderecoInstitucional", event.target.value)} /></label>
        <label>Telefone<input value={institutional.telefone || ""} onChange={(event) => update("dadosInstitucionais", "telefone", event.target.value)} /></label>
        <label>E-mail oficial<input type="email" value={institutional.emailOficial || ""} onChange={(event) => update("dadosInstitucionais", "emailOficial", event.target.value)} /></label>
        <label>Horário de atendimento<input value={institutional.horarioAtendimento || ""} onChange={(event) => update("dadosInstitucionais", "horarioAtendimento", event.target.value)} placeholder="Segunda a sexta, 8h às 17h" /></label>
      </div>
      <div className="form-grid">
        <label>Site<input value={institutional.site || ""} onChange={(event) => update("dadosInstitucionais", "site", event.target.value)} /></label>
        <label>Instagram<input value={social.instagram || ""} onChange={(event) => update("redesSociais", "instagram", event.target.value)} /></label>
        <label>Facebook<input value={social.facebook || ""} onChange={(event) => update("redesSociais", "facebook", event.target.value)} /></label>
        <label>YouTube<input value={social.youtube || ""} onChange={(event) => update("redesSociais", "youtube", event.target.value)} /></label>
      </div>
      <div className="form-grid">
        <label>Logotipo URL<input value={data.identidadeVisual.logoUrl || ""} onChange={(event) => update("identidadeVisual", "logoUrl", event.target.value)} /></label>
        <label>Cor primária<input type="color" value={data.identidadeVisual.corPrimaria || "#2563eb"} onChange={(event) => update("identidadeVisual", "corPrimaria", event.target.value)} /></label>
        <label>Cor secundária<input type="color" value={data.identidadeVisual.corSecundaria || "#0f766e"} onChange={(event) => update("identidadeVisual", "corSecundaria", event.target.value)} /></label>
        <label>Chefe de gabinete<select value={data.chefeGabineteId || ""} onChange={(event) => onChange({ ...data, chefeGabineteId: event.target.value })}><option value="">Não definido</option>{chiefOptions.map((user) => <option key={user.id} value={user.id}>{user.nome}</option>)}</select></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button compact"><Save size={18} /> Salvar gabinete</button>
    </form>
  );
}

function ParliamentarianSettings({ data, parties, onChange, onSubmit, error }) {
  const [insights, setInsights] = useState(data.insightsOficiais || null);
  const selectedParty = parties.find((party) => (
    party.id === data.partidoId || party.sigla === data.partido
  ));
  const update = (key, value) => onChange({ ...data, [key]: value });
  const updateParty = (party) => onChange({
    ...data,
    partidoId: party?.id || "",
    partido: party?.sigla || "",
    partidoNome: party?.nome || "",
    partidoNumero: party?.numero || "",
    partidoLogoUrl: party?.logoUrl || "",
    partidoFonteUrl: party?.fonteUrl || "",
  });
  const social = data.redesSociais || {};

  function updateSocial(key, value) {
    update("redesSociais", { ...social, [key]: value });
  }

  function updateMandate(index, key, value) {
    const mandates = [...(data.mandatos || [])];
    mandates[index] = { ...mandates[index], [key]: value };
    update("mandatos", mandates);
  }

  function addMandate() {
    update("mandatos", [
      ...(data.mandatos || []),
      { legislatura: "", cargo: "Vereador", inicio: "", fim: "", votos: "", status: "HISTORICO" },
    ]);
  }

  function removeMandate(index) {
    update("mandatos", (data.mandatos || []).filter((_, current) => current !== index));
  }

  async function requestInsights() {
    const result = await apiRequest("/api/v1/admin/parlamentar/insights-oficiais", {
      method: "POST",
      body: JSON.stringify({ nome: data.nomeParlamentar || data.nomeCompleto }),
    });
    setInsights(result);
  }

  return (
    <div className="parliamentarian-admin-panel">
      <form className="settings-form parliamentarian-form" onSubmit={onSubmit}>
        <div className="settings-title"><Users size={21} /><div><strong>Cadastro do parlamentar</strong><small>Dados do titular, partido, contato, redes, prioridades e historico de mandatos.</small></div></div>
        <div className="form-grid">
          <label>Nome completo<input value={data.nomeCompleto || ""} onChange={(event) => update("nomeCompleto", event.target.value)} /></label>
          <label>Nome parlamentar<input value={data.nomeParlamentar || ""} onChange={(event) => update("nomeParlamentar", event.target.value)} /></label>
          <label>Fotografia URL<input value={data.fotografiaUrl || ""} onChange={(event) => update("fotografiaUrl", event.target.value)} placeholder="https://..." /></label>
          <PartySearchSelect parties={parties} value={selectedParty} onChange={updateParty} />
        </div>
        <div className="form-grid">
          <label>Coligacao ou federacao<input value={data.coligacaoFederacao || ""} onChange={(event) => update("coligacaoFederacao", event.target.value)} /></label>
          <label>E-mail<input type="email" value={data.email || ""} onChange={(event) => update("email", event.target.value)} /></label>
          <label>Telefone institucional<input value={data.telefoneInstitucional || ""} onChange={(event) => update("telefoneInstitucional", event.target.value)} /></label>
          <label>Status no mandato<select value={data.statusMandato || "ATIVO"} onChange={(event) => update("statusMandato", event.target.value)}><option value="ATIVO">Ativo</option><option value="LICENCIADO">Licenciado</option><option value="SUPLENTE">Suplente</option><option value="ENCERRADO">Encerrado</option></select></label>
        </div>
        <label>Biografia resumida<textarea rows="5" value={data.biografia || ""} onChange={(event) => update("biografia", event.target.value)} /></label>
        <label>Areas prioritarias<input value={(data.areasPrioritarias || []).join(", ")} onChange={(event) => update("areasPrioritarias", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="Saude, educacao, infraestrutura" /></label>
        <div className="form-grid">
          <label>Instagram<input value={social.instagram || ""} onChange={(event) => updateSocial("instagram", event.target.value)} /></label>
          <label>Facebook<input value={social.facebook || ""} onChange={(event) => updateSocial("facebook", event.target.value)} /></label>
          <label>X / Twitter<input value={social.twitter || ""} onChange={(event) => updateSocial("twitter", event.target.value)} /></label>
          <label>Site<input value={social.site || ""} onChange={(event) => updateSocial("site", event.target.value)} /></label>
        </div>

        <section className="mandate-history">
          <header>
            <div><strong>Legislaturas e mandatos</strong><small>Mantenha o mandato atual e historico de mandatos anteriores, incluindo votos recebidos.</small></div>
            <button type="button" className="secondary-button compact" onClick={addMandate}><Plus size={17} /> Adicionar mandato</button>
          </header>
          {(data.mandatos || []).map((mandate, index) => (
            <article key={`${index}-${mandate.legislatura || "mandato"}`} className="mandate-row">
              <label>Legislatura<input value={mandate.legislatura || ""} onChange={(event) => updateMandate(index, "legislatura", event.target.value)} placeholder="2025-2028" /></label>
              <label>Cargo<input value={mandate.cargo || ""} onChange={(event) => updateMandate(index, "cargo", event.target.value)} /></label>
              <label>Inicio<input type="date" value={mandate.inicio || ""} onChange={(event) => updateMandate(index, "inicio", event.target.value)} /></label>
              <label>Fim<input type="date" value={mandate.fim || ""} onChange={(event) => updateMandate(index, "fim", event.target.value)} /></label>
              <label>Votos<input type="number" min="0" value={mandate.votos || ""} onChange={(event) => updateMandate(index, "votos", event.target.value)} /></label>
              <label>Status<select value={mandate.status || "HISTORICO"} onChange={(event) => updateMandate(index, "status", event.target.value)}><option value="ATUAL">Atual</option><option value="HISTORICO">Historico</option><option value="ENCERRADO">Encerrado</option></select></label>
              <button type="button" className="icon-button" title="Remover mandato" onClick={() => removeMandate(index)}><Trash2 size={17} /></button>
            </article>
          ))}
          {!data.mandatos?.length && <p className="table-message">Nenhum mandato cadastrado.</p>}
        </section>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button compact"><Save size={18} /> Salvar parlamentar</button>
      </form>

      <section className="official-insights-panel">
        <div className="settings-title"><Sparkles size={21} /><div><strong>Agente de dados oficiais</strong><small>Use fontes oficiais como TSE e TRE para apoiar conferencias e insights.</small></div></div>
        <button type="button" className="secondary-button compact" onClick={requestInsights}><Sparkles size={17} /> Buscar fontes oficiais</button>
        {insights?.fontes?.map((source) => (
          <a key={source.nome} href={source.url} target="_blank" rel="noreferrer">
            <ExternalLink size={16} />
            <span><strong>{source.nome}</strong><small>{source.uso}</small></span>
          </a>
        ))}
        {insights?.insightsSugeridos?.length > 0 && (
          <ul>{insights.insightsSugeridos.map((item) => <li key={item}>{item}</li>)}</ul>
        )}
      </section>
    </div>
  );
}

function PartySearchSelect({ parties, value, onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const normalized = query.trim().toLowerCase();
  const visible = parties.filter((party) => {
    if (!normalized) return true;
    return (
      party.sigla.toLowerCase().includes(normalized) ||
      party.nome.toLowerCase().includes(normalized) ||
      String(party.numero).includes(normalized)
    );
  }).slice(0, 12);

  function choose(party) {
    onChange(party);
    setQuery("");
    setOpen(false);
  }

  return (
    <label className="party-search-select" onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      Partido
      <div className={`search-select-control ${open ? "is-open" : ""}`}>
        <PartyMark party={value} />
        <input
          value={open ? query : partyLabel(value)}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          placeholder="Busque por sigla, nome ou número"
          autoComplete="off"
        />
        {value && (
          <button
            type="button"
            className="search-select-toggle"
            aria-label="Limpar partido"
            onClick={() => onChange(null)}
          >
            ×
          </button>
        )}
      </div>
      {open && (
        <div className="search-select-menu party-search-menu" role="listbox">
          {visible.map((party) => (
            <button key={party.id} type="button" role="option" onMouseDown={(event) => event.preventDefault()} onClick={() => choose(party)}>
              <PartyMark party={party} />
              <span>
                <strong>{party.sigla} · {party.numero}</strong>
                <small>{party.nome}</small>
              </span>
            </button>
          ))}
          {!visible.length && <p>Nenhum partido encontrado.</p>}
        </div>
      )}
    </label>
  );
}

function PartyMark({ party }) {
  if (party?.logoUrl) {
    return <img className="party-logo" src={party.logoUrl} alt={`Logo ${party.sigla}`} />;
  }
  return <span className="party-logo-fallback">{party?.sigla?.slice(0, 3) || "?"}</span>;
}

function partyLabel(party) {
  if (!party) return "";
  return `${party.sigla} · ${party.numero} · ${party.nome}`;
}

function UsersSettings({ form, users, onForm, onSubmit, onUpdate, error }) {
  const [selectedUserId, setSelectedUserId] = useState("");
  const [editForm, setEditForm] = useState({
    nome: "",
    email: "",
    perfil: "staff",
    status: "active",
    senha: "",
  });
  const selectedUser = users.find((user) => user.id === selectedUserId);

  useEffect(() => {
    if (!selectedUser) {
      if (selectedUserId) setSelectedUserId("");
      return;
    }
    setEditForm((current) => ({
      nome: selectedUser.nome,
      email: selectedUser.email,
      perfil: selectedUser.perfil,
      status: selectedUser.status,
      senha: current.senha,
    }));
  }, [selectedUser, selectedUserId]);

  function selectUser(user) {
    setSelectedUserId(user.id);
    setEditForm({
      nome: user.nome,
      email: user.email,
      perfil: user.perfil,
      status: user.status,
      senha: "",
    });
  }

  async function saveUser(event) {
    event.preventDefault();
    if (!selectedUser) return;
    const patch = {
      nome: editForm.nome,
      email: editForm.email,
      perfil: editForm.perfil,
      status: editForm.status,
    };
    if (editForm.senha) patch.senha = editForm.senha;
    await onUpdate(selectedUser, patch);
    setEditForm((current) => ({ ...current, senha: "" }));
  }

  async function changeStatus(event, user, status) {
    event.stopPropagation();
    if (user.status === status) return;
    await onUpdate(user, { status });
  }

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

    {selectedUser && (
      <form className="settings-form user-edit-form" onSubmit={saveUser}>
        <div className="settings-title">
          <Users size={21} />
          <div><strong>Editar usuario</strong><small>Atualize dados, perfil, senha opcional e status de acesso.</small></div>
        </div>
        <div className="form-grid">
          <label>Nome<input required value={editForm.nome} onChange={(event) => setEditForm((current) => ({ ...current, nome: event.target.value }))} /></label>
          <label>E-mail<input required type="email" value={editForm.email} onChange={(event) => setEditForm((current) => ({ ...current, email: event.target.value }))} /></label>
        </div>
        <div className="form-grid">
          <label>Perfil<select value={editForm.perfil} onChange={(event) => setEditForm((current) => ({ ...current, perfil: event.target.value }))}><option value="admin">Administrador do Gabinete</option><option value="representative">Vereador / Deputado Estadual</option><option value="manager">Gestor</option><option value="staff">Operacional</option></select></label>
          <label>Nova senha<input type="password" minLength={8} value={editForm.senha} onChange={(event) => setEditForm((current) => ({ ...current, senha: event.target.value }))} placeholder="Manter senha atual" /></label>
        </div>
        <UserStatusSwitch
          checked={editForm.status === "active"}
          onChange={(checked) => setEditForm((current) => ({ ...current, status: checked ? "active" : "blocked" }))}
          label="Acesso do usuario"
        />
        <div className="form-actions">
          <button className="primary-button compact"><Save size={18} /> Salvar usuario</button>
          <button type="button" className="secondary-button compact" onClick={() => setSelectedUserId("")}><X size={18} /> Fechar</button>
        </div>
      </form>
    )}

    <div className="category-list user-card-list">
      {users.map((user) => (
        <article
          key={user.id}
          className={selectedUserId === user.id ? "user-card active" : "user-card"}
          role="button"
          tabIndex={0}
          onClick={() => selectUser(user)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              selectUser(user);
            }
          }}
        >
          <span className="entity-icon"><Users size={19} /></span>
          <div>
            <strong>{user.nome}{user.chefeGabinete ? " · Chefe de Gabinete" : ""}</strong>
            <small>{user.email} · {userRoleLabels[user.perfil] || user.perfil} · {userStatusLabels[user.status] || user.status}</small>
          </div>
          <UserStatusSwitch
            checked={user.status === "active"}
            onChange={(checked, event) => changeStatus(event, user, checked ? "active" : "blocked")}
            compact
            label={`Acesso de ${user.nome}`}
          />
        </article>
      ))}
    </div>
  </>;
}

function UserStatusSwitch({ checked, onChange, label, compact = false }) {
  return (
    <button
      type="button"
      className={checked ? "user-status-switch is-on" : "user-status-switch"}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={checked ? "Desativar acesso" : "Ativar acesso"}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked, event);
      }}
    >
      <span className="switch-track" aria-hidden="true">
        <span className="switch-thumb">{checked ? <UserCheck size={13} /> : <UserX size={13} />}</span>
      </span>
      <span className={compact ? "switch-label compact" : "switch-label"}>
        {checked ? "Ativo" : "Bloqueado"}
      </span>
    </button>
  );
}

// Legacy kept only to avoid touching a mojibake-heavy block during this scoped UX change.
// eslint-disable-next-line no-unused-vars
function LegacyUsersSettings({ form, users, onForm, onSubmit, onUpdate, error }) {
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
  const visual = data?.identidadeVisual || {};
  return {
    dadosInstitucionais: data?.dadosInstitucionais || visual.dadosInstitucionais || {},
    redesSociais: data?.redesSociais || visual.redesSociais || {},
    identidadeVisual: visual,
    chefeGabineteId: data?.chefeGabineteId || "",
  };
}

function normalizeParliamentarian(data) {
  return {
    ...emptyParliamentarian,
    ...(data || {}),
    areasPrioritarias: Array.isArray(data?.areasPrioritarias) ? data.areasPrioritarias : [],
    redesSociais: data?.redesSociais || {},
    mandatos: Array.isArray(data?.mandatos) ? data.mandatos : [],
    insightsOficiais: data?.insightsOficiais || {},
  };
}
