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
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail, isValidWebsiteUrl, normalizeWebsiteUrl } from "../contactValidation";
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
    setOfficeJurisdictionForm(jurisdictionForm(jurisdiction));
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
        redesSociais: {},
        identidadeVisual: {
          ...officeForm.identidadeVisual,
          dadosInstitucionais: officeForm.dadosInstitucionais,
          redesSociais: {},
        },
      };
      await apiRequest("/api/v1/admin/jurisdicao", {
        method: "PATCH",
        body: JSON.stringify(jurisdictionPayload(officeJurisdictionForm)),
      });
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
      {sections.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>{label}</button>)}
    </section>
    <section className={wideLayout ? "admin-layout admin-layout-wide" : "admin-layout"}>
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
      {!["office", "parliamentarian", "users", "audit"].includes(active) && <>
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

function OfficeSettings({
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

  function updateInstitutional(patch) {
    onChange({ ...data, dadosInstitucionais: { ...institutional, ...patch } });
  }

  function nextIbgeCode(type, stateCode, cityName) {
    if (type === "ASSEMBLEIA_LEGISLATIVA") {
      return brazilStates.find((state) => state.code === stateCode)?.ibgeId || "";
    }
    return (municipalitiesByState[stateCode] || []).find((city) => city.name === cityName)?.id || "";
  }

  function updateState(state) {
    const municipalities = municipalitiesByState[state] || [];
    const currentCityExists = municipalities.some((city) => city.name === selectedMunicipality);
    const nextCity = currentCityExists ? selectedMunicipality : "";
    const code = nextIbgeCode(jurisdictionData.tipoCasa, state, nextCity);
    updateInstitutional({ estado: state, municipio: nextCity });
    onJurisdictionChange((current) => ({
      ...current,
      uf: state,
      municipio: nextCity,
      codigoIbge: code ? String(code) : "",
      nome: defaultJurisdictionName(current.tipoCasa, nextCity, state),
    }));
  }

  function updateMunicipality(municipalityName) {
    const code = nextIbgeCode(jurisdictionData.tipoCasa, selectedState, municipalityName);
    updateInstitutional({ estado: selectedState, municipio: municipalityName });
    onJurisdictionChange((current) => ({
      ...current,
      uf: selectedState,
      municipio: municipalityName,
      codigoIbge: code ? String(code) : "",
      nome: defaultJurisdictionName(current.tipoCasa, municipalityName, selectedState),
    }));
  }

  function updateJurisdictionType(value) {
    const code = nextIbgeCode(value, selectedState, selectedMunicipality);
    onJurisdictionChange((current) => ({
      ...current,
      tipoCasa: value,
      codigoIbge: code ? String(code) : current.codigoIbge,
      nome: defaultJurisdictionName(value, current.municipio || selectedMunicipality, current.uf || selectedState),
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
          <label>Tipo<select value={jurisdictionData.tipoCasa} onChange={(event) => updateJurisdictionType(event.target.value)}>
            <option value="CAMARA_MUNICIPAL">Câmara Municipal</option>
            <option value="ASSEMBLEIA_LEGISLATIVA">Assembleia Legislativa</option>
          </select></label>
          <label>Estado<select value={selectedState} onChange={(event) => updateState(event.target.value)}>
            <option value="">Selecionar estado</option>
            {brazilStates.map((state) => <option key={state.code} value={state.code}>{state.name} - {state.code}</option>)}
          </select></label>
          <MunicipalitySearchSelect
            stateCode={selectedState}
            municipalities={stateMunicipalities}
            value={selectedMunicipality}
            onChange={updateMunicipality}
          />
        </div>
        <div className="office-inner-panel">
          <h4>Malha IBGE</h4>
          {jurisdiction?.geojson && <p className="form-success ibge-status-message">Malha oficial carregada para o mapa territorial.</p>}
          {fieldErrors.ibge && <p className="form-error">{fieldErrors.ibge}</p>}
          <div className="ibge-actions-row">
            <button type="button" className="primary-button compact ibge-load-button" disabled={!canLoadIbge || importing} onClick={importFromIbge}>
              {importing ? "Carregando..." : "Carregar Malha IBGE"}
            </button>
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
      <button className="primary-button compact"><Save size={18} /> Salvar gabinete</button>
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

function ParliamentarianSettings({ data, parties, onChange, onSubmit, error }) {
  const [insights, setInsights] = useState(data.insightsOficiais || null);
  const [fieldErrors, setFieldErrors] = useState({});
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
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  function updateField(key, value) {
    update(key, value);
    if (fieldErrors[key]) setFieldErrors((current) => ({ ...current, [key]: "" }));
  }

  function handleSubmit(event) {
    const errors = {};
    if (data.email && !isValidEmail(data.email)) errors.email = "Informe um e-mail válido.";
    if (data.telefoneInstitucional && !isValidBrazilianPhone(data.telefoneInstitucional)) errors.telefoneInstitucional = "Informe um telefone válido com DDD.";
    if (data.fotografiaUrl && !isValidWebsiteUrl(data.fotografiaUrl)) errors.fotografiaUrl = "Informe uma URL válida para a fotografia.";
    if (social.site && !isValidWebsiteUrl(social.site)) errors.site = "Informe um site válido.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      event.preventDefault();
      return;
    }
    onSubmit(event);
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
      <form className="settings-form parliamentarian-form" onSubmit={handleSubmit} noValidate>
        <div className="settings-title"><Users size={21} /><div><strong>Cadastro do parlamentar</strong><small>Dados do titular, partido, contato, redes, prioridades e histórico de mandatos.</small></div></div>
        <div className="form-grid">
          <label>Nome completo<input value={data.nomeCompleto || ""} onChange={(event) => update("nomeCompleto", event.target.value)} /></label>
          <label>Nome parlamentar<input value={data.nomeParlamentar || ""} onChange={(event) => update("nomeParlamentar", event.target.value)} /></label>
          <label>Fotografia URL<input type="url" inputMode="url" value={data.fotografiaUrl || ""} onBlur={(event) => event.target.value && update("fotografiaUrl", normalizeWebsiteUrl(event.target.value))} onChange={(event) => updateField("fotografiaUrl", event.target.value)} placeholder="https://..." aria-invalid={Boolean(fieldErrors.fotografiaUrl)} />{fieldErrors.fotografiaUrl && <small className="field-error">{fieldErrors.fotografiaUrl}</small>}</label>
          <PartySearchSelect parties={parties} value={selectedParty} onChange={updateParty} />
        </div>
        <div className="form-grid">
          <label>Coligação ou federação<input value={data.coligacaoFederacao || ""} onChange={(event) => update("coligacaoFederacao", event.target.value)} /></label>
          <label>E-mail<input type="email" inputMode="email" autoComplete="email" placeholder="nome@dominio.com.br" value={data.email || ""} onChange={(event) => updateField("email", event.target.value)} aria-invalid={Boolean(fieldErrors.email)} />{fieldErrors.email && <small className="field-error">{fieldErrors.email}</small>}</label>
          <label>Telefone institucional<input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={data.telefoneInstitucional || ""} onChange={(event) => updateField("telefoneInstitucional", formatBrazilianPhone(event.target.value))} aria-invalid={Boolean(fieldErrors.telefoneInstitucional)} />{fieldErrors.telefoneInstitucional && <small className="field-error">{fieldErrors.telefoneInstitucional}</small>}</label>
          <label>Status no mandato<select value={data.statusMandato || "ATIVO"} onChange={(event) => update("statusMandato", event.target.value)}><option value="ATIVO">Ativo</option><option value="LICENCIADO">Licenciado</option><option value="SUPLENTE">Suplente</option><option value="ENCERRADO">Encerrado</option></select></label>
        </div>
        <label>Biografia resumida<textarea rows="5" value={data.biografia || ""} onChange={(event) => update("biografia", event.target.value)} /></label>
        <label>Áreas prioritárias<input value={(data.areasPrioritarias || []).join(", ")} onChange={(event) => update("areasPrioritarias", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="Saúde, educação, infraestrutura" /></label>
        <div className="form-grid">
          <label>Instagram<input value={social.instagram || ""} onChange={(event) => updateSocial("instagram", event.target.value)} /></label>
          <label>Facebook<input value={social.facebook || ""} onChange={(event) => updateSocial("facebook", event.target.value)} /></label>
          <label>X / Twitter<input value={social.twitter || ""} onChange={(event) => updateSocial("twitter", event.target.value)} /></label>
          <label>Site<input type="url" inputMode="url" placeholder="https://..." value={social.site || ""} onBlur={(event) => event.target.value && updateSocial("site", normalizeWebsiteUrl(event.target.value))} onChange={(event) => updateSocial("site", event.target.value)} aria-invalid={Boolean(fieldErrors.site)} />{fieldErrors.site && <small className="field-error">{fieldErrors.site}</small>}</label>
        </div>

        <section className="mandate-history">
          <header>
            <div><strong>Legislaturas e mandatos</strong><small>Mantenha o mandato atual e histórico de mandatos anteriores, incluindo votos recebidos.</small></div>
            <button type="button" className="secondary-button compact" onClick={addMandate}><Plus size={17} /> Adicionar mandato</button>
          </header>
          {(data.mandatos || []).map((mandate, index) => (
            <article key={`${index}-${mandate.legislatura || "mandato"}`} className="mandate-row">
              <label>Legislatura<input value={mandate.legislatura || ""} onChange={(event) => updateMandate(index, "legislatura", event.target.value)} placeholder="2025-2028" /></label>
              <label>Cargo<input value={mandate.cargo || ""} onChange={(event) => updateMandate(index, "cargo", event.target.value)} /></label>
              <label>Início<input type="date" value={mandate.inicio || ""} onChange={(event) => updateMandate(index, "inicio", event.target.value)} /></label>
              <label>Fim<input type="date" value={mandate.fim || ""} onChange={(event) => updateMandate(index, "fim", event.target.value)} /></label>
              <label>Votos<input type="number" min="0" value={mandate.votos || ""} onChange={(event) => updateMandate(index, "votos", event.target.value)} /></label>
              <label>Status<select value={mandate.status || "HISTORICO"} onChange={(event) => updateMandate(index, "status", event.target.value)}><option value="ATUAL">Atual</option><option value="HISTORICO">Histórico</option><option value="ENCERRADO">Encerrado</option></select></label>
              <button type="button" className="icon-button" title="Remover mandato" onClick={() => removeMandate(index)}><Trash2 size={17} /></button>
            </article>
          ))}
          {!data.mandatos?.length && <p className="table-message">Nenhum mandato cadastrado.</p>}
        </section>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button compact"><Save size={18} /> Salvar parlamentar</button>
      </form>

      <section className="official-insights-panel">
        <div className="settings-title"><Sparkles size={21} /><div><strong>Agente de dados oficiais</strong><small>Use fontes oficiais como TSE e TRE para apoiar conferências e insights.</small></div></div>
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
        <label>Itens por página<select value={perPage} onChange={(event) => onPerPage(Number(event.target.value))}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
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
        <span>Página {pagination.page} de {pagination.totalPages}</span>
        <div>
          <button className="secondary-button compact" type="button" disabled={pagination.page <= 1} onClick={() => onPage(pagination.page - 1)}>Anterior</button>
          <button className="secondary-button compact" type="button" disabled={pagination.page >= pagination.totalPages} onClick={() => onPage(pagination.page + 1)}>Próxima</button>
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

function jurisdictionPayload(form) {
  const payload = {
    tipoCasa: form.tipoCasa,
    nome: form.nome || defaultJurisdictionName(form.tipoCasa, form.municipio, form.uf),
    municipio: form.municipio,
    uf: form.uf,
    codigoIbge: form.codigoIbge,
    centro: {
      latitude: form.latitude,
      longitude: form.longitude,
    },
  };
  const hasBounds = ["minLatitude", "maxLatitude", "minLongitude", "maxLongitude"].every((key) => form[key] !== "");
  if (hasBounds) {
    payload.limites = {
      minLatitude: form.minLatitude,
      maxLatitude: form.maxLatitude,
      minLongitude: form.minLongitude,
      maxLongitude: form.maxLongitude,
    };
  }
  return payload;
}

function defaultJurisdictionName(type, city, state) {
  if (type === "ASSEMBLEIA_LEGISLATIVA") {
    return state ? `Estado de ${state}` : "";
  }
  return city ? `Município de ${city}` : "";
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
