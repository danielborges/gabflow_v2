import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Building2,
  Clock3,
  Eye,
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
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api";
import {
  formatBrazilianCpf,
  formatBrazilianPhone,
  isValidBrazilianCpf,
  isValidBrazilianPhone,
  isValidEmail,
  isValidWebsiteUrl,
  normalizeWebsiteUrl,
} from "../contactValidation";
import brazilLocations from "../data/brazilLocations.json";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

const brazilStates = brazilLocations.states;
const municipalitiesByState = brazilLocations.municipalitiesByState;

const sections = [
  ["office", "Gabinete"],
  ["parliamentarian", "Parlamentar"],
  ["users", "Usuários"],
  ["categories", "Categorias"],
  ["territories", "Territórios"],
  ["agencies", "Órgãos"],
  ["templates", "Templates"],
  ["integrations", "Integrações"],
  ["audit", "Auditoria"],
];

const initialForm = {
  nome: "",
  slaHoras: 72,
  emailContato: "",
  responsavelOrgao: "",
  telefoneOrgao: "",
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
  cpfUsuario: "",
  telefoneUsuario: "",
  senhaUsuario: "",
  perfilUsuario: "staff",
};

const emptyOffice = {
  dadosInstitucionais: {},
  redesSociais: {},
  identidadeVisual: {},
  chefeGabineteId: "",
  contrato: { plano: "starter", limiteUsuarios: 5, usuariosAtivos: 0 },
};

const emptyParliamentarian = {
  nomeCompleto: "",
  nomeParlamentar: "",
  cpf: "",
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
  dadosOficiais: "",
  areasPrioritarias: [],
  redesSociais: {},
  statusMandato: "ATIVO",
  mandatos: [],
  insightsOficiais: {},
  arquivosCampanha: [],
};

const userRoleLabels = {
  admin: "Administrador",
  representative: "Parlamentar",
  staff: "Operacional",
};

const userRoleOptions = [
  ["admin", "Administrador"],
  ["representative", "Parlamentar"],
  ["staff", "Operacional"],
];

const commercialPlanLabels = {
  starter: "Starter",
  professional: "Professional",
  premium: "Premium",
};

const defaultOfficeHours = {
  days: ["seg", "ter", "qua", "qui", "sex"],
  start: "08:00",
  end: "17:00",
};

const weekdays = [
  ["seg", "Seg"],
  ["ter", "Ter"],
  ["qua", "Qua"],
  ["qui", "Qui"],
  ["sex", "Sex"],
  ["sab", "Sab"],
  ["dom", "Dom"],
];

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
  const [officeJurisdictionForm, setOfficeJurisdictionForm] = useState(() => jurisdictionForm(null));
  const [parliamentarianForm, setParliamentarianForm] = useState(emptyParliamentarian);
  const [error, setError] = useState({ section: "", message: "" });
  const [success, setSuccess] = useState({ section: "", message: "" });

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
    setOfficeJurisdictionForm(jurisdictionForm(jurisdiction));
    setParliamentarianForm(mappedParliamentarian);
  }, [auditPage, auditPerPage]);

  useEffect(() => { load(); }, [load]);

  function clearError(section = active) {
    setError({ section, message: "" });
  }

  function showSuccess(section, message) {
    setSuccess({ section, message });
  }

  function clearSuccess(section = active) {
    setSuccess((current) => (current.section === section ? { section, message: "" } : current));
  }

  function showError(section, message) {
    setError({ section, message });
  }

  function sectionError(section) {
    return error.section === section ? error.message : "";
  }

  function sectionSuccess(section) {
    return success.section === section ? success.message : "";
  }

  async function submit(event) {
    event.preventDefault();
    const section = active;
    clearError(section);
    const paths = {
      categories: "/api/v1/admin/categorias",
      territories: "/api/v1/admin/territorios",
      agencies: "/api/v1/admin/orgaos",
      templates: "/api/v1/admin/templates-resposta",
      integrations: "/api/v1/admin/integracoes",
    };
    const payload = { nome: form.nome };
    if (section === "categories") payload.slaHoras = Number(form.slaHoras);
    if (section === "agencies") payload.emailContato = form.emailContato;
    if (section === "templates") {
      Object.assign(payload, {
        canal: form.canal,
        categoriaId: form.categoriaId || null,
        assunto: form.assunto || null,
        conteudo: form.conteudo,
      });
    }
    if (section === "integrations") {
      Object.assign(payload, {
        tipo: form.tipoIntegracao,
        status: form.statusIntegracao,
        configuracao: integrationConfig(form.configuracao, form.segredo),
      });
    }
    try {
      await apiRequest(paths[section], { method: "POST", body: JSON.stringify(payload) });
      setForm(initialForm);
      await load();
      showSuccess(section, "Registro adicionado com sucesso.");
    } catch (requestError) {
      showError(section, requestError.message);
    }
  }

  async function saveOffice(event) {
    event.preventDefault();
    clearError("office");
    try {
      const officePayload = {
        ...officeForm,
        redesSociais: {},
        identidadeVisual: {
          ...officeForm.identidadeVisual,
          dadosInstitucionais: officeForm.dadosInstitucionais,
          redesSociais: {},
        },
      };
      await apiRequest("/api/v1/admin/perfil-gabinete", {
        method: "PATCH",
        body: JSON.stringify(officePayload),
      });
      await load();
      showSuccess("office", "Gabinete salvo com sucesso.");
    } catch (requestError) {
      showError("office", requestError.message);
    }
  }

  async function saveParliamentarian(event) {
    event.preventDefault();
    clearError("parliamentarian");
    try {
      await apiRequest("/api/v1/admin/parlamentar", {
        method: "PATCH",
        body: JSON.stringify(parliamentarianForm),
      });
      await load();
      showSuccess("parliamentarian", "Parlamentar salvo com sucesso.");
      return true;
    } catch (requestError) {
      showError("parliamentarian", requestError.message);
      return false;
    }
  }

  async function createUser(event) {
    event.preventDefault();
    clearError("users");
    try {
      await apiRequest("/api/v1/admin/usuarios", {
        method: "POST",
        body: JSON.stringify({
          nome: form.nomeUsuario,
          email: form.emailUsuario,
          cpf: form.cpfUsuario,
          telefone: form.telefoneUsuario,
          senha: form.senhaUsuario,
          perfil: form.perfilUsuario,
        }),
      });
      setForm((current) => ({
        ...current,
        nomeUsuario: "",
        emailUsuario: "",
        cpfUsuario: "",
        telefoneUsuario: "",
        senhaUsuario: "",
      }));
      await load();
      showSuccess("users", "Usuário criado com sucesso.");
    } catch (requestError) {
      showError("users", requestError.message);
    }
  }

  async function updateUser(user, patch) {
    clearError("users");
    try {
      await apiRequest(`/api/v1/admin/usuarios/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await load();
      showSuccess("users", "Usuário atualizado com sucesso.");
    } catch (requestError) {
      showError("users", requestError.message);
    }
  }

  async function createTerritory(event) {
    event.preventDefault();
    clearError("territories");
    try {
      await apiRequest("/api/v1/admin/territorios", {
        method: "POST",
        body: JSON.stringify({ nome: form.nome }),
      });
      setForm((current) => ({ ...current, nome: "" }));
      await load();
      showSuccess("territories", "Território adicionado com sucesso.");
    } catch (requestError) {
      showError("territories", requestError.message);
    }
  }

  async function updateTerritory(territory, patch) {
    clearError("territories");
    try {
      await apiRequest(`/api/v1/admin/territorios/${territory.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await load();
      showSuccess("territories", "Território atualizado com sucesso.");
    } catch (requestError) {
      showError("territories", requestError.message);
    }
  }

  async function deleteTerritory(territory) {
    clearError("territories");
    try {
      await apiRequest(`/api/v1/admin/territorios/${territory.id}`, { method: "DELETE" });
      await load();
      showSuccess("territories", "Território desativado com sucesso.");
    } catch (requestError) {
      showError("territories", requestError.message);
    }
  }

  async function reloadTerritorySuggestions() {
    clearError("territories");
    try {
      await apiRequest("/api/v1/admin/territorios/recarregar-sugestoes", { method: "POST" });
      await load();
      showSuccess("territories", "Sugestões de territórios recarregadas com sucesso.");
    } catch (requestError) {
      showError("territories", requestError.message);
    }
  }

  async function createAgency(event) {
    event.preventDefault();
    clearError("agencies");
    try {
      await apiRequest("/api/v1/admin/orgaos", {
        method: "POST",
        body: JSON.stringify({
          nome: form.nome,
          emailContato: form.emailContato,
          responsavel: form.responsavelOrgao,
          telefone: form.telefoneOrgao,
        }),
      });
      setForm((current) => ({
        ...current,
        nome: "",
        emailContato: "",
        responsavelOrgao: "",
        telefoneOrgao: "",
      }));
      await load();
      showSuccess("agencies", "Órgão adicionado com sucesso.");
    } catch (requestError) {
      showError("agencies", requestError.message);
    }
  }

  async function updateAgency(agency, patch) {
    clearError("agencies");
    try {
      await apiRequest(`/api/v1/admin/orgaos/${agency.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await load();
      showSuccess("agencies", "Órgão atualizado com sucesso.");
    } catch (requestError) {
      showError("agencies", requestError.message);
    }
  }

  async function deleteAgency(agency) {
    clearError("agencies");
    try {
      await apiRequest(`/api/v1/admin/orgaos/${agency.id}`, { method: "DELETE" });
      await load();
      showSuccess("agencies", "Órgão desativado com sucesso.");
    } catch (requestError) {
      showError("agencies", requestError.message);
    }
  }

  async function reloadAgencySuggestions() {
    clearError("agencies");
    try {
      await apiRequest("/api/v1/admin/orgaos/recarregar-sugestoes", { method: "POST" });
      await load();
      showSuccess("agencies", "Sugestões de órgãos recarregadas com sucesso.");
    } catch (requestError) {
      showError("agencies", requestError.message);
    }
  }

  async function createTemplate(event) {
    event.preventDefault();
    clearError("templates");
    try {
      await apiRequest("/api/v1/admin/templates-resposta", {
        method: "POST",
        body: JSON.stringify({
          nome: form.nome,
          canal: form.canal,
          categoriaId: form.categoriaId || null,
          assunto: form.assunto || null,
          conteudo: form.conteudo,
        }),
      });
      setForm((current) => ({
        ...current,
        nome: "",
        categoriaId: "",
        assunto: "",
        conteudo: "",
      }));
      await load();
      showSuccess("templates", "Template adicionado com sucesso.");
    } catch (requestError) {
      showError("templates", requestError.message);
    }
  }

  async function updateTemplate(template, patch) {
    clearError("templates");
    try {
      await apiRequest(`/api/v1/admin/templates-resposta/${template.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await load();
      showSuccess("templates", "Template atualizado com sucesso.");
    } catch (requestError) {
      showError("templates", requestError.message);
    }
  }

  async function deleteTemplate(template) {
    clearError("templates");
    try {
      await apiRequest(`/api/v1/admin/templates-resposta/${template.id}`, { method: "DELETE" });
      await load();
      showSuccess("templates", "Template desativado com sucesso.");
    } catch (requestError) {
      showError("templates", requestError.message);
    }
  }

  const labels = {
    categories: ["Nova categoria", "O SLA será aplicado à solicitação.", Clock3],
    territories: ["Novo território", "Organize as demandas por bairro ou região.", MapPinned],
    agencies: ["Novo órgão", "Cadastre os destinatários dos encaminhamentos.", Building2],
    templates: ["Novo template", "Use somente as variáveis seguras indicadas.", FileText],
    integrations: ["Nova integração", "Configure canais e sistemas externos autorizados.", PlugZap],
  };
  const [title, description, Icon] = labels[active] || [];
  const wideLayout = ["audit", "office", "parliamentarian"].includes(active);

  return <>
    <section className="page-heading"><div><p className="eyebrow">Administrador do Gabinete</p><h1>Configuração administrativa</h1><p>Gerencie identidade institucional, equipe, usuários, parâmetros, canais, documentos, privacidade e auditoria interna.</p></div></section>
    <section className="admin-tabs segmented-control">
      {sections.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => { setActive(id); clearError(id); clearSuccess(id); }}>{label}</button>)}
    </section>
    <section className={wideLayout ? "admin-layout admin-layout-wide admin-tab-panel" : "admin-layout admin-tab-panel"}>
      {sectionSuccess(active) && <p className="form-success admin-section-success">{sectionSuccess(active)}</p>}
      {active === "office" && (
        <OfficeSettings
          data={officeForm}
          jurisdictionForm={officeJurisdictionForm}
          users={data.users}
          jurisdiction={data.jurisdiction}
          onChange={setOfficeForm}
          onJurisdictionChange={setOfficeJurisdictionForm}
          onSaved={load}
          onSubmit={saveOffice}
          error={sectionError("office")}
        />
      )}
      {active === "parliamentarian" && (
        <ParliamentarianSettings
          data={parliamentarianForm}
          parties={data.parties}
          jurisdiction={data.jurisdiction}
          onChange={setParliamentarianForm}
          onSubmit={saveParliamentarian}
          error={sectionError("parliamentarian")}
        />
      )}
      {active === "users" && (
        <UsersSettings
          form={form}
          users={data.users}
          contract={data.office.contrato}
          onForm={setForm}
          onSubmit={createUser}
          onUpdate={updateUser}
          error={sectionError("users")}
        />
      )}
      {active === "territories" && (
        <TerritoriesSettings
          form={form}
          territories={data.territories}
          jurisdiction={data.jurisdiction}
          onForm={setForm}
          onSubmit={createTerritory}
          onUpdate={updateTerritory}
          onDelete={deleteTerritory}
          onReload={reloadTerritorySuggestions}
          error={sectionError("territories")}
        />
      )}
      {active === "agencies" && (
        <AgenciesSettings
          form={form}
          agencies={data.agencies}
          jurisdiction={data.jurisdiction}
          onForm={setForm}
          onSubmit={createAgency}
          onUpdate={updateAgency}
          onDelete={deleteAgency}
          onReload={reloadAgencySuggestions}
          error={sectionError("agencies")}
        />
      )}
      {active === "templates" && (
        <TemplatesSettings
          form={form}
          templates={data.templates}
          categories={data.categories}
          onForm={setForm}
          onSubmit={createTemplate}
          onUpdate={updateTemplate}
          onDelete={deleteTemplate}
          error={sectionError("templates")}
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
      {!["office", "parliamentarian", "users", "territories", "agencies", "templates", "audit"].includes(active) && <>
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
                <option value="FORMULARIO_PUBLICO">Formulário público</option>
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
            <label>Configuração pública<textarea rows="4" value={form.configuracao} onChange={(event) => setForm((current) => ({ ...current, configuracao: event.target.value }))} placeholder="numero=+5532999999999&#10;webhook=https://..." /></label>
            <label>Token ou segredo<input value={form.segredo} onChange={(event) => setForm((current) => ({ ...current, segredo: event.target.value }))} /></label>
          </>}
          {sectionError(active) && <p className="form-error">{sectionError(active)}</p>}
          <div className="form-actions"><button className="primary-button compact"><Plus size={18} /> Adicionar</button></div>
        </form>
        <div className="category-list">
          {data[active].map((item) => <article key={item.id}><span className="entity-icon"><Icon size={19} /></span><div><strong>{item.nome}</strong><small>{active === "templates" ? `${item.canal} · ${item.categoria || "Todas as categorias"} · v${item.versao}` : item.emailContato || (item.ativa ? "Ativo" : "Inativo")}</small></div>{active === "categories" && <span>{item.slaHoras}h</span>}</article>)}
        </div>
      </>}
    </section>
  </>;
}

function OfficeSettings({
  data,
  jurisdictionForm: jurisdictionData,
  users,
  jurisdiction,
  onChange,
  onSaved,
  onSubmit,
  error,
}) {
  const [fieldErrors, setFieldErrors] = useState({});
  const [importing, setImporting] = useState(false);
  const [draggingLogo, setDraggingLogo] = useState(false);
  const institutional = data.dadosInstitucionais || {};
  const visual = data.identidadeVisual || {};
  const chiefOptions = users.filter((user) => user.status === "active" && !["representative", "platform_admin"].includes(user.perfil));
  const selectedState = jurisdictionData.uf || institutional.estado || "";
  const stateMunicipalities = municipalitiesByState[selectedState] || [];
  const selectedMunicipality = jurisdictionData.municipio || institutional.municipio || "";
  const selectedStateData = brazilStates.find((state) => state.code === selectedState);
  const selectedCityData = stateMunicipalities.find((city) => city.name === selectedMunicipality);
  const effectiveIbgeCode = jurisdictionData.codigoIbge || selectedCityData?.id || selectedStateData?.ibgeId || "";
  const schedule = parseOfficeHours(institutional.horarioAtendimento);
  const canLoadIbge = Boolean(effectiveIbgeCode);

  function update(section, key, value) {
    onChange({ ...data, [section]: { ...data[section], [key]: value } });
  }

  function updateContactField(section, key, value) {
    update(section, key, value);
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  function handleSubmit(event) {
    const errors = {};
    if (institutional.telefone && !isValidBrazilianPhone(institutional.telefone)) {
      errors.telefone = "Informe um telefone válido com DDD.";
    }
    if (institutional.whatsapp && !isValidBrazilianPhone(institutional.whatsapp)) {
      errors.whatsapp = "Informe um WhatsApp válido com DDD.";
    }
    if (institutional.emailOficial && !isValidEmail(institutional.emailOficial)) {
      errors.emailOficial = "Informe um e-mail válido.";
    }
    if (institutional.site && !isValidWebsiteUrl(institutional.site)) {
      errors.site = "Informe um site válido, como https://camara.gov.br.";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      event.preventDefault();
      return;
    }
    onSubmit(event);
  }

  async function importFromIbge() {
    setImporting(true);
    try {
      await apiRequest("/api/v1/admin/jurisdicao/ibge", {
        method: "POST",
        body: JSON.stringify({
          tipoCasa: jurisdictionData.tipoCasa,
          codigoIbge: String(effectiveIbgeCode),
          nome: jurisdictionData.nome || defaultJurisdictionName(jurisdictionData.tipoCasa, selectedMunicipality, selectedState),
        }),
      });
      await onSaved();
      setFieldErrors((current) => ({ ...current, ibge: "" }));
    } catch (requestError) {
      setFieldErrors((current) => ({ ...current, ibge: requestError.message }));
    } finally {
      setImporting(false);
    }
  }

  function updateSchedule(key, value) {
    const nextSchedule = { ...schedule, [key]: value };
    update("dadosInstitucionais", "horarioAtendimento", formatOfficeHours(nextSchedule));
  }

  function updateWeekday(day) {
    const days = schedule.days.includes(day)
      ? schedule.days.filter((item) => item !== day)
      : [...schedule.days, day];
    updateSchedule("days", days);
  }

  function applyLogoFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => update("identidadeVisual", "logoUrl", String(reader.result || ""));
    reader.readAsDataURL(file);
  }

  return (
    <form className="settings-form office-settings-form office-panel-form" onSubmit={handleSubmit} noValidate>
      <div className="settings-title"><ShieldCheck size={21} /><div><strong>Dados do gabinete</strong><small>Configurações administrativas do gabinete e sua jurisdição.</small></div></div>

      <section className="office-form-panel">
        <h3>Jurisdição</h3>
        <div className="form-grid">
          <ReadOnlyField label="Tipo" value={chamberTypeLabel(jurisdictionData.tipoCasa)} />
          <ReadOnlyField label="Estado" value={stateLabel(selectedState)} />
          <ReadOnlyField label="Município" value={selectedMunicipality || "Não informado"} />
        </div>
        <div className="office-inner-panel">
          <h4>Malha IBGE</h4>
          {fieldErrors.ibge && <p className="form-error">{fieldErrors.ibge}</p>}
          <div className="ibge-actions-row">
            <button type="button" className="primary-button compact ibge-load-button" disabled={!canLoadIbge || importing} onClick={importFromIbge}>
              {importing ? "Carregando..." : "Carregar Malha IBGE"}
            </button>
            {jurisdiction?.geojson && <p className="form-success ibge-status-message">Malha oficial carregada para o mapa territorial.</p>}
          </div>
          <div className="ibge-values-grid" aria-label="Dados da malha IBGE">
            <IbgeValue label="Código IBGE" value={effectiveIbgeCode} />
            <IbgeValue label="Latitude Central" value={jurisdictionData.latitude} />
            <IbgeValue label="Longitude Central" value={jurisdictionData.longitude} />
            <IbgeValue label="Latitude mínima" value={jurisdictionData.minLatitude} />
            <IbgeValue label="Latitude máxima" value={jurisdictionData.maxLatitude} />
            <IbgeValue label="Longitude mínima" value={jurisdictionData.minLongitude} />
            <IbgeValue label="Longitude máxima" value={jurisdictionData.maxLongitude} />
          </div>
        </div>
      </section>

      <section className="office-form-panel">
        <h3>Dados do Gabinete</h3>
        <div className="office-data-grid">
          <div className="office-data-row">
            <label>Nome do Gabinete<input value={institutional.nomeGabinete || ""} onChange={(event) => update("dadosInstitucionais", "nomeGabinete", event.target.value)} /></label>
            <label className="address-field-label">
              <span>Endereço</span>
              <GooglePlaceAutocompleteInput
                value={institutional.enderecoInstitucional || ""}
                onChange={(value) => update("dadosInstitucionais", "enderecoInstitucional", value)}
                placeholder="Digite o endereço"
                territoryBounds={jurisdiction?.limites}
                hideStatus
                inputProps={{ "aria-label": "Endereço" }}
              />
              <small className="maps-territory-note">Sugestões do Google Maps restritas ao território</small>
            </label>
            <label>Chefe de gabinete<select value={data.chefeGabineteId || ""} onChange={(event) => onChange({ ...data, chefeGabineteId: event.target.value })}><option value="">Não definido</option>{chiefOptions.map((user) => <option key={user.id} value={user.id}>{user.nome}</option>)}</select></label>
          </div>
          <div className="office-data-row">
            <label>Telefone<input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={institutional.telefone || ""} onChange={(event) => updateContactField("dadosInstitucionais", "telefone", formatBrazilianPhone(event.target.value))} aria-invalid={Boolean(fieldErrors.telefone)} />{fieldErrors.telefone && <small className="field-error">{fieldErrors.telefone}</small>}</label>
            <label>WhatsApp<span className="whatsapp-input"><WhatsAppMark /><input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={institutional.whatsapp || ""} onChange={(event) => updateContactField("dadosInstitucionais", "whatsapp", formatBrazilianPhone(event.target.value))} aria-invalid={Boolean(fieldErrors.whatsapp)} /></span>{fieldErrors.whatsapp && <small className="field-error">{fieldErrors.whatsapp}</small>}</label>
          </div>
          <div className="office-data-row">
            <label>E-mail institucional<input type="email" inputMode="email" autoComplete="email" placeholder="gabinete@camara.gov.br" value={institutional.emailOficial || ""} onChange={(event) => updateContactField("dadosInstitucionais", "emailOficial", event.target.value)} aria-invalid={Boolean(fieldErrors.emailOficial)} />{fieldErrors.emailOficial && <small className="field-error">{fieldErrors.emailOficial}</small>}</label>
            <label>Site do Gabinete<input type="url" inputMode="url" placeholder="https://camara.gov.br" value={institutional.site || ""} onBlur={(event) => event.target.value && update("dadosInstitucionais", "site", normalizeWebsiteUrl(event.target.value))} onChange={(event) => updateContactField("dadosInstitucionais", "site", event.target.value)} aria-invalid={Boolean(fieldErrors.site)} />{fieldErrors.site && <small className="field-error">{fieldErrors.site}</small>}</label>
          </div>
          <OfficeHoursPicker schedule={schedule} onToggleDay={updateWeekday} onChange={updateSchedule} />
        </div>
      </section>

      <section className="office-form-panel">
        <h3>Otimizações</h3>
        <div className="office-optimization-grid">
          <label>Cor primária<input className="color-square-input" type="color" value={visual.corPrimaria || "#2563eb"} onChange={(event) => update("identidadeVisual", "corPrimaria", event.target.value)} /></label>
          <label>Cor secundária<input className="color-square-input" type="color" value={visual.corSecundaria || "#0f766e"} onChange={(event) => update("identidadeVisual", "corSecundaria", event.target.value)} /></label>
          <label
            className={`logo-dropzone ${draggingLogo ? "is-dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDraggingLogo(true);
            }}
            onDragLeave={() => setDraggingLogo(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDraggingLogo(false);
              applyLogoFile(event.dataTransfer.files?.[0]);
            }}
          >
            Logotipo do Gabinete
            <span><Upload size={18} /> Arraste uma imagem ou selecione o arquivo</span>
            <input type="file" accept="image/*" onChange={(event) => applyLogoFile(event.target.files?.[0])} />
            {visual.logoUrl && <img src={visual.logoUrl} alt="Logotipo do gabinete" />}
          </label>
        </div>
      </section>

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions"><button className="primary-button compact"><Save size={18} /> Salvar gabinete</button></div>
    </form>
  );
}

// eslint-disable-next-line no-unused-vars
function LegacyOfficeSettings({
  data,
  jurisdictionForm: jurisdictionData,
  users,
  jurisdiction,
  onChange,
  onJurisdictionChange,
  onSaved,
  onSubmit,
  error,
}) {
  const [fieldErrors, setFieldErrors] = useState({});
  const [importing, setImporting] = useState(false);
  const [draggingLogo, setDraggingLogo] = useState(false);
  const update = (section, key, value) => onChange({ ...data, [section]: { ...data[section], [key]: value } });
  const institutional = data.dadosInstitucionais || {};
  const social = data.redesSociais || {};
  const chiefOptions = users.filter((user) => user.status === "active" && !["representative", "platform_admin"].includes(user.perfil));
  const selectedState = jurisdictionData.uf || institutional.estado || "";
  const stateMunicipalities = municipalitiesByState[selectedState] || [];
  const selectedMunicipality = jurisdictionData.municipio || institutional.municipio || "";
  const visual = data.identidadeVisual || {};
  const schedule = parseOfficeHours(institutional.horarioAtendimento);

  function updateInstitutional(patch) {
    onChange({
      ...data,
      dadosInstitucionais: {
        ...institutional,
        ...patch,
      },
    });
  }

  function updateState(state) {
    const municipalities = municipalitiesByState[state] || [];
    const currentCityExists = municipalities.some((city) => city.name === selectedMunicipality);
    const nextCity = currentCityExists ? selectedMunicipality : "";
    updateInstitutional({
      estado: state,
      municipio: nextCity,
    });
    onJurisdictionChange((current) => ({
      ...current,
      uf: state,
      municipio: nextCity,
      codigoIbge: currentCityExists ? current.codigoIbge : "",
      nome: defaultJurisdictionName(current.tipoCasa, nextCity, state),
    }));
  }

  function updateMunicipality(municipalityName) {
    const city = stateMunicipalities.find((item) => item.name === municipalityName);
    updateInstitutional({ estado: selectedState, municipio: municipalityName });
    onJurisdictionChange((current) => ({
      ...current,
      uf: selectedState,
      municipio: municipalityName,
      codigoIbge: city?.id ? String(city.id) : current.codigoIbge,
      nome: defaultJurisdictionName(current.tipoCasa, municipalityName, selectedState),
    }));
  }

  function updateJurisdiction(key, value) {
    onJurisdictionChange((current) => ({
      ...current,
      [key]: value,
      ...(key === "tipoCasa" ? { nome: defaultJurisdictionName(value, current.municipio, current.uf) } : {}),
    }));
  }

  function updateContactField(section, key, value) {
    update(section, key, value);
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  function handleSubmit(event) {
    const errors = {};
    if (institutional.telefone && !isValidBrazilianPhone(institutional.telefone)) {
      errors.telefone = "Informe um telefone válido com DDD.";
    }
    if (institutional.whatsapp && !isValidBrazilianPhone(institutional.whatsapp)) {
      errors.whatsapp = "Informe um WhatsApp válido com DDD.";
    }
    if (institutional.emailOficial && !isValidEmail(institutional.emailOficial)) {
      errors.emailOficial = "Informe um e-mail válido.";
    }
    if (institutional.site && !isValidWebsiteUrl(institutional.site)) {
      errors.site = "Informe um site válido, como https://camara.gov.br.";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      event.preventDefault();
      return;
    }
    onSubmit(event);
  }

  async function importFromIbge() {
    setImporting(true);
    try {
      await apiRequest("/api/v1/admin/jurisdicao/ibge", {
        method: "POST",
        body: JSON.stringify({
          tipoCasa: jurisdictionData.tipoCasa,
          codigoIbge: jurisdictionData.codigoIbge,
          nome: jurisdictionData.nome,
        }),
      });
      await onSaved();
    } catch (requestError) {
      setFieldErrors((current) => ({ ...current, ibge: requestError.message }));
    } finally {
      setImporting(false);
    }
  }

  function updateSchedule(key, value) {
    const nextSchedule = { ...schedule, [key]: value };
    update("dadosInstitucionais", "horarioAtendimento", formatOfficeHours(nextSchedule));
  }

  function updateWeekday(day) {
    const days = schedule.days.includes(day)
      ? schedule.days.filter((item) => item !== day)
      : [...schedule.days, day];
    updateSchedule("days", days);
  }

  function applyLogoFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => update("identidadeVisual", "logoUrl", String(reader.result || ""));
    reader.readAsDataURL(file);
  }

  void importing;
  void draggingLogo;
  void setDraggingLogo;
  void visual;
  void updateMunicipality;
  void updateJurisdiction;
  void importFromIbge;
  void updateWeekday;
  void applyLogoFile;

  return (
    <form className="settings-form office-settings-form" onSubmit={handleSubmit} noValidate>
      <div className="settings-title"><ShieldCheck size={21} /><div><strong>Dados do gabinete</strong><small>Identidade institucional, canais oficiais, redes sociais, logotipo e chefia administrativa.</small></div></div>
      <div className="form-grid">
        <label>Nome do gabinete<input value={institutional.nomeGabinete || ""} onChange={(event) => update("dadosInstitucionais", "nomeGabinete", event.target.value)} /></label>
        <label>Estado<select value={selectedState} onChange={(event) => updateState(event.target.value)}>
          <option value="">Selecionar estado</option>
          {brazilStates.map((state) => <option key={state.code} value={state.code}>{state.name} - {state.code}</option>)}
        </select></label>
        <MunicipalitySearchSelect
          stateCode={selectedState}
          municipalities={stateMunicipalities}
          value={institutional.municipio || ""}
          onChange={(municipality) => update("dadosInstitucionais", "municipio", municipality)}
        />
      </div>
      <div className="form-grid">
        <label>Endereço institucional<GooglePlaceAutocompleteInput value={institutional.enderecoInstitucional || ""} onChange={(value) => update("dadosInstitucionais", "enderecoInstitucional", value)} placeholder="Digite o endereço institucional" territoryBounds={jurisdiction?.limites} inputProps={{ "aria-label": "Endereço institucional" }} /></label>
        <label>Telefone<input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={institutional.telefone || ""} onChange={(event) => updateContactField("dadosInstitucionais", "telefone", formatBrazilianPhone(event.target.value))} aria-invalid={Boolean(fieldErrors.telefone)} />{fieldErrors.telefone && <small className="field-error">{fieldErrors.telefone}</small>}</label>
        <label>E-mail oficial<input type="email" inputMode="email" autoComplete="email" placeholder="gabinete@camara.gov.br" value={institutional.emailOficial || ""} onChange={(event) => updateContactField("dadosInstitucionais", "emailOficial", event.target.value)} aria-invalid={Boolean(fieldErrors.emailOficial)} />{fieldErrors.emailOficial && <small className="field-error">{fieldErrors.emailOficial}</small>}</label>
        <label>Horário de atendimento<input value={institutional.horarioAtendimento || ""} onChange={(event) => update("dadosInstitucionais", "horarioAtendimento", event.target.value)} placeholder="Segunda a sexta, 8h às 17h" /></label>
      </div>
      <div className="form-grid">
        <label>Site<input type="url" inputMode="url" placeholder="https://camara.gov.br" value={institutional.site || ""} onBlur={(event) => event.target.value && update("dadosInstitucionais", "site", normalizeWebsiteUrl(event.target.value))} onChange={(event) => updateContactField("dadosInstitucionais", "site", event.target.value)} aria-invalid={Boolean(fieldErrors.site)} />{fieldErrors.site && <small className="field-error">{fieldErrors.site}</small>}</label>
        <label>Instagram<input value={social.instagram || ""} onChange={(event) => update("redesSociais", "instagram", event.target.value)} /></label>
        <label>Facebook<input value={social.facebook || ""} onChange={(event) => update("redesSociais", "facebook", event.target.value)} /></label>
        <label>YouTube<input value={social.youtube || ""} onChange={(event) => update("redesSociais", "youtube", event.target.value)} /></label>
      </div>
      <div className="form-grid">
        <label>Logotipo URL<input type="url" inputMode="url" placeholder="https://..." value={data.identidadeVisual.logoUrl || ""} onBlur={(event) => event.target.value && update("identidadeVisual", "logoUrl", normalizeWebsiteUrl(event.target.value))} onChange={(event) => updateContactField("identidadeVisual", "logoUrl", event.target.value)} aria-invalid={Boolean(fieldErrors.logoUrl)} />{fieldErrors.logoUrl && <small className="field-error">{fieldErrors.logoUrl}</small>}</label>
        <label>Cor primária<input type="color" value={data.identidadeVisual.corPrimaria || "#2563eb"} onChange={(event) => update("identidadeVisual", "corPrimaria", event.target.value)} /></label>
        <label>Cor secundária<input type="color" value={data.identidadeVisual.corSecundaria || "#0f766e"} onChange={(event) => update("identidadeVisual", "corSecundaria", event.target.value)} /></label>
        <label>Chefe de gabinete<select value={data.chefeGabineteId || ""} onChange={(event) => onChange({ ...data, chefeGabineteId: event.target.value })}><option value="">Não definido</option>{chiefOptions.map((user) => <option key={user.id} value={user.id}>{user.nome}</option>)}</select></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button compact"><Save size={18} /> Salvar gabinete</button>
    </form>
  );
}

function OfficeHoursPicker({ schedule, onToggleDay, onChange }) {
  return (
    <div className="office-data-row office-hours-row">
      <div className="office-hours-picker">
        <span>Horário de atendimento</span>
        <div className="weekday-row" role="group" aria-label="Dias de atendimento">
          {weekdays.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`weekday-toggle ${schedule.days.includes(key) ? "is-selected" : ""}`}
              onClick={() => onToggleDay(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <label>Início<input type="time" value={schedule.start} onChange={(event) => onChange("start", event.target.value)} /></label>
      <label>Fim<input type="time" value={schedule.end} onChange={(event) => onChange("end", event.target.value)} /></label>
    </div>
  );
}

function IbgeValue({ label, value }) {
  const displayValue = value === null || value === undefined || value === "" ? "-" : value;
  return (
    <div className="ibge-value-cell">
      <span>{label}</span>
      <strong>{displayValue}</strong>
    </div>
  );
}

function ReadOnlyField({ label, value }) {
  return (
    <label className="readonly-field">
      {label}
      <span>{value || "Não informado"}</span>
    </label>
  );
}

function WhatsAppMark() {
  return (
    <span className="whatsapp-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32" focusable="false">
        <path fill="#25D366" d="M16 3.5A12.4 12.4 0 0 0 5.3 22.2L3.8 28.5l6.5-1.6A12.4 12.4 0 1 0 16 3.5Z" />
        <path fill="#fff" d="M22.9 18.8c-.4-.2-2.3-1.1-2.6-1.2-.4-.1-.6-.2-.8.2-.2.4-.9 1.2-1.1 1.4-.2.2-.4.3-.8.1-.4-.2-1.5-.5-2.8-1.7-1-1-1.7-2.1-1.9-2.5-.2-.4 0-.6.2-.8.2-.2.4-.4.6-.7.2-.2.2-.4.4-.6.1-.2.1-.5 0-.7-.1-.2-.8-2-.9-2.7-.2-.7-.5-.6-.8-.6h-.7c-.2 0-.7.1-1 .5-.4.4-1.3 1.3-1.3 3.1s1.3 3.6 1.5 3.8c.2.2 2.6 4 6.3 5.6.9.4 1.6.6 2.1.8.9.3 1.7.2 2.3.1.7-.1 2.3-.9 2.6-1.8.3-.9.3-1.6.2-1.8-.1-.2-.4-.3-.8-.5Z" />
      </svg>
    </span>
  );
}

function MunicipalitySearchSelect({ stateCode, municipalities, value, onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const normalized = normalizeSearch(query);
  const selected = municipalities.find((city) => city.name === value);
  const visible = municipalities.filter((city) => {
    if (!normalized) return true;
    return normalizeSearch(city.name).includes(normalized);
  }).slice(0, 30);

  useEffect(() => {
    setQuery("");
    setOpen(false);
  }, [stateCode]);

  function choose(city) {
    onChange(city.name);
    setQuery("");
    setOpen(false);
  }

  function clear() {
    onChange("");
    setQuery("");
    setOpen(false);
  }

  return (
    <label className="municipality-search-select" onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      Município
      <div className={`search-select-control ${open ? "is-open" : ""}`}>
        <MapPinned size={17} aria-hidden="true" />
        <input
          role="combobox"
          aria-label="Município"
          aria-expanded={open}
          aria-controls="office-municipality-options"
          aria-autocomplete="list"
          disabled={!stateCode}
          value={open ? query : selected?.name || value}
          onFocus={() => {
            if (stateCode) setOpen(true);
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          placeholder={stateCode ? "Busque o município" : "Selecione o estado primeiro"}
          autoComplete="off"
        />
        {value && (
          <button type="button" className="search-select-toggle" aria-label="Limpar município" onClick={clear}>
            x
          </button>
        )}
      </div>
      {open && stateCode && (
        <div id="office-municipality-options" className="search-select-menu municipality-search-menu" role="listbox">
          {visible.map((city) => (
            <button key={city.id} type="button" role="option" onMouseDown={(event) => event.preventDefault()} onClick={() => choose(city)}>
              <span>{city.name}</span>
              <small>{stateCode}</small>
            </button>
          ))}
          {!visible.length && <p>Nenhum município encontrado nesse estado.</p>}
        </div>
      )}
    </label>
  );
}

function normalizeSearch(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function ParliamentarianSettings({ data, parties, jurisdiction, onChange, onSubmit, error }) {
  const [insights, setInsights] = useState(data.insightsOficiais || null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [successMessage, setSuccessMessage] = useState("");
  const selectedParty = parties.find((party) => (
    party.id === data.partidoId || party.sigla === data.partido
  ));
  const legislatureOptions = legislatureOptionsFor(jurisdiction?.tipoCasa);
  const update = (key, value) => {
    setSuccessMessage("");
    onChange({ ...data, [key]: value });
  };
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
    setSuccessMessage("");
    update("redesSociais", { ...social, [key]: value });
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  function updateField(key, value) {
    setSuccessMessage("");
    update(key, value);
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  async function handleSubmit(event) {
    const errors = {};
    const cpfDigits = (data.cpf || "").replace(/\D/g, "");
    if (cpfDigits.length === 11 && !isValidBrazilianCpf(data.cpf)) errors.cpf = "Informe um CPF válido.";
    if (data.email && !isValidEmail(data.email)) errors.email = "Informe um e-mail válido.";
    ["instagram", "facebook", "twitter", "tiktok", "youtube"].forEach((key) => {
      if (social[key] && !isValidSocialHandle(social[key])) errors[key] = "Use @usuario ou uma URL válida.";
    });
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      event.preventDefault();
      return;
    }
    const saved = await onSubmit(event);
    if (saved) setSuccessMessage("Parlamentar salvo com sucesso.");
  }

  function updateMandate(index, key, value) {
    setSuccessMessage("");
    const mandates = [...(data.mandatos || [])];
    const next = { ...mandates[index], [key]: value };
    if (key === "legislatura") next.status = mandateStatus(value);
    mandates[index] = next;
    update("mandatos", mandates);
  }

  function addMandate() {
    setSuccessMessage("");
    const legislatura = legislatureOptions[0]?.value || "";
    update("mandatos", [
      ...(data.mandatos || []),
      { legislatura, votos: "", coligacaoFederacao: "", status: mandateStatus(legislatura) },
    ]);
  }

  function removeMandate(index) {
    setSuccessMessage("");
    update("mandatos", (data.mandatos || []).filter((_, current) => current !== index));
  }

  async function requestInsights() {
    const result = await apiRequest("/api/v1/admin/parlamentar/insights-oficiais", {
      method: "POST",
      body: JSON.stringify({ nome: data.nomeParlamentar || data.nomeCompleto }),
    });
    setInsights(result);
    onChange({ ...data, dadosOficiais: officialInsightsText(result), insightsOficiais: result });
  }

  return (
    <form className="settings-form parliamentarian-form parliamentarian-redesign" onSubmit={handleSubmit} noValidate>
      <div className="settings-title"><Users size={21} /><div><strong>Cadastro do parlamentar</strong><small>Dados oficiais, imagem pública, redes sociais, mandatos e acervo de campanha.</small></div></div>

      <section className="parliamentarian-identity-panel">
        <div className="parliamentarian-photo-preview">
          <div>{data.fotografiaUrl ? <img src={data.fotografiaUrl} alt="Fotografia oficial do parlamentar" /> : <Users size={42} />}</div>
          {selectedParty && <span>{selectedParty.logoUrl ? <img src={selectedParty.logoUrl} alt={`Logo ${selectedParty.sigla}`} /> : selectedParty.sigla}</span>}
        </div>
        <div className="parliamentarian-main-fields">
          <label>Nome completo<input value={data.nomeCompleto || ""} onChange={(event) => update("nomeCompleto", event.target.value)} /></label>
          <label>Nome parlamentar<input value={data.nomeParlamentar || ""} onChange={(event) => update("nomeParlamentar", event.target.value)} /></label>
          <label>CPF<input inputMode="numeric" maxLength={14} placeholder="000.000.000-00" value={data.cpf ? formatBrazilianCpf(data.cpf) : ""} onChange={(event) => updateField("cpf", formatBrazilianCpf(event.target.value))} aria-invalid={Boolean(fieldErrors.cpf)} />{fieldErrors.cpf && <small className="field-error">{fieldErrors.cpf}</small>}</label>
        </div>
      </section>

      <OfficialPhotoDropzone value={data.fotografiaUrl || ""} onChange={(value) => updateField("fotografiaUrl", value)} onError={(message) => setFieldErrors((current) => ({ ...current, fotografiaUrl: message }))} />
      {fieldErrors.fotografiaUrl && <p className="form-error">{fieldErrors.fotografiaUrl}</p>}

      <div className="form-grid">
        <PartySearchSelect parties={parties} value={selectedParty} onChange={updateParty} />
        <label>Email oficial<input type="email" inputMode="email" autoComplete="email" placeholder="nome@dominio.com.br" value={data.email || ""} onChange={(event) => updateField("email", event.target.value)} aria-invalid={Boolean(fieldErrors.email)} />{fieldErrors.email && <small className="field-error">{fieldErrors.email}</small>}</label>
      </div>

      <RichTextEditor label="Biografia resumida" value={data.biografia || ""} onChange={(value) => update("biografia", value)} />

      <label className="official-data-field">
        <span>Dados oficiais (Agente IA)<button type="button" className="secondary-button compact" onClick={requestInsights}><Sparkles size={17} /> Buscar fontes oficiais</button></span>
        <small>Use fontes oficiais como TSE e TRE para apoiar conferências e insights.</small>
        <textarea rows="7" value={data.dadosOficiais || ""} onChange={(event) => update("dadosOficiais", event.target.value)} placeholder="As fontes oficiais consultadas e observações do Agente IA aparecerão aqui." />
      </label>
      {insights?.fontes?.length > 0 && (
        <div className="official-source-list">
          {insights.fontes.map((source) => (
            <a key={source.nome} href={source.url} target="_blank" rel="noreferrer">
              <ExternalLink size={16} />
              <span><strong>{source.nome}</strong><small>{source.uso}</small></span>
            </a>
          ))}
        </div>
      )}

      <label>Áreas prioritárias<input value={(data.areasPrioritarias || []).join(", ")} onChange={(event) => update("areasPrioritarias", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="Saúde, educação, infraestrutura" /></label>

      <section className="social-panel">
        <header><strong>Redes Sociais</strong></header>
        <div className="form-grid">
          <SocialInput label="Instagram" network="instagram" value={social.instagram || ""} error={fieldErrors.instagram} onChange={(value) => updateSocial("instagram", value)} />
          <SocialInput label="Facebook" network="facebook" value={social.facebook || ""} error={fieldErrors.facebook} onChange={(value) => updateSocial("facebook", value)} />
          <SocialInput label="X / Twitter" network="twitter" value={social.twitter || ""} error={fieldErrors.twitter} onChange={(value) => updateSocial("twitter", value)} />
          <SocialInput label="TikTok" network="tiktok" value={social.tiktok || ""} error={fieldErrors.tiktok} onChange={(value) => updateSocial("tiktok", value)} />
          <SocialInput label="YouTube" network="youtube" value={social.youtube || ""} error={fieldErrors.youtube} onChange={(value) => updateSocial("youtube", value)} />
        </div>
      </section>

      <section className="mandate-history">
        <header>
          <div><strong>Mandatos</strong><small>Inclua, edite ou exclua mandatos vinculados às legislaturas oficiais.</small></div>
          <button type="button" className="secondary-button compact" onClick={addMandate}><Plus size={17} /> Adicionar mandato</button>
        </header>
        {(data.mandatos || []).map((mandate, index) => (
          <article key={`${index}-${mandate.legislatura || "mandato"}`} className="mandate-row">
            <label>Legislatura<select value={mandate.legislatura || ""} onChange={(event) => updateMandate(index, "legislatura", event.target.value)}><option value="">Selecionar</option>{legislatureOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>Quant. votos<input type="number" min="0" value={mandate.votos || ""} onChange={(event) => updateMandate(index, "votos", event.target.value)} /></label>
            <label>Coligação ou federação<input value={mandate.coligacaoFederacao || ""} onChange={(event) => updateMandate(index, "coligacaoFederacao", event.target.value)} /></label>
            <ReadOnlyField label="Status" value={mandateStatusLabel(mandate.status || mandateStatus(mandate.legislatura))} />
            <button type="button" className="icon-button danger-soft" title="Excluir mandato" onClick={() => removeMandate(index)}><Trash2 size={17} /></button>
          </article>
        ))}
        {!data.mandatos?.length && <p className="table-message">Nenhum mandato cadastrado.</p>}
      </section>

      <CampaignFilesDropzone files={data.arquivosCampanha || []} onChange={(files) => update("arquivosCampanha", files)} onError={(message) => setFieldErrors((current) => ({ ...current, arquivosCampanha: message }))} />
      {fieldErrors.arquivosCampanha && <p className="form-error">{fieldErrors.arquivosCampanha}</p>}
      {error && <p className="form-error">{error}</p>}
      {successMessage && <p className="form-success parliamentarian-success">{successMessage}</p>}
      <div className="parliamentarian-form-actions">
        <button className="primary-button compact"><Save size={18} /> Salvar parlamentar</button>
      </div>
    </form>
  );
}

const officialPhotoMaxBytes = 4 * 1024 * 1024;
const campaignFileMaxBytes = 25 * 1024 * 1024;
const campaignFileTypes = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.oasis.opendocument.text",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "image/png",
  "image/jpeg",
  "image/gif",
  "video/mp4",
  "video/quicktime",
  "audio/mpeg",
  "audio/mp4",
  "audio/wav",
  "audio/ogg",
];

function OfficialPhotoDropzone({ value, onChange, onError }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function selectFile(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      onError("A fotografia oficial deve ser uma imagem.");
      return;
    }
    if (file.size > officialPhotoMaxBytes) {
      onError("A fotografia oficial deve ter no máximo 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const image = new window.Image();
      image.onload = () => {
        const ratio = image.width / image.height;
        if (image.width < 600 || image.height < 600) {
          onError("Use uma imagem com pelo menos 600 x 600 px.");
          return;
        }
        if (ratio < 0.65 || ratio > 1.35) {
          onError("Use uma foto oficial em proporção próxima de retrato/quadrada.");
          return;
        }
        onError("");
        onChange(String(reader.result || ""));
      };
      image.onerror = () => onError("Não foi possível ler a imagem selecionada.");
      image.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  }

  return (
    <section className="parliamentarian-upload-section">
      <label>Fotografia</label>
      <input ref={inputRef} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => selectFile(event.target.files?.[0])} />
      <div
        className={`attachment-dropzone parliamentarian-photo-dropzone ${dragging ? "is-dragging" : ""}`}
        role="button"
        tabIndex="0"
        aria-label="Selecionar ou arrastar fotografia oficial"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          selectFile(event.dataTransfer.files?.[0]);
        }}
      >
        <span className="attachment-drop-icon"><Upload size={21} /></span>
        <span><strong>{value ? "Trocar fotografia oficial" : "Arraste a fotografia oficial para cá"}</strong><small>PNG, JPG ou WEBP · mínimo 600 x 600 px · máximo 4 MB</small></span>
      </div>
    </section>
  );
}

function RichTextEditor({ label, value, onChange }) {
  function wrap(prefix, suffix = prefix) {
    const selection = window.getSelection?.()?.toString?.() || "";
    onChange(`${value}${value ? "\n" : ""}${prefix}${selection || "texto"}${suffix}`);
  }
  return (
    <label className="rich-text-field">
      {label}
      <div className="rich-text-toolbar" aria-label={`${label} - formatação`}>
        <button type="button" title="Negrito" onClick={() => wrap("<strong>", "</strong>")}>B</button>
        <button type="button" title="Itálico" onClick={() => wrap("<em>", "</em>")}>I</button>
        <button type="button" title="Lista" onClick={() => wrap("<ul><li>", "</li></ul>")}>•</button>
      </div>
      <textarea rows="7" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Escreva uma biografia resumida para uso institucional." />
    </label>
  );
}

function SocialInput({ label, network, value, error, onChange }) {
  return (
    <label className="social-input-label">
      {label}
      <span className="social-input">
        <SocialIcon network={network} />
        <input value={value} onChange={(event) => onChange(event.target.value)} onBlur={(event) => onChange(normalizeSocialHandle(event.target.value))} placeholder="@usuario ou https://..." aria-invalid={Boolean(error)} />
      </span>
      {error && <small className="field-error">{error}</small>}
    </label>
  );
}

function SocialIcon({ network }) {
  return <span className={`social-brand social-brand-${network}`} aria-hidden="true">{socialBrandText[network]}</span>;
}

const socialBrandText = {
  instagram: "◎",
  facebook: "f",
  twitter: "X",
  tiktok: "♪",
  youtube: "▶",
};

function CampaignFilesDropzone({ files, onChange, onError }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function addFiles(fileList) {
    const selected = Array.from(fileList || []);
    if (!selected.length) return;
    const accepted = [];
    for (const file of selected) {
      if (file.size > campaignFileMaxBytes) {
        onError(`${file.name} excede o limite de 25 MB.`);
        return;
      }
      if (file.type && !campaignFileTypes.includes(file.type)) {
        onError(`${file.name} não é um tipo permitido.`);
        return;
      }
      accepted.push({ id: `${Date.now()}-${file.name}`, nome: file.name, tipo: file.type || "arquivo", tamanho: file.size, carregadoEm: new Date().toISOString() });
    }
    onError("");
    onChange([...(files || []), ...accepted]);
  }

  return (
    <section className="campaign-files-section">
      <header><strong>Documentos e materiais de campanha</strong><small>PDF, DOC, DOCX, ODT, PPT, PPTX, imagens, vídeos e áudios.</small></header>
      <input ref={inputRef} className="visually-hidden" type="file" multiple accept={campaignFileTypes.join(",")} onChange={(event) => addFiles(event.target.files)} />
      <div
        className={`attachment-dropzone ${dragging ? "is-dragging" : ""}`}
        role="button"
        tabIndex="0"
        aria-label="Selecionar ou arrastar arquivos de campanha"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <span className="attachment-drop-icon"><Upload size={21} /></span>
        <span><strong>Arraste arquivos de campanha para cá</strong><small>ou clique para selecionar · máximo de 25 MB por arquivo</small></span>
      </div>
      <div className="campaign-file-list">
        {(files || []).map((file) => (
          <article key={file.id || file.nome}>
            <FileText size={17} />
            <span><strong>{file.nome}</strong><small>{formatBytes(file.tamanho || 0)} · {file.tipo}</small></span>
            <button type="button" className="icon-button danger-soft" title="Excluir arquivo" onClick={() => onChange(files.filter((item) => item !== file))}><Trash2 size={16} /></button>
          </article>
        ))}
        {!files?.length && <p className="table-message">Nenhum material de campanha carregado.</p>}
      </div>
    </section>
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

function legislatureOptionsFor(chamberType) {
  const currentYear = new Date().getFullYear();
  const span = chamberType === "ASSEMBLEIA_LEGISLATIVA" ? 4 : 4;
  const currentStart = chamberType === "ASSEMBLEIA_LEGISLATIVA"
    ? 2023 + Math.floor((currentYear - 2023) / span) * span
    : 2025 + Math.floor((currentYear - 2025) / span) * span;
  return Array.from({ length: 6 }, (_, index) => {
    const start = currentStart - index * span;
    const end = start + span;
    const value = `${start}-${end}`;
    return { value, label: `${start} a ${end}` };
  });
}

function mandateStatus(legislature) {
  const [start, end] = String(legislature || "").split("-").map(Number);
  const year = new Date().getFullYear();
  if (start && end && year >= start && year <= end) return "ATUAL";
  return "HISTORICO";
}

function mandateStatusLabel(status) {
  return status === "ATUAL" ? "Atual" : "Histórico";
}

function normalizeSocialHandle(value) {
  const trimmed = value.trim();
  if (!trimmed || /^https?:\/\//i.test(trimmed)) return trimmed;
  const clean = trimmed.replace(/^@+/, "").replace(/\s+/g, "");
  return clean ? `@${clean}` : "";
}

function isValidSocialHandle(value) {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (/^https?:\/\//i.test(trimmed)) return isValidWebsiteUrl(trimmed);
  return /^@[A-Za-z0-9._-]{2,60}$/.test(trimmed);
}

function officialInsightsText(insights) {
  const lines = [];
  if (insights?.consulta) lines.push(`Consulta sugerida: ${insights.consulta}`);
  if (insights?.fontes?.length) {
    lines.push("", "Fontes oficiais sugeridas:");
    insights.fontes.forEach((source) => lines.push(`- ${source.nome}: ${source.url}`));
  }
  if (insights?.insightsSugeridos?.length) {
    lines.push("", "Pontos para conferência:");
    insights.insightsSugeridos.forEach((item) => lines.push(`- ${item}`));
  }
  return lines.join("\n").trim();
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const amount = value / (1024 ** exponent);
  return `${amount.toFixed(amount >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function TemplatesSettings({ form, templates, categories, onForm, onSubmit, onUpdate, onDelete, error }) {
  const [selectedId, setSelectedId] = useState("");
  const [preview, setPreview] = useState(null);
  const [editForm, setEditForm] = useState({
    nome: "",
    canal: "WHATSAPP",
    categoriaId: "",
    assunto: "",
    conteudo: "",
  });
  const selected = templates.find((item) => item.id === selectedId);
  const templateForm = selected
    ? editForm
    : {
        nome: form.nome,
        canal: form.canal,
        categoriaId: form.categoriaId,
        assunto: form.assunto,
        conteudo: form.conteudo,
      };

  function selectTemplate(item) {
    setSelectedId(item.id);
    setEditForm({
      nome: item.nome,
      canal: item.canal,
      categoriaId: item.categoriaId || "",
      assunto: item.assunto || "",
      conteudo: item.conteudo || "",
    });
  }

  function clearSelection() {
    setSelectedId("");
    setEditForm({ nome: "", canal: "WHATSAPP", categoriaId: "", assunto: "", conteudo: "" });
    onForm((current) => ({ ...current, nome: "", canal: "WHATSAPP", categoriaId: "", assunto: "", conteudo: "" }));
  }

  function updateField(field, value) {
    if (selected) {
      setEditForm((current) => ({ ...current, [field]: value }));
      return;
    }
    onForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    if (selected) {
      await onUpdate(selected, { ...templateForm, ativa: selected.ativa });
      return;
    }
    await onSubmit(event);
  }

  return <>
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-title"><FileText size={21} /><div><strong>{selected ? "Editar template" : "Novo template"}</strong><small>Inclua mensagens reutilizáveis com variáveis seguras.</small></div></div>
      <label>Nome<input required value={templateForm.nome} onChange={(event) => updateField("nome", event.target.value)} /></label>
      <div className="form-grid">
        <label>Canal<select value={templateForm.canal} onChange={(event) => updateField("canal", event.target.value)}><option value="WHATSAPP">WhatsApp</option><option value="EMAIL">E-mail</option><option value="TELEFONE">Telefone</option><option value="PRESENCIAL">Presencial</option><option value="INTERNO">Interno</option></select></label>
        <label>Categoria<select value={templateForm.categoriaId} onChange={(event) => updateField("categoriaId", event.target.value)}><option value="">Todas</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
      </div>
      <label>Assunto<input value={templateForm.assunto} onChange={(event) => updateField("assunto", event.target.value)} /></label>
      <label>Conteúdo<textarea required rows="7" value={templateForm.conteudo} onChange={(event) => updateField("conteudo", event.target.value)} placeholder="Olá, {{cidadao}}. A solicitação {{protocolo}} está com status {{status}}." /></label>
      <small className="template-help">Variáveis permitidas: {"{{cidadao}}"}, {"{{protocolo}}"} e {"{{status}}"}</small>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="primary-button compact">{selected ? <Save size={18} /> : <Plus size={18} />} {selected ? "Salvar template" : "Adicionar template"}</button>
        {selected && <button type="button" className="secondary-button compact" onClick={clearSelection}><X size={18} /> Novo template</button>}
      </div>
    </form>
    <section className="settings-form users-datatable-section">
      <div className="settings-title"><FileText size={21} /><div><strong>Templates cadastrados</strong><small>Visualize exemplos, edite ou desative templates de resposta.</small></div></div>
      <div className="users-datatable templates-datatable" role="region" aria-label="Templates cadastrados">
        <table>
          <thead><tr><th>Template</th><th>Canal</th><th>Categoria</th><th>Status</th><th>Ações</th></tr></thead>
          <tbody>
            {templates.map((item) => (
              <tr key={item.id} className={selectedId === item.id ? "selected" : ""} onClick={() => selectTemplate(item)} tabIndex={0}>
                <td><strong>{item.nome}</strong><small>v{item.versao}</small></td>
                <td>{item.canal}</td>
                <td>{item.categoria || "Todas"}</td>
                <td>{item.ativa ? "Ativo" : "Inativo"}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" title="Visualizar exemplo" onClick={(event) => { event.stopPropagation(); setPreview(item); }}><Eye size={15} /></button>
                    <button type="button" className={item.ativa ? "danger-soft" : ""} title={item.ativa ? "Desativar template" : "Reativar template"} onClick={(event) => { event.stopPropagation(); item.ativa ? onDelete(item) : onUpdate(item, { ativa: true }); }}>
                      {item.ativa ? <Trash2 size={15} /> : <Save size={15} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!templates.length && <tr><td colSpan={5} className="empty-table-cell">Nenhum template cadastrado.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
    {preview && (
      <div className="modal-backdrop" role="presentation" onClick={() => setPreview(null)}>
        <section className="template-preview-modal" role="dialog" aria-modal="true" aria-label="Visualização do template" onClick={(event) => event.stopPropagation()}>
          <header><div><strong>{preview.nome}</strong><small>{preview.canal} · {preview.categoria || "Todas as categorias"} · v{preview.versao}</small></div><button type="button" className="icon-button" onClick={() => setPreview(null)} aria-label="Fechar"><X size={18} /></button></header>
          {preview.assunto && <div className="template-preview-subject"><span>Assunto</span><strong>{renderTemplateExample(preview.assunto)}</strong></div>}
          <pre>{renderTemplateExample(preview.conteudo)}</pre>
        </section>
      </div>
    )}
  </>;
}

function renderTemplateExample(value = "") {
  return value
    .replaceAll("{{cidadao}}", "Maria Silva")
    .replaceAll("{{protocolo}}", "GAB-2026-000123")
    .replaceAll("{{status}}", "Em atendimento");
}

function TerritoriesSettings({ form, territories, jurisdiction, onForm, onSubmit, onUpdate, onDelete, onReload, error }) {
  const [selectedId, setSelectedId] = useState("");
  const [editName, setEditName] = useState("");
  const selected = territories.find((item) => item.id === selectedId);
  const jurisdictionLabel = jurisdiction?.nome || [jurisdiction?.municipio, jurisdiction?.uf].filter(Boolean).join("/") || "Jurisdição não configurada";

  function selectTerritory(item) {
    setSelectedId(item.id);
    setEditName(item.nome);
  }

  function clearSelection() {
    setSelectedId("");
    setEditName("");
    onForm((current) => ({ ...current, nome: "" }));
  }

  async function submit(event) {
    event.preventDefault();
    if (selected) {
      await onUpdate(selected, { nome: editName, ativa: selected.ativa });
      return;
    }
    await onSubmit(event);
  }

  return <>
    <section className="user-plan-summary territory-suggestion-summary" aria-label="Jurisdição dos territórios">
      <MapPinned size={18} />
      <strong>{jurisdictionLabel}</strong>
      <span>{territories.filter((item) => item.ativa).length} território(s) ativo(s)</span>
      <button type="button" className="secondary-button compact" onClick={onReload}><Save size={16} /> Recarregar sugestões</button>
    </section>
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-title"><MapPinned size={21} /><div><strong>{selected ? "Editar território" : "Novo território"}</strong><small>Use os territórios reais sugeridos para a jurisdição e ajuste quando necessário.</small></div></div>
      <label>Nome<input required value={selected ? editName : form.nome} onChange={(event) => selected ? setEditName(event.target.value) : onForm((current) => ({ ...current, nome: event.target.value }))} /></label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="primary-button compact">{selected ? <Save size={18} /> : <Plus size={18} />} {selected ? "Salvar território" : "Adicionar território"}</button>
        {selected && <button type="button" className="secondary-button compact" onClick={clearSelection}><X size={18} /> Novo território</button>}
      </div>
    </form>
    <section className="settings-form users-datatable-section">
      <div className="settings-title"><MapPinned size={21} /><div><strong>Territórios cadastrados</strong><small>Itens excluídos ficam inativos e podem ser restaurados pela recarga de sugestões.</small></div></div>
      <div className="users-datatable territories-datatable" role="region" aria-label="Territórios cadastrados">
        <table>
          <thead><tr><th>Território</th><th>Status</th><th>Ações</th></tr></thead>
          <tbody>
            {territories.map((item) => (
              <tr key={item.id} className={selectedId === item.id ? "selected" : ""} onClick={() => selectTerritory(item)} tabIndex={0}>
                <td><strong>{item.nome}</strong></td>
                <td>{item.ativa ? "Ativo" : "Inativo"}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" className={item.ativa ? "danger-soft" : ""} title={item.ativa ? "Excluir território" : "Reativar território"} onClick={(event) => { event.stopPropagation(); item.ativa ? onDelete(item) : onUpdate(item, { ativa: true }); }}>
                      {item.ativa ? <Trash2 size={15} /> : <Save size={15} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!territories.length && <tr><td colSpan={3} className="empty-table-cell">Nenhum território cadastrado.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </>;
}

function AgenciesSettings({ form, agencies, jurisdiction, onForm, onSubmit, onUpdate, onDelete, onReload, error }) {
  const [selectedId, setSelectedId] = useState("");
  const [editForm, setEditForm] = useState({ nome: "", emailContato: "", responsavel: "", telefone: "" });
  const selected = agencies.find((item) => item.id === selectedId);
  const jurisdictionLabel = jurisdiction?.nome || [jurisdiction?.municipio, jurisdiction?.uf].filter(Boolean).join("/") || "Jurisdição não configurada";
  const agencyForm = selected
    ? editForm
    : {
        nome: form.nome,
        emailContato: form.emailContato,
        responsavel: form.responsavelOrgao,
        telefone: form.telefoneOrgao,
      };

  function selectAgency(item) {
    setSelectedId(item.id);
    setEditForm({
      nome: item.nome,
      emailContato: item.emailContato || "",
      responsavel: item.responsavel || "",
      telefone: item.telefone || "",
    });
  }

  function clearSelection() {
    setSelectedId("");
    setEditForm({ nome: "", emailContato: "", responsavel: "", telefone: "" });
    onForm((current) => ({
      ...current,
      nome: "",
      emailContato: "",
      responsavelOrgao: "",
      telefoneOrgao: "",
    }));
  }

  function updateField(field, value) {
    if (selected) {
      setEditForm((current) => ({ ...current, [field]: value }));
      return;
    }
    const map = {
      nome: "nome",
      emailContato: "emailContato",
      responsavel: "responsavelOrgao",
      telefone: "telefoneOrgao",
    };
    onForm((current) => ({ ...current, [map[field]]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    if (selected) {
      await onUpdate(selected, { ...agencyForm, ativa: selected.ativa });
      return;
    }
    await onSubmit(event);
  }

  return <>
    <section className="user-plan-summary territory-suggestion-summary" aria-label="Jurisdição dos órgãos">
      <Building2 size={18} />
      <strong>{jurisdictionLabel}</strong>
      <span>{agencies.filter((item) => item.ativa).length} órgão(s) ativo(s)</span>
      <button type="button" className="secondary-button compact" onClick={onReload}><Save size={16} /> Recarregar sugestões</button>
    </section>
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-title"><Building2 size={21} /><div><strong>{selected ? "Editar órgão" : "Novo órgão"}</strong><small>Cadastre órgãos vinculados à jurisdição para encaminhamento e acompanhamento.</small></div></div>
      <label>Nome<input required value={agencyForm.nome} onChange={(event) => updateField("nome", event.target.value)} /></label>
      <div className="form-grid">
        <label>Responsável<input value={agencyForm.responsavel} onChange={(event) => updateField("responsavel", event.target.value)} placeholder="A definir" /></label>
        <label>Telefone<input type="tel" inputMode="numeric" maxLength={15} value={agencyForm.telefone} onChange={(event) => updateField("telefone", formatBrazilianPhone(event.target.value))} placeholder="(00) 00000-0000" /></label>
      </div>
      <label>E-mail de contato<input type="email" inputMode="email" value={agencyForm.emailContato} onChange={(event) => updateField("emailContato", event.target.value.toLowerCase())} placeholder="contato@orgao.gov.br" /></label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="primary-button compact">{selected ? <Save size={18} /> : <Plus size={18} />} {selected ? "Salvar órgão" : "Adicionar órgão"}</button>
        {selected && <button type="button" className="secondary-button compact" onClick={clearSelection}><X size={18} /> Novo órgão</button>}
      </div>
    </form>
    <section className="settings-form users-datatable-section">
      <div className="settings-title"><Building2 size={21} /><div><strong>Órgãos cadastrados</strong><small>Itens excluídos ficam inativos e podem ser restaurados pela recarga de sugestões.</small></div></div>
      <div className="users-datatable agencies-datatable" role="region" aria-label="Órgãos cadastrados">
        <table>
          <thead><tr><th>Órgão</th><th>Contato</th><th>Status</th><th>Ações</th></tr></thead>
          <tbody>
            {agencies.map((item) => (
              <tr key={item.id} className={selectedId === item.id ? "selected" : ""} onClick={() => selectAgency(item)} tabIndex={0}>
                <td><strong>{item.nome}</strong><small>{item.origem || "Manual"}</small></td>
                <td><strong>{item.responsavel || "A definir"}</strong><small>{[item.telefone, item.emailContato].filter(Boolean).join(" · ") || "Contato não informado"}</small></td>
                <td>{item.ativa ? "Ativo" : "Inativo"}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" className={item.ativa ? "danger-soft" : ""} title={item.ativa ? "Excluir órgão" : "Reativar órgão"} onClick={(event) => { event.stopPropagation(); item.ativa ? onDelete(item) : onUpdate(item, { ativa: true }); }}>
                      {item.ativa ? <Trash2 size={15} /> : <Save size={15} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!agencies.length && <tr><td colSpan={4} className="empty-table-cell">Nenhum órgão cadastrado.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </>;
}

function UsersSettings({ form, users, contract, onForm, onSubmit, onUpdate, error }) {
  const [selectedUserId, setSelectedUserId] = useState("");
  const [editForm, setEditForm] = useState({
    nome: "",
    email: "",
    cpf: "",
    telefone: "",
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
      cpf: selectedUser.cpf || "",
      telefone: selectedUser.telefone || "",
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
      cpf: user.cpf || "",
      telefone: user.telefone || "",
      perfil: user.perfil,
      status: user.status,
      senha: "",
    });
  }

  function clearSelection() {
    setSelectedUserId("");
    setEditForm({
      nome: "",
      email: "",
      cpf: "",
      telefone: "",
      perfil: "staff",
      status: "active",
      senha: "",
    });
  }

  async function saveUser(event) {
    event.preventDefault();
    if (!selectedUser) return;
    const patch = {
      nome: editForm.nome,
      email: editForm.email,
      cpf: editForm.cpf,
      telefone: editForm.telefone,
      perfil: editForm.perfil,
      status: editForm.status,
    };
    if (editForm.senha) patch.senha = editForm.senha;
    await onUpdate(selectedUser, patch);
    setEditForm((current) => ({ ...current, senha: "" }));
  }

  function handleSubmit(event) {
    if (selectedUser) {
      saveUser(event);
      return;
    }
    onSubmit(event);
  }

  function updateCurrentUserField(field, value) {
    if (selectedUser) {
      setEditForm((current) => ({ ...current, [field]: value }));
      return;
    }
    const createFieldMap = {
      nome: "nomeUsuario",
      email: "emailUsuario",
      cpf: "cpfUsuario",
      telefone: "telefoneUsuario",
      perfil: "perfilUsuario",
      senha: "senhaUsuario",
    };
    onForm((current) => ({ ...current, [createFieldMap[field]]: value }));
  }

  async function changeStatus(event, user, status) {
    event.stopPropagation();
    if (user.status === status) return;
    await onUpdate(user, { status });
  }

  const activeUsers = contract?.usuariosAtivos ?? users.filter((user) => user.status === "active").length;
  const userLimit = contract?.limiteUsuarios ?? activeUsers;
  const plan = contract?.plano || "starter";
  const planLabel = commercialPlanLabels[plan] || plan;
  const userForm = selectedUser
    ? editForm
    : {
        nome: form.nomeUsuario,
        email: form.emailUsuario,
        cpf: form.cpfUsuario,
        telefone: form.telefoneUsuario,
        perfil: form.perfilUsuario,
        status: "active",
        senha: form.senhaUsuario,
      };
  const cpfDigits = userForm.cpf.replace(/\D/g, "");

  return <>
    <section className="user-plan-summary" aria-label="Plano contratado">
      <ShieldCheck size={18} />
      <strong>Plano contratado: {planLabel}</strong>
      <span>{activeUsers} de {userLimit.toLocaleString("pt-BR")} usuário(s) ativo(s)</span>
    </section>
    <form className="settings-form" onSubmit={handleSubmit}>
      <div className="settings-title"><Users size={21} /><div><strong>{selectedUser ? "Editar usuário" : "Novo usuário"}</strong><small>{selectedUser ? "Atualize dados, perfil, senha opcional e status de acesso." : "Crie assessores e atribua perfis internos."}</small></div></div>
      <label>Nome<input required value={userForm.nome} onChange={(event) => updateCurrentUserField("nome", event.target.value)} /></label>
      <label>E-mail<input required type="email" inputMode="email" autoComplete="email" pattern="^[^@\s]+@[^@\s]+\.[^@\s]{2,}$" placeholder="nome@dominio.com.br" value={userForm.email} onChange={(event) => updateCurrentUserField("email", event.target.value.toLowerCase())} /></label>
      <div className="form-grid">
        <label>CPF<input required inputMode="numeric" autoComplete="off" maxLength={14} placeholder="000.000.000-00" value={userForm.cpf} onChange={(event) => updateCurrentUserField("cpf", formatBrazilianCpf(event.target.value))} aria-invalid={cpfDigits.length === 11 && !isValidBrazilianCpf(userForm.cpf)} />{cpfDigits.length === 11 && !isValidBrazilianCpf(userForm.cpf) && <small className="field-error">CPF inválido.</small>}</label>
        <label>Telefone<input type="tel" inputMode="numeric" autoComplete="tel" maxLength={15} placeholder="(00) 00000-0000" value={userForm.telefone} onChange={(event) => updateCurrentUserField("telefone", formatBrazilianPhone(event.target.value))} /></label>
      </div>
      <div className="form-grid">
        <label>{selectedUser ? "Nova senha" : "Senha inicial"}<input required={!selectedUser} type="password" minLength={8} value={userForm.senha} onChange={(event) => updateCurrentUserField("senha", event.target.value)} placeholder={selectedUser ? "Manter senha atual" : ""} /></label>
        <label>Perfil<select value={userForm.perfil} onChange={(event) => updateCurrentUserField("perfil", event.target.value)}>{userRoleOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {selectedUser && (
        <UserStatusSwitch
          checked={userForm.status === "active"}
          onChange={(checked) => setEditForm((current) => ({ ...current, status: checked ? "active" : "blocked" }))}
          label="Acesso do usuário"
        />
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="primary-button compact">{selectedUser ? <Save size={18} /> : <Plus size={18} />} {selectedUser ? "Salvar usuário" : "Criar usuário"}</button>
        {selectedUser && <button type="button" className="secondary-button compact" onClick={clearSelection}><X size={18} /> Novo usuário</button>}
      </div>
    </form>

    <section className="settings-form users-datatable-section">
      <div className="settings-title"><Users size={21} /><div><strong>Usuários cadastrados</strong><small>Clique em uma linha para editar no formulário acima.</small></div></div>
      <div className="users-datatable" role="region" aria-label="Usuários cadastrados">
        <table>
          <thead>
            <tr>
              <th>Nome</th>
              <th>E-mail</th>
              <th>CPF</th>
              <th>Telefone</th>
              <th>Perfil</th>
              <th>Acesso</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr
                key={user.id}
                className={selectedUserId === user.id ? "selected" : ""}
                tabIndex={0}
                onClick={() => selectUser(user)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectUser(user);
                  }
                }}
              >
                <td><strong>{user.nome}</strong>{user.chefeGabinete && <small>Chefe de Gabinete</small>}</td>
                <td>{user.email}</td>
                <td>{user.cpf || "-"}</td>
                <td>{user.telefone || "-"}</td>
                <td>{userRoleLabels[user.perfil] || user.perfil}</td>
                <td>
                  <UserStatusSwitch
                    checked={user.status === "active"}
                    onChange={(checked, event) => changeStatus(event, user, checked ? "active" : "blocked")}
                    compact
                    label={`Acesso de ${user.nome}`}
                  />
                </td>
              </tr>
            ))}
            {!users.length && (
              <tr>
                <td colSpan={6} className="empty-table-cell">Nenhum usuário cadastrado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
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
      <label>Perfil<select value={form.perfilUsuario} onChange={(event) => onForm((current) => ({ ...current, perfilUsuario: event.target.value }))}>{userRoleOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button compact"><Plus size={18} /> Criar usuario</button>
    </form>
    <div className="category-list">
      {users.map((user) => <article key={user.id}><span className="entity-icon"><Users size={19} /></span><div><strong>{user.nome}{user.chefeGabinete ? " · Chefe de Gabinete" : ""}</strong><small>{user.email} · {user.perfil} · {user.status}</small></div><select value={user.status} onChange={(event) => onUpdate(user, { status: event.target.value })}><option value="active">active</option><option value="blocked">blocked</option></select></article>)}
    </div>
  </>;
}

function AuditSettings({ items, pagination, perPage, onPage, onPerPage }) {
  const [sort, setSort] = useState({ key: "quando", direction: "desc" });
  const columns = [
    ["quem", "Quem fez"],
    ["oQue", "O que foi feito"],
    ["onde", "Onde"],
    ["quando", "Quando"],
  ];
  const rows = useMemo(() => items.map((item) => {
    const when = new Date(item.criadoEm);
    return {
      ...item,
      quem: item.usuarioNome || "Sistema",
      quemDetalhe: item.usuarioEmail || "Ação automática",
      oQue: item.acaoAmigavel || humanizeAuditAction(item.acao),
      onde: item.entidadeAmigavel || humanizeAuditEntity(item.entidade),
      registro: item.registro || "Registro interno",
      quando: when,
      quandoTexto: when.toLocaleString("pt-BR"),
    };
  }), [items]);
  const sortedRows = useMemo(() => [...rows].sort((left, right) => {
    const leftValue = auditSortValue(left, sort.key);
    const rightValue = auditSortValue(right, sort.key);
    const result = leftValue.localeCompare(rightValue, "pt-BR", { numeric: true, sensitivity: "base" });
    return sort.direction === "asc" ? result : -result;
  }), [rows, sort]);

  function changeSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  return (
    <div className="audit-admin-panel">
      <header className="audit-admin-toolbar">
        <div>
          <strong>Trilha de auditoria interna</strong>
          <span>{pagination.total} registro(s)</span>
        </div>
        <label>Itens por página<select value={perPage} onChange={(event) => onPerPage(Number(event.target.value))}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
      </header>
      <div className="audit-admin-table">
        <table>
          <thead>
            <tr>
              {columns.map(([key, label]) => (
                <th key={key}>
                  <button type="button" onClick={() => changeSort(key)} aria-sort={sort.key === key ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
                    {label}
                    {sort.key === key ? (sort.direction === "asc" ? <ArrowUp size={14} /> : <ArrowDown size={14} />) : <ArrowUpDown size={14} />}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((item) => (
              <tr key={item.id}>
                <td><strong>{item.quem}</strong><small>{item.quemDetalhe}</small></td>
                <td><strong>{item.oQue}</strong><small>{item.resumo || item.acao}</small></td>
                <td><strong>{item.onde}</strong><small>{item.registro}</small></td>
                <td><strong>{item.quandoTexto}</strong><small>{relativeAuditDate(item.quando)}</small></td>
              </tr>
            ))}
            {!items.length && (
              <tr><td colSpan="4" className="audit-empty">Nenhum evento encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="audit-admin-pagination">
        <span>Página {pagination.page} de {pagination.totalPages}</span>
        <div>
          <button className="secondary-button compact" type="button" disabled={pagination.page <= 1} onClick={() => onPage(pagination.page - 1)}>Anterior</button>
          <button className="secondary-button compact" type="button" disabled={pagination.page >= pagination.totalPages} onClick={() => onPage(pagination.page + 1)}>Próxima</button>
        </div>
      </footer>
    </div>
  );
}

function auditSortValue(item, key) {
  if (key === "quando") return item.quando?.toISOString?.() || "";
  return String(item[key] || "");
}

function humanizeAuditAction(action = "") {
  const labels = {
    "auth.login": "Acessou o sistema",
    "response_template.created": "Template de resposta criado",
    "response_template.updated": "Template de resposta editado",
    "response_template.deactivated": "Template de resposta desativado",
    "territory.suggestions.reloaded": "Sugestões de territórios recarregadas",
    "agency.suggestions.reloaded": "Sugestões de órgãos recarregadas",
  };
  if (labels[action]) return labels[action];
  return action.replace(/[._]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Evento registrado";
}

function humanizeAuditEntity(entity = "") {
  const labels = {
    external_agency: "Órgão",
    integration_setting: "Integração",
    request_category: "Categoria",
    response_template: "Template de resposta",
    territory: "Território",
    user: "Usuário",
  };
  if (labels[entity]) return labels[entity];
  return entity.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Registro";
}

function relativeAuditDate(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  return `há ${days} dia(s)`;
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

// eslint-disable-next-line no-unused-vars
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
      <div className="settings-title"><MapPinned size={21} /><div><strong>Jurisdição territorial</strong><small>Escopo usado por mapa, indicadores e autocomplete.</small></div></div>
      <div className="form-grid">
        <label>Tipo<select value={form.tipoCasa} onChange={(event) => setForm((current) => ({ ...current, tipoCasa: event.target.value }))}><option value="CAMARA_MUNICIPAL">Câmara Municipal</option><option value="ASSEMBLEIA_LEGISLATIVA">Assembleia Legislativa</option></select></label>
        <label>UF<input required maxLength="2" value={form.uf} onChange={(event) => setForm((current) => ({ ...current, uf: event.target.value.toUpperCase() }))} /></label>
      </div>
      <label>Nome da jurisdição<input value={form.nome} onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))} placeholder="Ex.: Juiz de Fora/MG" /></label>
      <label>Município<input value={form.municipio} onChange={(event) => setForm((current) => ({ ...current, municipio: event.target.value }))} /></label>
      <div className="form-grid">
        <label>Código IBGE<input value={form.codigoIbge} onChange={(event) => setForm((current) => ({ ...current, codigoIbge: event.target.value.replace(/\D/g, "") }))} placeholder="Ex.: 3136702" /></label>
        <button type="button" className="secondary-button jurisdiction-import-button" disabled={importing || !form.codigoIbge} onClick={importFromIbge}>{importing ? "Carregando malha..." : "Carregar malha do IBGE"}</button>
      </div>
      <div className="form-grid">
        <label>Latitude central<input type="number" step="0.000001" value={form.latitude} onChange={(event) => setForm((current) => ({ ...current, latitude: event.target.value }))} /></label>
        <label>Longitude central<input type="number" step="0.000001" value={form.longitude} onChange={(event) => setForm((current) => ({ ...current, longitude: event.target.value }))} /></label>
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

function defaultJurisdictionName(type, city, state) {
  if (type === "ASSEMBLEIA_LEGISLATIVA") {
    return state ? `Estado de ${state}` : "";
  }
  return city ? `Município de ${city}` : "";
}

function chamberTypeLabel(type) {
  const labels = {
    CAMARA_MUNICIPAL: "Câmara Municipal",
    ASSEMBLEIA_LEGISLATIVA: "Assembleia Legislativa",
  };
  return labels[type] || type || "Não informado";
}

function stateLabel(stateCode) {
  const state = brazilStates.find((item) => item.code === stateCode);
  if (!state) return stateCode || "Não informado";
  return `${state.name} - ${state.code}`;
}

function parseOfficeHours(value) {
  if (!value) return defaultOfficeHours;
  if (typeof value === "object") {
    return {
      ...defaultOfficeHours,
      ...value,
      days: Array.isArray(value.days) ? value.days : defaultOfficeHours.days,
    };
  }
  const text = String(value);
  if (text.startsWith("json:")) {
    try {
      const parsed = JSON.parse(text.slice(5));
      return {
        ...defaultOfficeHours,
        ...parsed,
        days: Array.isArray(parsed.days) ? parsed.days : defaultOfficeHours.days,
      };
    } catch {
      return defaultOfficeHours;
    }
  }
  return defaultOfficeHours;
}

function formatOfficeHours(schedule) {
  const normalized = {
    days: Array.isArray(schedule.days) ? schedule.days : defaultOfficeHours.days,
    start: schedule.start || defaultOfficeHours.start,
    end: schedule.end || defaultOfficeHours.end,
  };
  return `json:${JSON.stringify(normalized)}`;
}

function normalizeOffice(data) {
  const visual = data?.identidadeVisual || {};
  return {
    dadosInstitucionais: data?.dadosInstitucionais || visual.dadosInstitucionais || {},
    redesSociais: data?.redesSociais || visual.redesSociais || {},
    identidadeVisual: visual,
    chefeGabineteId: data?.chefeGabineteId || "",
    contrato: data?.contrato || emptyOffice.contrato,
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
