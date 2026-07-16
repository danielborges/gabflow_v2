import {
  CheckCircle2,
  Download,
  FileClock,
  History,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiDownload, apiRequest } from "../api";

const tabs = [
  ["requests", "Direitos do titular"],
  ["retention", "Retenção"],
  ["audit", "Auditoria"],
];

export function PrivacyGovernancePage() {
  const [active, setActive] = useState("requests");
  const [summary, setSummary] = useState(null);
  const [privacyRequests, setPrivacyRequests] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [audits, setAudits] = useState([]);
  const [citizens, setCitizens] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [summaryData, requestData, policyData, auditData, citizenData] =
        await Promise.all([
          apiRequest("/api/v1/privacidade/resumo"),
          apiRequest("/api/v1/privacidade/solicitacoes"),
          apiRequest("/api/v1/privacidade/retencao"),
          apiRequest("/api/v1/auditoria?size=50"),
          apiRequest("/api/v1/cidadaos"),
        ]);
      setSummary(summaryData);
      setPrivacyRequests(requestData.content);
      setPolicies(policyData.content);
      setAudits(auditData.content);
      setCitizens(citizenData.content);
    } catch (requestError) {
      setError(requestError.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return <>
    <section className="page-heading">
      <div><p className="eyebrow">LGPD e governança</p><h1>Privacidade</h1><p>Direitos do titular, retenção e rastreabilidade administrativa.</p></div>
    </section>
    {summary && <section className="privacy-metrics">
      <Metric icon={FileClock} value={summary.solicitacoesAbertas} label="Solicitações abertas" />
      <Metric icon={FileClock} value={summary.solicitacoesVencidas} label="Solicitações vencidas" tone="danger" />
      <Metric icon={ShieldCheck} value={summary.cidadaosAtivos} label="Titulares ativos" />
      <Metric icon={History} value={summary.politicasAtivas} label="Políticas ativas" />
    </section>}
    <section className="admin-tabs segmented-control">
      {tabs.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>{label}</button>)}
    </section>
    {error && <p className="form-error privacy-error">{error}</p>}
    {active === "requests" && <PrivacyRequests items={privacyRequests} citizens={citizens} onChanged={load} />}
    {active === "retention" && <RetentionPolicies items={policies} onChanged={load} />}
    {active === "audit" && <AuditTrail items={audits} />}
  </>;
}

function Metric({ icon: Icon, value, label, tone = "" }) {
  return <article className={tone}><Icon size={20} /><div><strong>{value}</strong><span>{label}</span></div></article>;
}

function PrivacyRequests({ items, citizens, onChanged }) {
  const [form, setForm] = useState({
    cidadaoId: "",
    tipo: "ACESSO",
    detalhes: "",
    identidadeValidada: false,
    prazoDias: 15,
  });
  const [resolution, setResolution] = useState({});

  async function submit(event) {
    event.preventDefault();
    await apiRequest("/api/v1/privacidade/solicitacoes", {
      method: "POST",
      body: JSON.stringify({ ...form, prazoDias: Number(form.prazoDias) }),
    });
    setForm({ cidadaoId: "", tipo: "ACESSO", detalhes: "", identidadeValidada: false, prazoDias: 15 });
    onChanged();
  }

  async function conclude(item) {
    await apiRequest(`/api/v1/privacidade/solicitacoes/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: "CONCLUIDA",
        identidadeValidada: true,
        resolucao: resolution[item.id] || "Solicitação atendida e conferida.",
      }),
    });
    onChanged();
  }

  async function exportData(item) {
    const blob = await apiDownload(
      `/api/v1/privacidade/solicitacoes/${item.id}/exportar`,
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `dados-titular-${item.cidadaoId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return <section className="privacy-layout">
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-title"><ShieldCheck size={21} /><div><strong>Nova solicitação</strong><small>Registre a demanda e valide a identidade do solicitante.</small></div></div>
      <label>Cidadão<select required value={form.cidadaoId} onChange={(event) => setForm((current) => ({ ...current, cidadaoId: event.target.value }))}><option value="">Selecione</option>{citizens.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
      <div className="form-grid">
        <label>Direito<select value={form.tipo} onChange={(event) => setForm((current) => ({ ...current, tipo: event.target.value }))}><option value="ACESSO">Acesso aos dados</option><option value="CORRECAO">Correção</option><option value="ANONIMIZACAO">Anonimização</option><option value="REVOGACAO_CONSENTIMENTO">Revogação de consentimento</option></select></label>
        <label>Prazo interno (dias)<input type="number" min="1" max="365" value={form.prazoDias} onChange={(event) => setForm((current) => ({ ...current, prazoDias: event.target.value }))} /></label>
      </div>
      <label>Detalhes<textarea required rows="4" value={form.detalhes} onChange={(event) => setForm((current) => ({ ...current, detalhes: event.target.value }))} /></label>
      <label className="checkbox-label"><input type="checkbox" checked={form.identidadeValidada} onChange={(event) => setForm((current) => ({ ...current, identidadeValidada: event.target.checked }))} /> Identidade validada</label>
      <button className="primary-button compact"><Plus size={17} /> Registrar</button>
    </form>
    <div className="privacy-request-list">
      {items.map((item) => <article key={item.id} className={item.vencida ? "overdue" : ""}>
        <header><div><strong>{item.cidadao}</strong><small>{requestTypeLabel(item.tipo)} · prazo {formatDate(item.prazo)}</small></div><span className={`status-badge status-${item.status.toLowerCase()}`}>{statusLabel(item.status)}</span></header>
        <p>{item.detalhes}</p>
        {item.status !== "CONCLUIDA" && item.status !== "REJEITADA" && <div className="privacy-actions">
          <input value={resolution[item.id] || ""} onChange={(event) => setResolution((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Resolução adotada" />
          <button className="secondary-button" onClick={() => conclude(item)}><CheckCircle2 size={16} /> Concluir</button>
        </div>}
        {item.tipo === "ACESSO" && item.identidadeValidada && <button className="text-action" onClick={() => exportData(item)}><Download size={16} /> Exportar dados</button>}
      </article>)}
      {items.length === 0 && <div className="table-message">Nenhuma solicitação de privacidade.</div>}
    </div>
  </section>;
}

function RetentionPolicies({ items, onChanged }) {
  const [form, setForm] = useState({ tipoDado: "CIDADAO", retencaoDias: 1825, acao: "REVISAR", ativa: true });
  async function submit(event) {
    event.preventDefault();
    await apiRequest("/api/v1/privacidade/retencao", {
      method: "PUT",
      body: JSON.stringify({ ...form, retencaoDias: Number(form.retencaoDias) }),
    });
    onChanged();
  }
  return <section className="privacy-layout">
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-title"><FileClock size={21} /><div><strong>Política de retenção</strong><small>A execução permanece sujeita à revisão humana.</small></div></div>
      <label>Tipo de dado<select value={form.tipoDado} onChange={(event) => setForm((current) => ({ ...current, tipoDado: event.target.value }))}><option value="CIDADAO">Cidadãos</option><option value="ANEXO">Anexos</option><option value="AUDITORIA">Auditoria</option></select></label>
      <label>Retenção em dias<input type="number" min="30" max="36500" value={form.retencaoDias} onChange={(event) => setForm((current) => ({ ...current, retencaoDias: event.target.value }))} /></label>
      <label>Ação ao vencer<select value={form.acao} onChange={(event) => setForm((current) => ({ ...current, acao: event.target.value }))}><option value="REVISAR">Revisar</option><option value="ANONIMIZAR">Sugerir anonimização</option></select></label>
      <label className="checkbox-label"><input type="checkbox" checked={form.ativa} onChange={(event) => setForm((current) => ({ ...current, ativa: event.target.checked }))} /> Política ativa</label>
      <button className="primary-button compact">Salvar política</button>
    </form>
    <div className="policy-list">{items.map((item) => <article key={item.id}><FileClock size={19} /><div><strong>{dataTypeLabel(item.tipoDado)}</strong><small>{item.retencaoDias} dias · {item.acao === "REVISAR" ? "Revisão humana" : "Sugerir anonimização"}</small></div><span>{item.ativa ? "Ativa" : "Inativa"}</span></article>)}</div>
  </section>;
}

function AuditTrail({ items }) {
  return <section className="audit-table"><div className="table-scroll"><table><thead><tr><th>Data</th><th>Usuário</th><th>Ação</th><th>Entidade</th><th>IP</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{formatDate(item.criadaEm)}</td><td>{item.usuario}</td><td><strong>{item.acao}</strong></td><td>{item.entidade}</td><td>{item.ip || "-"}</td></tr>)}</tbody></table></div></section>;
}

function requestTypeLabel(value) {
  return { ACESSO: "Acesso", CORRECAO: "Correção", ANONIMIZACAO: "Anonimização", REVOGACAO_CONSENTIMENTO: "Revogação" }[value] || value;
}
function statusLabel(value) {
  return { ABERTA: "Aberta", EM_ANALISE: "Em análise", CONCLUIDA: "Concluída", REJEITADA: "Rejeitada" }[value] || value;
}
function dataTypeLabel(value) {
  return { CIDADAO: "Cidadãos", ANEXO: "Anexos", AUDITORIA: "Auditoria" }[value] || value;
}
function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
