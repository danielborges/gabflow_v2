import {
  Activity,
  Building2,
  Gauge,
  LifeBuoy,
  LockKeyhole,
  LogOut,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../api";

const availableModules = [
  "solicitacoes",
  "cidadaos",
  "ia",
  "rag",
  "documentos",
  "agenda",
  "fiscalizacao",
  "canais",
  "privacidade",
  "integracoes",
];

const plans = ["starter", "professional", "premium", "enterprise"];
const settingTypes = [
  "PARAMETER",
  "GLOBAL_TEMPLATE",
  "INTEGRATION_PROVIDER",
  "FEATURE_FLAG",
  "SECURITY_POLICY",
];

export function PlatformAdminWorkspace({ user, onLogout }) {
  const [activeView, setActiveView] = useState("overview");
  const [overview, setOverview] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [settings, setSettings] = useState([]);
  const [supportAccesses, setSupportAccesses] = useState([]);
  const [audit, setAudit] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [usage, setUsage] = useState(null);
  const [notice, setNotice] = useState("");

  const loadPlatformData = useCallback(async () => {
    const [overviewData, tenantsData, settingsData, supportData, auditData] = await Promise.all([
      apiRequest("/api/v1/platform/overview"),
      apiRequest("/api/v1/platform/gabinetes"),
      apiRequest("/api/v1/platform/configuracoes"),
      apiRequest("/api/v1/platform/suporte"),
      apiRequest("/api/v1/platform/auditoria"),
    ]);
    setOverview(overviewData);
    setTenants(tenantsData.content || []);
    setSettings(settingsData.content || []);
    setSupportAccesses(supportData.content || []);
    setAudit(auditData.content || []);
    if (!selectedTenantId && tenantsData.content?.[0]) {
      setSelectedTenantId(tenantsData.content[0].id);
    }
  }, [selectedTenantId]);

  useEffect(() => {
    loadPlatformData();
  }, [loadPlatformData]);

  async function loadUsage(tenantId) {
    setSelectedTenantId(tenantId);
    if (!tenantId) {
      setUsage(null);
      return;
    }
    setUsage(await apiRequest(`/api/v1/platform/gabinetes/${tenantId}/consumo`));
  }

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId),
    [tenants, selectedTenantId],
  );

  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <div className="sidebar-brand">
          <img src="/images/logo.png" alt="GabFlow" />
        </div>
        <div className="platform-badge"><ShieldCheck size={18} /> Administrador Geral</div>
        <nav aria-label="Administracao da plataforma">
          <PlatformNav active={activeView} id="overview" label="Painel" icon={Gauge} onClick={setActiveView} />
          <PlatformNav active={activeView} id="tenants" label="Gabinetes" icon={Building2} onClick={setActiveView} />
          <PlatformNav active={activeView} id="settings" label="Configuracoes" icon={Settings2} onClick={setActiveView} />
          <PlatformNav active={activeView} id="support" label="Suporte" icon={LifeBuoy} onClick={setActiveView} />
          <PlatformNav active={activeView} id="audit" label="Auditoria" icon={Activity} onClick={setActiveView} />
        </nav>
        <div className="sidebar-footer">
          <div className="security-note"><LockKeyhole size={18} /><span>Sem acesso livre a dados internos</span></div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">GabFlow Plataforma</p>
            <h1 className="compact-title">Administracao Geral</h1>
          </div>
          <div className="user-summary">
            <span className="avatar">{user.name.slice(0, 2).toUpperCase()}</span>
            <span><strong>{user.name}</strong><small>Operacao da plataforma</small></span>
          </div>
          <button className="icon-button" onClick={onLogout} aria-label="Sair" title="Sair">
            <LogOut size={20} />
          </button>
        </header>

        {notice && <p className="form-success platform-notice">{notice}</p>}
        {activeView === "overview" && <OverviewPanel overview={overview} />}
        {activeView === "tenants" && (
          <TenantsPanel
            tenants={tenants}
            selectedTenant={selectedTenant}
            selectedTenantId={selectedTenantId}
            usage={usage}
            onLoadUsage={loadUsage}
            onRefresh={loadPlatformData}
            onNotice={setNotice}
          />
        )}
        {activeView === "settings" && (
          <SettingsPanel settings={settings} onRefresh={loadPlatformData} onNotice={setNotice} />
        )}
        {activeView === "support" && (
          <SupportPanel
            tenants={tenants}
            supportAccesses={supportAccesses}
            onRefresh={loadPlatformData}
            onNotice={setNotice}
          />
        )}
        {activeView === "audit" && <AuditPanel audit={audit} />}
      </main>
    </div>
  );
}

function PlatformNav({ active, id, label, icon: Icon, onClick }) {
  return (
    <button className={active === id ? "nav-item active" : "nav-item"} onClick={() => onClick(id)}>
      <Icon size={19} />
      <span>{label}</span>
    </button>
  );
}

function OverviewPanel({ overview }) {
  const totals = overview?.totais || {};
  return (
    <section className="page-section">
      <p className="eyebrow">Operacao consolidada</p>
      <h2>Saude da plataforma</h2>
      <div className="metric-grid">
        <Metric label="Gabinetes" value={totals.gabinetes} />
        <Metric label="Usuarios" value={totals.usuarios} />
        <Metric label="Solicitacoes" value={totals.solicitacoes} />
        <Metric label="Docs RAG" value={totals.documentosRag} />
        <Metric label="Mensagens" value={totals.mensagensCanal} />
        <Metric label="Anexos" value={totals.anexos} />
      </div>
      <div className="platform-columns">
        <section>
          <h3>Gabinetes por status</h3>
          <KeyValueRows rows={overview?.gabinetesPorStatus || {}} />
        </section>
        <section>
          <h3>Alertas</h3>
          {(overview?.alertas || []).length ? (
            overview.alertas.map((alert) => <p className="soft-alert" key={alert.tipo}>{alert.mensagem}</p>)
          ) : (
            <p className="muted">Nenhum alerta consolidado no momento.</p>
          )}
        </section>
      </div>
    </section>
  );
}

function TenantsPanel({
  tenants,
  selectedTenant,
  selectedTenantId,
  usage,
  onLoadUsage,
  onRefresh,
  onNotice,
}) {
  const [form, setForm] = useState({
    nome: "",
    slug: "",
    plano: "starter",
    limiteUsuarios: 5,
    limiteArmazenamentoMb: 1024,
    modulosHabilitados: ["solicitacoes", "cidadaos", "canais"],
  });
  const [contractForm, setContractForm] = useState({ contrato: "active", motivo: "" });
  const [moduleDraft, setModuleDraft] = useState([]);

  async function createTenant(event) {
    event.preventDefault();
    await apiRequest("/api/v1/platform/gabinetes", { method: "POST", body: JSON.stringify(form) });
    setForm({ ...form, nome: "", slug: "" });
    onNotice("Gabinete cadastrado.");
    await onRefresh();
  }

  async function transitionContract(event) {
    event.preventDefault();
    if (!selectedTenantId) return;
    await apiRequest(`/api/v1/platform/gabinetes/${selectedTenantId}/contrato`, {
      method: "POST",
      body: JSON.stringify(contractForm),
    });
    setContractForm({ ...contractForm, motivo: "" });
    onNotice("Transicao contratual registrada.");
    await onRefresh();
    await onLoadUsage(selectedTenantId);
  }

  async function saveModules() {
    if (!selectedTenantId) return;
    const modules = moduleDraft.length ? moduleDraft : selectedTenant?.modulosHabilitados || [];
    await apiRequest(`/api/v1/platform/gabinetes/${selectedTenantId}`, {
      method: "PATCH",
      body: JSON.stringify({ modulosHabilitados: modules }),
    });
    onNotice("Modulos habilitados atualizados.");
    await onRefresh();
    await onLoadUsage(selectedTenantId);
  }

  function selectTenant(tenantId) {
    const tenant = tenants.find((item) => item.id === tenantId);
    setContractForm({ contrato: tenant?.contrato || "active", motivo: "" });
    setModuleDraft(tenant?.modulosHabilitados || []);
    onLoadUsage(tenantId);
  }

  return (
    <section className="page-section">
      <p className="eyebrow">Clientes e contratos</p>
      <h2>Gabinetes contratados</h2>
      <div className="platform-columns">
        <form className="compact-form" onSubmit={createTenant}>
          <h3>Novo gabinete</h3>
          <label>Nome<input value={form.nome} onChange={(event) => setForm({ ...form, nome: event.target.value })} required /></label>
          <label>Slug<input value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })} required /></label>
          <label>Plano<select value={form.plano} onChange={(event) => setForm({ ...form, plano: event.target.value })}>{plans.map((plan) => <option key={plan}>{plan}</option>)}</select></label>
          <div className="inline-fields">
            <label>Usuarios<input type="number" min="1" value={form.limiteUsuarios} onChange={(event) => setForm({ ...form, limiteUsuarios: Number(event.target.value) })} /></label>
            <label>Storage MB<input type="number" min="1" value={form.limiteArmazenamentoMb} onChange={(event) => setForm({ ...form, limiteArmazenamentoMb: Number(event.target.value) })} /></label>
          </div>
          <ModulePicker value={form.modulosHabilitados} onChange={(modules) => setForm({ ...form, modulosHabilitados: modules })} />
          <button className="primary-button" type="submit"><Plus size={18} /> Cadastrar</button>
        </form>

        <section>
          <div className="list-toolbar">
            <select value={selectedTenantId} onChange={(event) => selectTenant(event.target.value)}>
              <option value="">Selecionar gabinete</option>
              {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.nome}</option>)}
            </select>
          </div>
          <div className="tenant-list">
            {tenants.map((tenant) => (
              <article className="tenant-row" key={tenant.id}>
                <div>
                  <strong>{tenant.nome}</strong>
                  <small>{tenant.slug} · {tenant.plano} · {tenant.contrato}</small>
                </div>
                <button className="secondary-button" type="button" onClick={() => selectTenant(tenant.id)}>Editar</button>
              </article>
            ))}
          </div>
          {selectedTenant && (
            <div className="usage-panel">
              <h3>Contrato e modulos</h3>
              <form className="compact-form compact-form-flat" onSubmit={transitionContract}>
                <label>Status contratual
                  <select
                    value={contractForm.contrato}
                    onChange={(event) => setContractForm({ ...contractForm, contrato: event.target.value })}
                  >
                    <option value="trial">trial</option>
                    <option value="active">active</option>
                    <option value="suspended">suspended</option>
                    <option value="cancelled">cancelled</option>
                  </select>
                </label>
                <label>Motivo
                  <textarea
                    value={contractForm.motivo}
                    onChange={(event) => setContractForm({ ...contractForm, motivo: event.target.value })}
                    required
                    rows={3}
                  />
                </label>
                <button className="primary-button" type="submit"><Save size={18} /> Registrar contrato</button>
              </form>
              <div className="module-editor">
                <ModulePicker
                  value={moduleDraft.length ? moduleDraft : selectedTenant.modulosHabilitados}
                  onChange={setModuleDraft}
                />
                <button className="secondary-button" type="button" onClick={saveModules}>Salvar modulos</button>
              </div>
            </div>
          )}
          {usage && (
            <div className="usage-panel">
              <h3>Consumo sem dados sensiveis</h3>
              <KeyValueRows rows={usage.consumo} />
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function SettingsPanel({ settings, onRefresh, onNotice }) {
  const [form, setForm] = useState({ tipo: "PARAMETER", chave: "", nome: "", valor: "{}" });

  async function saveSetting(event) {
    event.preventDefault();
    await apiRequest("/api/v1/platform/configuracoes", {
      method: "POST",
      body: JSON.stringify({ ...form, valor: JSON.parse(form.valor || "{}") }),
    });
    setForm({ tipo: "PARAMETER", chave: "", nome: "", valor: "{}" });
    onNotice("Configuracao global salva.");
    await onRefresh();
  }

  return (
    <section className="page-section">
      <p className="eyebrow">Parametros, modelos e provedores</p>
      <h2>Configuracoes globais</h2>
      <div className="platform-columns">
        <form className="compact-form" onSubmit={saveSetting}>
          <label>Tipo<select value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{settingTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
          <label>Chave<input value={form.chave} onChange={(event) => setForm({ ...form, chave: event.target.value })} required /></label>
          <label>Nome<input value={form.nome} onChange={(event) => setForm({ ...form, nome: event.target.value })} /></label>
          <label>Valor JSON<textarea value={form.valor} onChange={(event) => setForm({ ...form, valor: event.target.value })} rows={5} /></label>
          <button className="primary-button" type="submit"><Save size={18} /> Salvar</button>
        </form>
        <div className="tenant-list">
          {settings.map((item) => (
            <article className="tenant-row" key={item.id}>
              <div>
                <strong>{item.nome}</strong>
                <small>{item.tipo} · {item.chave}</small>
              </div>
              <span className={item.ativo ? "status-pill success" : "status-pill"}>{item.ativo ? "ativo" : "inativo"}</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function SupportPanel({ tenants, supportAccesses, onRefresh, onNotice }) {
  const [form, setForm] = useState({ tenantId: "", solicitadoPor: "", autorizadoPor: "", motivo: "", escopo: "" });

  async function saveSupport(event) {
    event.preventDefault();
    await apiRequest("/api/v1/platform/suporte", { method: "POST", body: JSON.stringify(form) });
    setForm({ tenantId: "", solicitadoPor: "", autorizadoPor: "", motivo: "", escopo: "" });
    onNotice("Acesso de suporte registrado em auditoria.");
    await onRefresh();
  }

  return (
    <section className="page-section">
      <p className="eyebrow">Suporte com justificativa</p>
      <h2>Acessos excepcionais</h2>
      <div className="platform-columns">
        <form className="compact-form" onSubmit={saveSupport}>
          <label>Gabinete<select value={form.tenantId} onChange={(event) => setForm({ ...form, tenantId: event.target.value })} required><option value="">Selecionar</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.nome}</option>)}</select></label>
          <label>Solicitado por<input value={form.solicitadoPor} onChange={(event) => setForm({ ...form, solicitadoPor: event.target.value })} required /></label>
          <label>Autorizado por<input value={form.autorizadoPor} onChange={(event) => setForm({ ...form, autorizadoPor: event.target.value })} /></label>
          <label>Escopo<input value={form.escopo} onChange={(event) => setForm({ ...form, escopo: event.target.value })} required /></label>
          <label>Motivo<textarea value={form.motivo} onChange={(event) => setForm({ ...form, motivo: event.target.value })} required /></label>
          <button className="primary-button" type="submit"><ShieldCheck size={18} /> Registrar</button>
        </form>
        <div className="tenant-list">
          {supportAccesses.map((item) => (
            <article className="tenant-row" key={item.id}>
              <div>
                <strong>{item.escopo}</strong>
                <small>{item.solicitadoPor} · {item.status} · {new Date(item.criadoEm).toLocaleString("pt-BR")}</small>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function AuditPanel({ audit }) {
  return (
    <section className="page-section">
      <p className="eyebrow">Trilha administrativa</p>
      <h2>Auditoria da plataforma</h2>
      <div className="tenant-list">
        {audit.map((item) => (
          <article className="tenant-row" key={item.id}>
            <div>
              <strong>{item.acao}</strong>
              <small>{item.entidade} · {item.entidadeId || "sem entidade"} · {new Date(item.criadoEm).toLocaleString("pt-BR")}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }) {
  return <article className="metric-card"><span>{label}</span><strong>{value ?? 0}</strong></article>;
}

function KeyValueRows({ rows }) {
  return (
    <div className="key-value-list">
      {Object.entries(rows).map(([key, value]) => (
        <p key={key}><span>{key}</span><strong>{value}</strong></p>
      ))}
    </div>
  );
}

function ModulePicker({ value, onChange }) {
  function toggle(module) {
    onChange(value.includes(module) ? value.filter((item) => item !== module) : [...value, module]);
  }
  return (
    <fieldset className="module-picker">
      <legend>Modulos habilitados</legend>
      {availableModules.map((module) => (
        <label key={module}>
          <input type="checkbox" checked={value.includes(module)} onChange={() => toggle(module)} />
          {module}
        </label>
      ))}
    </fieldset>
  );
}
