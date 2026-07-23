import {
  Activity,
  ArrowUpDown,
  Building2,
  CalendarCheck,
  ClipboardList,
  CreditCard,
  FileText,
  Gauge,
  History,
  LifeBuoy,
  LockKeyhole,
  LogOut,
  PhoneCall,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  UserPlus,
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

const plans = ["starter", "professional", "premium"];
const planUserLimits = { starter: 5, professional: 15, premium: 9999 };
const leadStatuses = [
  ["new", "Novo"],
  ["contacting", "Em contato"],
  ["proposal_sent", "Proposta enviada"],
  ["contract_negotiation", "Contrato em negociação"],
  ["payment_pending", "Pagamento pendente"],
  ["onboarding_scheduled", "Onboarding agendado"],
  ["converted", "Convertido"],
  ["lost", "Perdido"],
];
const paymentStatuses = [
  ["pending", "Pendente"],
  ["invoice_sent", "Cobrança enviada"],
  ["paid", "Pago"],
  ["overdue", "Em atraso"],
  ["cancelled", "Cancelado"],
];
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
  const [contractingInterests, setContractingInterests] = useState([]);
  const [settings, setSettings] = useState([]);
  const [supportAccesses, setSupportAccesses] = useState([]);
  const [audit, setAudit] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [usage, setUsage] = useState(null);
  const [notice, setNotice] = useState("");

  const loadPlatformData = useCallback(async () => {
    const [overviewData, tenantsData, interestsData, settingsData, supportData, auditData] = await Promise.all([
      apiRequest("/api/v1/platform/overview"),
      apiRequest("/api/v1/platform/gabinetes"),
      apiRequest("/api/v1/platform/interesses-contratacao"),
      apiRequest("/api/v1/platform/configuracoes"),
      apiRequest("/api/v1/platform/suporte"),
      apiRequest("/api/v1/platform/auditoria"),
    ]);
    setOverview(overviewData);
    setTenants(tenantsData.content || []);
    setContractingInterests(interestsData.content || []);
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
        <nav aria-label="Administração da plataforma">
          <PlatformNav active={activeView} id="overview" label="Painel" icon={Gauge} onClick={setActiveView} />
          <PlatformNav active={activeView} id="interests" label="Interesses em Contratação" icon={ClipboardList} onClick={setActiveView} />
          <PlatformNav active={activeView} id="tenants" label="Gabinetes" icon={Building2} onClick={setActiveView} />
          <PlatformNav active={activeView} id="settings" label="Configurações" icon={Settings2} onClick={setActiveView} />
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
            <h1 className="compact-title">Administração Geral</h1>
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
        {activeView === "interests" && (
          <ContractingInterestsPanel
            interests={contractingInterests}
            onRefresh={loadPlatformData}
            onNotice={setNotice}
          />
        )}
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
      <h2>Saúde da plataforma</h2>
      <div className="metric-grid">
        <Metric label="Gabinetes" value={totals.gabinetes} />
        <Metric label="Usuários" value={totals.usuarios} />
        <Metric label="Solicitações" value={totals.solicitacoes} />
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

function ContractingInterestsPanel({ interests, onRefresh, onNotice }) {
  const [selectedId, setSelectedId] = useState(interests[0]?.id || "");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState({ key: "criadoEm", direction: "desc" });
  const [activeAction, setActiveAction] = useState("contact");
  const [form, setForm] = useState(defaultInterestForm());
  const selected = interests.find((item) => item.id === selectedId) || interests[0];

  useEffect(() => {
    if (!selected) return;
    setSelectedId(selected.id);
    setForm(defaultInterestForm(selected));
  }, [selected]);

  const visibleInterests = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return interests
      .filter((item) => !statusFilter || item.status === statusFilter)
      .filter((item) => {
        if (!normalizedQuery) return true;
        return [item.nomeGabinete, item.administradorGabinete, item.email, item.municipio, item.estado, item.plano, statusLabel(item.status, leadStatuses)]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedQuery));
      })
      .sort((left, right) => compareInterest(left, right, sort));
  }, [interests, query, statusFilter, sort]);

  const groupedInterests = useMemo(() => visibleInterests.reduce((groups, item) => {
    const jurisdiction = `${item.municipio || "Sem município"}/${item.estado || "UF"}`;
    groups[jurisdiction] = [...(groups[jurisdiction] || []), item];
    return groups;
  }, {}), [visibleInterests]);

  function sortBy(key) {
    setSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
  }

  async function submitAction(event) {
    event.preventDefault();
    if (!selected) return;
    const payload = { status: form.status, pagamento: form.pagamento, dataOnboarding: form.dataOnboarding || null, observacoesContrato: form.observacoesContrato };
    if (activeAction === "contact" && form.tentativaObservacao.trim()) payload.tentativaContato = { canal: form.tentativaCanal, resultado: form.tentativaResultado, observacao: form.tentativaObservacao };
    if (activeAction === "document" && form.documentoNome.trim()) payload.documentoContrato = { tipo: form.documentoTipo, nome: form.documentoNome, url: form.documentoUrl, observacao: form.documentoObservacao };
    if (activeAction === "contract") { payload.gerarContrato = true; payload.status = "contract_negotiation"; }
    if (activeAction === "payment" && form.pagamentoValor) payload.pagamentoItem = { tipo: form.pagamentoTipo, status: form.pagamentoItemStatus, valor: form.pagamentoValor, vencimento: form.pagamentoVencimento, observacao: form.pagamentoObservacao };
    if (activeAction === "onboarding" && form.onboardingData) { payload.onboarding = { data: form.onboardingData, local: form.onboardingLocal, tecnicoResponsavel: form.tecnicoResponsavel, observacao: form.onboardingObservacao }; payload.status = "onboarding_scheduled"; }
    await apiRequest(`/api/v1/platform/interesses-contratacao/${selected.id}`, { method: "PATCH", body: JSON.stringify(payload) });
    onNotice("Funil comercial atualizado.");
    await onRefresh();
  }

  async function convertToTenant(target = selected) {
    if (!target) return;
    const slug = window.prompt("Slug do gabinete contratado", slugifyClient(target.nomeGabinete));
    if (!slug) return;
    await apiRequest(`/api/v1/platform/interesses-contratacao/${target.id}/converter`, { method: "POST", body: JSON.stringify({ slug, plano: target.plano, observacoesContrato: form.observacoesContrato }) });
    onNotice("Interesse convertido em gabinete contratado.");
    await onRefresh();
  }

  return (
    <section className="page-section contracting-page">
      <p className="eyebrow">Funil comercial</p>
      <div className="section-title-row">
        <h2>Interesses em Contratação</h2>
        <span className="status-pill">SLA: primeiro contato em até 24h</span>
      </div>
      <div className="contracting-toolbar">
        <label>Pesquisar<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Gabinete, cidade, e-mail, plano..." /></label>
        <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">Todos</option>{leadStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      <div className="contracting-datatable">
        <table>
          <thead>
            <tr>
              <th><button type="button" onClick={() => sortBy("nomeGabinete")}>Gabinete <ArrowUpDown size={14} /></button></th>
              <th><button type="button" onClick={() => sortBy("plano")}>Plano <ArrowUpDown size={14} /></button></th>
              <th><button type="button" onClick={() => sortBy("status")}>Status <ArrowUpDown size={14} /></button></th>
              <th><button type="button" onClick={() => sortBy("pagamento")}>Pagamento <ArrowUpDown size={14} /></button></th>
              <th><button type="button" onClick={() => sortBy("criadoEm")}>SLA <ArrowUpDown size={14} /></button></th>
              <th>Contato</th>
              <th>Ações</th>
            </tr>
          </thead>
          {Object.entries(groupedInterests).map(([jurisdiction, items]) => (
            <tbody key={jurisdiction}>
              <tr className="jurisdiction-row"><td colSpan={7}>{jurisdiction} <span>{items.length} proposta(s)</span></td></tr>
              {items.map((item) => (
                <tr key={item.id} className={selected?.id === item.id ? "selected" : ""}>
                  <td><strong>{item.nomeGabinete}</strong><small>{item.administradorGabinete}</small></td>
                  <td>{item.plano}</td>
                  <td><span className="status-pill">{statusLabel(item.status, leadStatuses)}</span></td>
                  <td>{statusLabel(item.pagamento, paymentStatuses)}</td>
                  <td><span className={slaState(item) === "overdue" ? "sla-pill overdue" : "sla-pill"}>{slaLabel(item)}</span></td>
                  <td><small>{item.email}</small><small>{item.whatsapp || item.telefone}</small></td>
                  <td><div className="row-actions"><button type="button" title="Abrir proposta" onClick={() => setSelectedId(item.id)}><ClipboardList size={15} /></button><button type="button" title="Contatos realizados" onClick={() => { setSelectedId(item.id); setActiveAction("contact"); }}><PhoneCall size={15} /></button><button type="button" title="Transformar em gabinete" disabled={Boolean(item.tenantConvertidoId)} onClick={() => { setSelectedId(item.id); convertToTenant(item); }}><UserPlus size={15} /></button></div></td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
        {!visibleInterests.length && <p className="muted empty-grid-message">Nenhuma proposta encontrada.</p>}
      </div>
      {selected && (
        <form className="compact-form contracting-action-panel" onSubmit={submitAction}>
          <header><div><h3>{selected.nomeGabinete}</h3><p>{selected.municipio}/{selected.estado} · {selected.email}</p></div><button className="secondary-button" type="button" disabled={Boolean(selected.tenantConvertidoId)} onClick={convertToTenant}><UserPlus size={17} /> Transformar em gabinete</button></header>
          <div className="action-tabs">
            <button type="button" className={activeAction === "contact" ? "active" : ""} onClick={() => setActiveAction("contact")}><PhoneCall size={16} /> Contatos</button>
            <button type="button" className={activeAction === "document" ? "active" : ""} onClick={() => setActiveAction("document")}><FileText size={16} /> Documentos</button>
            <button type="button" className={activeAction === "contract" ? "active" : ""} onClick={() => setActiveAction("contract")}><FileText size={16} /> Gerar contrato</button>
            <button type="button" className={activeAction === "payment" ? "active" : ""} onClick={() => setActiveAction("payment")}><CreditCard size={16} /> Pagamentos</button>
            <button type="button" className={activeAction === "onboarding" ? "active" : ""} onClick={() => setActiveAction("onboarding")}><CalendarCheck size={16} /> Onboarding</button>
            <button type="button" className={activeAction === "history" ? "active" : ""} onClick={() => setActiveAction("history")}><History size={16} /> Histórico</button>
          </div>
          <div className="inline-fields three-fields"><label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>{leadStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Pagamento<select value={form.pagamento} onChange={(event) => setForm({ ...form, pagamento: event.target.value })}>{paymentStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Onboarding<input type="date" value={form.dataOnboarding} onChange={(event) => setForm({ ...form, dataOnboarding: event.target.value })} /></label></div>
          {activeAction === "contact" && <ContactActionForm form={form} setForm={setForm} selected={selected} />}
          {activeAction === "document" && <DocumentActionForm form={form} setForm={setForm} selected={selected} />}
          {activeAction === "contract" && <p className="contracting-notes">A ação registra uma minuta de contrato gerada para a proposta e move o funil para negociação contratual.</p>}
          {activeAction === "payment" && <PaymentActionForm form={form} setForm={setForm} selected={selected} />}
          {activeAction === "onboarding" && <OnboardingActionForm form={form} setForm={setForm} selected={selected} />}
          {activeAction === "history" && <ActionHistory selected={selected} />}
          <label>Observações contratuais<textarea rows={3} value={form.observacoesContrato} onChange={(event) => setForm({ ...form, observacoesContrato: event.target.value })} /></label>
          <button className="primary-button" type="submit"><Save size={18} /> Salvar ação do funil</button>
        </form>
      )}
    </section>
  );
}

function defaultInterestForm(selected = {}) {
  return { status: selected.status || "new", pagamento: selected.pagamento || "pending", dataOnboarding: selected.dataOnboarding || "", observacoesContrato: selected.observacoesContrato || "", tentativaCanal: "telefone", tentativaResultado: "", tentativaObservacao: "", documentoTipo: "contrato_assinado", documentoNome: "", documentoUrl: "", documentoObservacao: "", pagamentoTipo: "onboarding", pagamentoItemStatus: selected.pagamento || "pending", pagamentoValor: "", pagamentoVencimento: "", pagamentoObservacao: "", onboardingData: selected.onboarding?.data || selected.dataOnboarding || "", onboardingLocal: selected.onboarding?.local || "remota", tecnicoResponsavel: selected.onboarding?.tecnicoResponsavel || "", onboardingObservacao: selected.onboarding?.observacao || "" };
}

function ContactActionForm({ form, setForm, selected }) {
  return <fieldset className="contact-attempt-box"><legend>Contatos realizados</legend><div className="inline-fields"><label>Canal<select value={form.tentativaCanal} onChange={(event) => setForm({ ...form, tentativaCanal: event.target.value })}><option value="email">E-mail</option><option value="telefone">Telefone</option><option value="whatsapp">WhatsApp</option></select></label><label>Resultado<input value={form.tentativaResultado} onChange={(event) => setForm({ ...form, tentativaResultado: event.target.value })} placeholder="Ex.: reunião marcada" /></label></div><label>Observações<textarea rows={2} value={form.tentativaObservacao} onChange={(event) => setForm({ ...form, tentativaObservacao: event.target.value })} /></label><Timeline title="Histórico de contatos" items={selected.tentativasContato} /></fieldset>;
}

function DocumentActionForm({ form, setForm, selected }) {
  return <fieldset className="contact-attempt-box"><legend>Cadastrar documentos</legend><div className="inline-fields three-fields"><label>Tipo<select value={form.documentoTipo} onChange={(event) => setForm({ ...form, documentoTipo: event.target.value })}><option value="contrato_assinado">Contrato assinado</option><option value="documento_comercial">Documento comercial</option></select></label><label>Nome<input value={form.documentoNome} onChange={(event) => setForm({ ...form, documentoNome: event.target.value })} /></label><label>URL/Referência<input value={form.documentoUrl} onChange={(event) => setForm({ ...form, documentoUrl: event.target.value })} /></label></div><label>Observações<textarea rows={2} value={form.documentoObservacao} onChange={(event) => setForm({ ...form, documentoObservacao: event.target.value })} /></label><Timeline title="Documentos cadastrados" items={selected.documentosContrato} labelKey="nome" /></fieldset>;
}

function PaymentActionForm({ form, setForm, selected }) {
  return <fieldset className="contact-attempt-box"><legend>Pagamentos</legend><div className="inline-fields three-fields"><label>Tipo<select value={form.pagamentoTipo} onChange={(event) => setForm({ ...form, pagamentoTipo: event.target.value })}><option value="onboarding">Onboarding</option><option value="mensalidade">Mensalidade</option></select></label><label>Status<select value={form.pagamentoItemStatus} onChange={(event) => setForm({ ...form, pagamentoItemStatus: event.target.value })}>{paymentStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Valor<input type="number" min="0" step="0.01" value={form.pagamentoValor} onChange={(event) => setForm({ ...form, pagamentoValor: event.target.value })} /></label></div><div className="inline-fields"><label>Vencimento<input type="date" value={form.pagamentoVencimento} onChange={(event) => setForm({ ...form, pagamentoVencimento: event.target.value })} /></label><label>Observação<input value={form.pagamentoObservacao} onChange={(event) => setForm({ ...form, pagamentoObservacao: event.target.value })} /></label></div><Timeline title="Histórico de pagamentos" items={selected.pagamentos} labelKey="tipo" /></fieldset>;
}

function OnboardingActionForm({ form, setForm, selected }) {
  return <fieldset className="contact-attempt-box"><legend>Agendar e controlar onboarding</legend><div className="inline-fields three-fields"><label>Data<input type="date" value={form.onboardingData} onChange={(event) => setForm({ ...form, onboardingData: event.target.value })} /></label><label>Local<select value={form.onboardingLocal} onChange={(event) => setForm({ ...form, onboardingLocal: event.target.value })}><option value="remota">Remota</option><option value="presencial">Presencial</option></select></label><label>Técnico responsável<input value={form.tecnicoResponsavel} onChange={(event) => setForm({ ...form, tecnicoResponsavel: event.target.value })} /></label></div><label>Observações<textarea rows={2} value={form.onboardingObservacao} onChange={(event) => setForm({ ...form, onboardingObservacao: event.target.value })} /></label>{selected.onboarding?.data && <p className="contracting-notes">Onboarding atual: {selected.onboarding.data} · {selected.onboarding.local} · {selected.onboarding.tecnicoResponsavel || "sem técnico"}</p>}</fieldset>;
}

function ActionHistory({ selected }) { return <Timeline title="Histórico das ações realizadas" items={selected.historicoAcoes} labelKey="acao" />; }

function Timeline({ title, items = [], labelKey = "resultado" }) {
  return items.length ? <div className="contact-attempt-history"><strong>{title}</strong>{items.map((item, index) => <p key={`${item.registradoEm}-${index}`}><span>{item.registradoEm} · {item[labelKey] || item.status || item.tipo}</span>{item.observacao || item.dados?.observacao || item.nome || item.acao}</p>)}</div> : <p className="muted">Sem registros.</p>;
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
    limiteArmazenamentoMb: 1024,
    modulosHabilitados: ["solicitacoes", "cidadaos", "canais"],
  });
  const [contractForm, setContractForm] = useState({ contrato: "active", motivo: "" });
  const [moduleDraft, setModuleDraft] = useState([]);

  async function createTenant(event) {
    event.preventDefault();
    const payload = {
      nome: form.nome,
      slug: form.slug,
      plano: form.plano,
      limiteArmazenamentoMb: form.limiteArmazenamentoMb,
      modulosHabilitados: form.modulosHabilitados,
    };
    await apiRequest("/api/v1/platform/gabinetes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
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
            <label>Limite do plano<input value={planUserLimits[form.plano].toLocaleString("pt-BR")} disabled /></label>
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
    onNotice("Configuração global salva.");
    await onRefresh();
  }

  return (
    <section className="page-section">
      <p className="eyebrow">Parametros, modelos e provedores</p>
      <h2>Configurações globais</h2>
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

function statusLabel(value, options) {
  return options.find(([key]) => key === value)?.[1] || value || "-";
}

function compareInterest(left, right, sort) {
  const leftValue = left[sort.key] || "";
  const rightValue = right[sort.key] || "";
  const result = String(leftValue).localeCompare(String(rightValue), "pt-BR", { numeric: true });
  return sort.direction === "asc" ? result : -result;
}

function slaState(item) {
  if (["converted", "lost"].includes(item.status)) return "closed";
  const createdAt = item.criadoEm ? new Date(item.criadoEm).getTime() : Date.now();
  const firstContact = (item.tentativasContato || []).length > 0;
  const hours = (Date.now() - createdAt) / 36e5;
  return !firstContact && hours > 24 ? "overdue" : "ok";
}

function slaLabel(item) {
  if ((item.tentativasContato || []).length > 0) return "Atendido";
  const createdAt = item.criadoEm ? new Date(item.criadoEm).getTime() : Date.now();
  const remaining = Math.ceil(24 - ((Date.now() - createdAt) / 36e5));
  return remaining < 0 ? `${Math.abs(remaining)}h atrasado` : `${remaining}h restantes`;
}

function slugifyClient(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
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

