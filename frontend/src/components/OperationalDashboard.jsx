import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Download,
  FileCheck2,
  FileText,
  Forward,
  ListTodo,
  MapPin,
  MapPinned,
  MessageSquareReply,
  Repeat2,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
  UserMinus,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiDownload, apiRequest } from "../api";
import { TerritorialMap } from "./TerritorialMap";

const statusLabels = {
  NOVA: "Nova",
  TRIAGEM: "Em triagem",
  EM_ATENDIMENTO: "Em atendimento",
  AGUARDANDO_ORGAO: "Aguardando órgão",
  AGUARDANDO_CIDADAO: "Aguardando cidadão",
  RESOLVIDA: "Resolvida",
  ENCERRADA: "Encerrada",
  CANCELADA: "Cancelada",
};

const defaultPeriod = dashboardDefaultPeriod();
const emptyTerritorialRows = [];
const defaultDashboardFilters = {
  inicio: defaultPeriod.inicio,
  fim: defaultPeriod.fim,
  categoria: "",
  canal: "",
  territorioId: "",
  orgaoId: "",
  granularidade: "dia",
};

export function OperationalDashboard({ user, onOpenRequests, onOpenRequest }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [activePanel, setActivePanel] = useState("operation");
  const [filters, setFilters] = useState(defaultDashboardFilters);
  const [savedViews, setSavedViews] = useState([]);
  const [savedViewName, setSavedViewName] = useState("");
  const [savedViewError, setSavedViewError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      const query = params.toString();
      setData(await apiRequest(`/api/v1/painel/operacional${query ? `?${query}` : ""}`));
    } catch (requestError) {
      setError(requestError.message);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    apiRequest("/api/v1/painel/territorial/visoes")
      .then((response) => setSavedViews(response.content || []))
      .catch(() => setSavedViews([]));
  }, []);

  async function geocodePending() {
    setGeocoding(true);
    setError("");
    try {
      recordTerritorialMetric("ACAO_INICIADA", filters);
      await apiRequest("/api/v1/painel/territorial/geocodificar", { method: "POST" });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setGeocoding(false);
    }
  }

  function openTerritorialPanel() {
    setActivePanel("territorial");
    recordTerritorialMetric("ABA_ABERTA", filters);
  }

  function changeFilters(nextFilters) {
    setFilters(nextFilters);
    if (activePanel === "territorial") {
      recordTerritorialMetric("FILTRO_APLICADO", nextFilters);
    }
  }

  async function saveCurrentView() {
    if (!savedViewName.trim()) return;
    setSavedViewError("");
    try {
      const saved = await apiRequest("/api/v1/painel/territorial/visoes", {
        method: "POST",
        body: JSON.stringify({ nome: savedViewName.trim(), filtros: filters }),
      });
      setSavedViews((current) => [
        ...current.filter((item) => item.id !== saved.id),
        saved,
      ].sort((left, right) => left.nome.localeCompare(right.nome)));
      setSavedViewName("");
    } catch (requestError) {
      setSavedViewError(requestError.message);
    }
  }

  function investigateTerritory(requestFilters) {
    recordTerritorialMetric("INVESTIGACAO_INICIADA", filters);
    onOpenRequests?.(requestFilters);
  }

  if (error) return <p className="form-error dashboard-error">{error}</p>;
  if (!data) return <div className="table-message dashboard-loading">Carregando painel...</div>;

  const cards = [
    ["Abertas", data.indicadores.abertas, ListTodo, "neutral"],
    ["Atrasadas", data.indicadores.atrasadas, AlertTriangle, "danger"],
    ["Próximas do prazo", data.indicadores.proximasDoPrazo, Clock3, "warning"],
    ["Sem responsável", data.indicadores.semResponsavel, UserMinus, "warning"],
    ["Aguardando órgão", data.indicadores.aguardandoOrgao, Building2, "neutral"],
    ["Tarefas pendentes", data.indicadores.tarefasPendentes, CheckCircle2, "success"],
    ["Retornos vencidos", data.indicadores.retornosVencidos, AlertTriangle, "danger"],
    ["Retornos próximos", data.indicadores.retornosProximos, CalendarClock, "warning"],
  ];

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Operação do gabinete</p>
          <h1>Painel operacional</h1>
          <p>Prioridades, prazos e distribuição territorial das demandas em um único lugar.</p>
        </div>
      </section>
      <nav className="dashboard-tabs segmented-control" aria-label="Seções do painel operacional" role="tablist">
        <button type="button" role="tab" aria-selected={activePanel === "operation"} aria-controls="dashboard-operation-panel" className={activePanel === "operation" ? "active" : ""} onClick={() => setActivePanel("operation")}>
          <ListTodo size={17} /> Operação
        </button>
        <button type="button" role="tab" aria-selected={activePanel === "territorial"} aria-controls="dashboard-territorial-panel" className={activePanel === "territorial" ? "active" : ""} onClick={openTerritorialPanel}>
          <MapPinned size={17} /> Inteligência territorial
        </button>
        <button type="button" role="tab" aria-selected={activePanel === "report"} aria-controls="dashboard-report-panel" className={activePanel === "report" ? "active" : ""} onClick={() => setActivePanel("report")}>
          <FileText size={17} /> Relatórios
        </button>
      </nav>
      <section
        id={`dashboard-${activePanel}-panel`}
        className="dashboard-tab-panel"
        role="tabpanel"
        aria-label={activePanel === "operation" ? "Operação" : activePanel === "territorial" ? "Inteligência territorial" : "Relatórios"}
      >
      {activePanel === "operation" && <>
        <DashboardFilters
          filters={filters}
          options={data.filtros?.opcoes}
          onChange={changeFilters}
          onClear={() => setFilters(defaultDashboardFilters)}
        />
        <section className="metric-grid">
          {cards.map(([label, value, Icon, tone]) => (
            <article key={label} className={`metric-${tone}`}>
              <Icon size={20} />
              <div><strong>{value}</strong><span>{label}</span></div>
            </article>
          ))}
        </section>
        <section className="dashboard-layout">
        <div className="dashboard-main">
          <OperationalMetricsPanel metrics={data.metricasOperacionais} />
          <PrivacyAggregationNotice summary={data.privacidadeAgregacao} />
          <DemandAlertsPanel alerts={data.alertasDemanda} />
          <header><div><h2>Fila prioritária</h2><p>Demandas abertas ordenadas por atraso e prazo.</p></div><button className="secondary-button" onClick={() => onOpenRequests?.()}>Ver solicitações</button></header>
          {data.filaPrioritaria.length === 0 ? <p className="muted-copy">Nenhuma demanda aberta.</p> : (
            <div className="priority-queue">
              {data.filaPrioritaria.map((item) => (
                <article key={item.id}>
                  <span className={item.atrasada ? "queue-marker overdue" : "queue-marker"} />
                  <div><strong>{item.titulo || "Sem título"}</strong><small>{item.protocolo} · {statusLabel(item.status)}</small></div>
                  <span>{item.prazo ? formatDate(item.prazo) : "Sem SLA"}</span>
                </article>
              ))}
            </div>
          )}
          <section className="dashboard-returns">
            <header><div><h2>Retornos prioritários</h2><p>Agendamentos vencidos ou próximos para acompanhamento.</p></div></header>
            {(data.retornosPrioritarios || []).length === 0 ? <p className="muted-copy">Nenhum retorno pendente.</p> : (
              <div className="priority-queue">
                {data.retornosPrioritarios.map((item) => <article key={item.id}>
                  <span className={item.vencido ? "queue-marker overdue" : "queue-marker"} />
                  <div><strong>{item.titulo || "Solicitação sem título"}</strong><small>{item.protocolo} · {item.responsavel}</small></div>
                  <span>{formatDate(item.agendadoPara)}</span>
                </article>)}
              </div>
            )}
          </section>
        </div>
        <div className="dashboard-breakdowns">
          <Breakdown title="Por status" items={data.porStatus} labelFormatter={statusLabel} />
          <Breakdown title="Por categoria" items={data.porCategoria} />
          <Breakdown title="Por território" items={data.porTerritorio} />
          <Breakdown title="Por órgão" items={data.porOrgao || []} />
          <Breakdown title="Por canal" items={data.porCanal || data.porOrigem || []} />
          <Breakdown title="Por período" items={data.porPeriodo || []} labelFormatter={periodLabel} />
        </div>
        </section>
      </>}
      {activePanel === "territorial" && (
        <>
          <TerritorialSavedViews
            items={savedViews}
            name={savedViewName}
            error={savedViewError}
            onNameChange={setSavedViewName}
            onApply={(view) => changeFilters({ ...defaultDashboardFilters, ...view.filtros })}
            onSave={saveCurrentView}
          />
          <TerritorialWorkspace
            user={user}
            data={data}
            busy={geocoding}
            onGeocode={geocodePending}
            onInvestigate={investigateTerritory}
            onOpenRequest={onOpenRequest}
          />
        </>
      )}
      {activePanel === "report" && <ReportsWorkspace />}
      </section>
    </>
  );
}

function DashboardFilters({ filters, options = {}, onChange, onClear }) {
  const update = (key, value) => onChange({ ...filters, [key]: value });
  const hasActiveFilters = Object.values(filters).some((value) => value && value !== "dia");
  return (
    <section className="dashboard-filter-panel">
      <label>Início<input type="date" value={filters.inicio} onChange={(event) => update("inicio", event.target.value)} /></label>
      <label>Fim<input type="date" value={filters.fim} onChange={(event) => update("fim", event.target.value)} /></label>
      <label>Categoria<select value={filters.categoria} onChange={(event) => update("categoria", event.target.value)}>
        <option value="">Todas</option>
        {(options.categorias || []).map((item) => <option key={item} value={item}>{item}</option>)}
      </select></label>
      <label>Canal<select value={filters.canal} onChange={(event) => update("canal", event.target.value)}>
        <option value="">Todos</option>
        {(options.canais || []).map((item) => <option key={item} value={item}>{sourceLabel(item)}</option>)}
      </select></label>
      <label>Bairro/região<select value={filters.territorioId} onChange={(event) => update("territorioId", event.target.value)}>
        <option value="">Todos</option>
        {(options.territorios || []).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
      </select></label>
      <label>Órgão<select value={filters.orgaoId} onChange={(event) => update("orgaoId", event.target.value)}>
        <option value="">Todos</option>
        {(options.orgaos || []).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
      </select></label>
      <label>Período<select value={filters.granularidade} onChange={(event) => update("granularidade", event.target.value)}>
        <option value="dia">Dia</option>
        <option value="mes">Mês</option>
      </select></label>
      <button className="secondary-button compact" disabled={!hasActiveFilters} onClick={onClear}>Limpar</button>
    </section>
  );
}

function PrivacyAggregationNotice({ summary }) {
  if (!summary?.gruposSuprimidos) return null;
  return (
    <section className="privacy-aggregation-notice">
      <ShieldCheck size={17} />
      <span>
        <strong>Agregação mínima aplicada</strong>
        <small>
          {summary.gruposSuprimidos} grupo(s) pequeno(s) ocultado(s). Gráficos exibem apenas recortes com pelo menos {summary.minimoPorGrupo} solicitações.
        </small>
      </span>
    </section>
  );
}

function TerritorialSavedViews({ items, name, error, onNameChange, onApply, onSave }) {
  return (
    <section className="territorial-saved-views">
      <label>
        Visão salva
        <select defaultValue="" onChange={(event) => {
          const view = items.find((item) => item.id === event.target.value);
          if (view) onApply(view);
        }}>
          <option value="">Selecionar visão</option>
          {items.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
        </select>
      </label>
      <label>
        Nome da visão
        <input value={name} maxLength="80" onChange={(event) => onNameChange(event.target.value)} placeholder="Ex.: Saúde — últimos 30 dias" />
      </label>
      <button className="secondary-button compact" disabled={name.trim().length < 2} onClick={onSave}>Salvar visão</button>
      {error && <p className="form-error">{error}</p>}
    </section>
  );
}

function TerritorialWorkspace({ user, data, busy, onGeocode, onInvestigate, onOpenRequest }) {
  const rows = data.territorial?.tabelaTerritorial || emptyTerritorialRows;
  const [selectedId, setSelectedId] = useState(rows[0]?.id || null);
  const [sort, setSort] = useState({ key: "total", direction: "desc" });
  const [actionData, setActionData] = useState({ content: [], page: 1, total: 0, totalPages: 1, permissoes: {} });
  const [executionMetrics, setExecutionMetrics] = useState({});
  const [territorialAlerts, setTerritorialAlerts] = useState([]);
  const [actionUsers, setActionUsers] = useState([]);
  const [actionError, setActionError] = useState("");
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [actionQuery, setActionQuery] = useState({ status: "ABERTAS", tipo: "", prazoEstado: "", q: "", page: 1, size: 10, sort: "criadaEm,desc" });
  useEffect(() => {
    if (!rows.some((item) => item.id === selectedId)) setSelectedId(rows[0]?.id || null);
  }, [rows, selectedId]);
  const selected = rows.find((item) => item.id === selectedId) || null;
  const actionableSelection = selected && !selected.semTerritorio && selected.id !== "sem-territorio";
  const loadActions = useCallback(async () => {
    if (!selectedId || selectedId === "sem-territorio") {
      setActionData({ content: [], page: 1, total: 0, totalPages: 1, permissoes: {} });
      setActionError("");
      return;
    }
    try {
      const params = new URLSearchParams({ territorioId: selectedId });
      Object.entries(actionQuery).forEach(([key, value]) => {
        if (value !== "") params.set(key, String(value));
      });
      const [response, metrics, alerts] = await Promise.all([
        apiRequest(`/api/v1/painel/territorial/acoes?${params}`),
        apiRequest(`/api/v1/painel/territorial/metricas-execucao?territorioId=${selectedId}`),
        apiRequest(`/api/v1/painel/territorial/alertas?territorioId=${selectedId}&status=ABERTOS`),
      ]);
      setActionData(response);
      setExecutionMetrics(metrics);
      setTerritorialAlerts(alerts.content || []);
      setActionUsers(response.responsaveis || []);
      setActionError("");
    } catch (requestError) {
      setActionError(requestError.message);
    }
  }, [actionQuery, selectedId]);
  useEffect(() => {
    loadActions();
  }, [loadActions]);
  const sortedRows = [...rows].sort((left, right) => {
    const leftValue = left[sort.key] ?? -Infinity;
    const rightValue = right[sort.key] ?? -Infinity;
    const result = typeof leftValue === "string"
      ? leftValue.localeCompare(rightValue)
      : Number(leftValue) - Number(rightValue);
    return sort.direction === "asc" ? result : -result;
  });
  function changeSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  }
  return (
    <section className="territorial-workspace">
      <div className="territorial-exploration-main">
        <TerritorialComparisonSummary comparison={data.territorial?.comparacao} />
        <TerritorialPanel
          data={data.territorial}
          busy={busy}
          onGeocode={onGeocode}
          selectedTerritoryId={selectedId}
          onSelectTerritory={setSelectedId}
          onOpenRequest={onOpenRequest}
          onCreateTerritorialAction={(feature) => {
            if (feature?.territorioId) setSelectedId(feature.territorioId);
            setActionModalOpen(true);
          }}
          expanded
        />
        <TerritorialTable
          rows={sortedRows}
          selectedId={selectedId}
          sort={sort}
          onSort={changeSort}
          onSelect={setSelectedId}
          onInvestigate={onInvestigate}
        />
      </div>
      <aside className="territorial-support">
        <TerritorialInvestigationPanel item={selected} onInvestigate={onInvestigate} />
        <TerritorialOperationsPanel
          data={actionData}
          error={actionError}
          query={actionQuery}
          users={actionUsers}
          user={user}
          selected={actionableSelection ? selected : null}
          metrics={executionMetrics}
          alerts={territorialAlerts}
          onCreate={() => setActionModalOpen(true)}
          onChanged={loadActions}
          onQueryChange={setActionQuery}
        />
      </aside>
      {actionModalOpen && actionableSelection && (
        <TerritorialActionModal
          item={selected}
          filters={data.filtros?.selecionados || { territorioId: selected.id }}
          users={actionUsers}
          onClose={() => setActionModalOpen(false)}
          onCreated={() => {
            setActionModalOpen(false);
            loadActions();
          }}
        />
      )}
    </section>
  );
}

function TerritorialComparisonSummary({ comparison }) {
  if (!comparison) return null;
  const available = comparison.estado === "DISPONIVEL";
  return <section className={`territorial-comparison-summary ${available ? "" : "insufficient"}`}>
    <div><strong>Comparação temporal</strong><span>{comparison.metodo === "JANELAS_EQUIVALENTES" ? "Janelas equivalentes" : comparison.metodo}</span></div>
    <div><strong>{formatPeriodRange(comparison.periodoAtual)}</strong><span>{comparison.periodoAtual?.amostra || 0} solicitações atuais</span></div>
    <div><strong>{formatPeriodRange(comparison.periodoAnterior)}</strong><span>{comparison.periodoAnterior?.amostra || 0} solicitações anteriores</span></div>
    <div><strong>{available ? formatVariation(comparison.variacaoVolumePercentual) : "Amostra insuficiente"}</strong><span>variação de volume</span></div>
  </section>;
}

function TerritorialTable({ rows, selectedId, sort, onSort, onSelect, onInvestigate }) {
  const headers = [
    ["nome", "Território"], ["total", "Volume"], ["percentualAtraso", "Atraso"],
    ["taxaSolucao", "Solução"], ["tempoMedianoPrimeiraRespostaHoras", "1ª resposta"],
    ["tempoMedianoResolucaoHoras", "Resolução"], ["tendencia", "Tendência"],
  ];
  return <section className="territorial-table-panel">
    <header><div><h2>Tabela territorial</h2><p>Alternativa acessível ao mapa, com o mesmo recorte e seleção.</p></div></header>
    {!rows.length ? <p className="muted-copy">Amostra insuficiente para comparar territórios.</p> : <div className="table-scroll">
      <table className="territorial-table">
        <colgroup>
          <col className="territorial-column-name" />
          <col className="territorial-column-volume" />
          <col className="territorial-column-percentage" />
          <col className="territorial-column-percentage" />
          <col className="territorial-column-response" />
          <col className="territorial-column-resolution" />
          <col className="territorial-column-trend" />
          <col className="territorial-column-action" />
        </colgroup>
        <thead><tr>{headers.map(([key, label]) => <th key={key} aria-sort={sort.key === key ? sort.direction : "none"}><button onClick={() => onSort(key)}>{label}</button></th>)}<th>Ação</th></tr></thead>
        <tbody>{rows.map((item) => <tr key={item.id} className={item.id === selectedId ? "selected" : ""} tabIndex="0" onClick={() => onSelect(item.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(item.id); }}>
          <td><span className="territorial-name-cell"><strong>{item.nome}</strong><small>{formatPercent(item.qualidadeGeograficaPercentual)} com localização</small></span></td>
          <td>{item.total}</td><td>{formatPercent(item.percentualAtraso)}</td><td>{formatPercent(item.taxaSolucao)}</td>
          <td>{formatHours(item.tempoMedianoPrimeiraRespostaHoras)}</td><td>{formatHours(item.tempoMedianoResolucaoHoras)}</td>
          <td><TrendBadge item={item} /></td>
          <td><button className="secondary-button compact" onClick={(event) => { event.stopPropagation(); onInvestigate(item.filtroSolicitacoes); }}>Ver solicitações</button></td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>;
}

function TrendBadge({ item }) {
  if (item.comparacao?.estado !== "DISPONIVEL") return <span className="trend-badge neutral">Sem base</span>;
  const labels = { CRESCIMENTO: "Crescimento", REDUCAO: "Redução", ESTAVEL: "Estável" };
  return <span className={`trend-badge ${item.tendencia.toLowerCase()}`}>{labels[item.tendencia] || "Sem comparação"}</span>;
}

function TerritorialInvestigationPanel({ item, onInvestigate }) {
  if (!item) return <section className="territorial-investigation-panel"><h2>Detalhamento</h2><p className="muted-copy">Selecione um território no mapa ou na tabela.</p></section>;
  const comparison = item.comparacao || {};
  return <section className="territorial-investigation-panel">
    <header><div><h2>{item.nome}</h2><p>{item.total} solicitações no período</p></div></header>
    {item.estadoQualidade === "BAIXA_QUALIDADE" && <p className="territorial-quality-state">Baixa qualidade geográfica: interprete o recorte com cautela.</p>}
    {comparison.estado === "DISPONIVEL" ? <div className="territorial-comparison-grid">
      <span><strong>{formatVariation(comparison.variacaoVolumePercentual)}</strong><small>volume</small></span>
      <span><strong>{formatPoints(comparison.variacaoAtrasoPontosPercentuais)}</strong><small>atraso</small></span>
      <span><strong>{formatPoints(comparison.variacaoSolucaoPontosPercentuais)}</strong><small>solução</small></span>
    </div> : <p className="territorial-sample-state">{comparison.estado === "SEM_COMPARACAO" ? "Não há registros na janela anterior equivalente." : `Amostra anterior insuficiente (${comparison.amostraAnterior || 0} registros).`}</p>}
    <Breakdown title="Categorias" items={item.detalhes?.categorias || []} />
    <Breakdown title="Órgãos" items={item.detalhes?.orgaos || []} />
    <Breakdown title="Responsáveis" items={item.detalhes?.responsaveis || []} />
    <section className="territorial-examples"><h3>Exemplos autorizados</h3>{item.detalhes?.amostra?.length ? item.detalhes.amostra.map((request) => <article key={request.id}><strong>{request.protocolo}</strong><span>{request.titulo}</span></article>) : <p className="muted-copy">Sem exemplos disponíveis para seu perfil.</p>}</section>
    <button className="primary-button" onClick={() => onInvestigate(item.filtroSolicitacoes)}>Ver solicitações</button>
  </section>;
}

function TerritorialOperationsPanel({ data, error, query, users, user, selected, metrics, alerts, onCreate, onChanged, onQueryChange }) {
  const [closingId, setClosingId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [edit, setEdit] = useState({ responsavelId: "", prazo: "" });
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState("");
  const [evidenceAction, setEvidenceAction] = useState(null);
  const [evidence, setEvidence] = useState({ tipo: "DOCUMENTO", titulo: "", descricao: "", data: "", url: "", arquivo: null });
  const [resolvingAlert, setResolvingAlert] = useState(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const actions = data.content || [];
  const permissions = data.permissoes || {};

  function changeQuery(key, value) {
    onQueryChange((current) => ({ ...current, [key]: value, page: key === "page" ? value : 1 }));
  }

  async function updateAction(action, payload) {
    setSaving(true);
    setLocalError("");
    try {
      await apiRequest(`/api/v1/painel/territorial/acoes/${action.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setClosingId(null);
      setResult("");
      await onChanged();
    } catch (requestError) {
      setLocalError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  function openEdit(action) {
    setEditingId(action.id);
    setEdit({
      responsavelId: action.responsavelId || "",
      prazo: action.prazo ? localDateTimeValue(new Date(action.prazo)) : "",
    });
  }

  async function saveEdit(action) {
    await updateAction(action, {
      responsavelId: edit.responsavelId || null,
      prazo: edit.prazo ? new Date(edit.prazo).toISOString() : null,
    });
    setEditingId(null);
  }

  async function submitEvidence(event, action) {
    event.preventDefault();
    setSaving(true);
    setLocalError("");
    try {
      let body;
      if (evidence.arquivo) {
        body = new FormData();
        Object.entries(evidence).forEach(([key, value]) => {
          if (value) body.append(key === "arquivo" ? "arquivo" : key, value);
        });
      } else {
        body = JSON.stringify({ ...evidence, arquivo: undefined });
      }
      await apiRequest(`/api/v1/painel/territorial/acoes/${action.id}/evidencias`, { method: "POST", body });
      setEvidenceAction(null);
      setEvidence({ tipo: "DOCUMENTO", titulo: "", descricao: "", data: "", url: "", arquivo: null });
      await onChanged();
    } catch (requestError) {
      setLocalError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function updateAlert(alert, status, justificativa = "") {
    setSaving(true);
    setLocalError("");
    try {
      await apiRequest(`/api/v1/painel/territorial/alertas/${alert.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, justificativa }),
      });
      setResolvingAlert(null);
      setResolutionNote("");
      await onChanged();
    } catch (requestError) {
      setLocalError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="territorial-operations-panel">
    <header>
      <div><h2>Operação territorial</h2><p>{permissions.escopo === "PROPRIAS" ? `Apenas ações atribuídas a ${user?.name || "você"}.` : "Histórico e prazos do território selecionado."}</p></div>
      <button className="primary-button compact" disabled={!selected || !permissions.podeCriar} onClick={onCreate}>Nova ação</button>
    </header>
    <div className="territorial-execution-metrics" aria-label="Métricas de execução territorial">
      <span><strong>{metrics?.abertas || 0}</strong><small>abertas</small></span>
      <span><strong>{formatPercent(metrics?.taxaConclusaoPercentual)}</strong><small>conclusão</small></span>
      <span><strong>{formatPercent(metrics?.coberturaEvidenciasPercentual)}</strong><small>com evidência</small></span>
      <span><strong>{metrics?.cumprimentoPrazoPercentual == null ? "N/A" : formatPercent(metrics.cumprimentoPrazoPercentual)}</strong><small>no prazo</small></span>
      <span><strong>{formatHours(metrics?.tempoMedioConclusaoHoras)}</strong><small>tempo médio</small></span>
    </div>
    {!!alerts?.length && <section className="territorial-alert-center">
      <header><strong>Alertas operacionais</strong><span>{alerts.length} aberto(s)</span></header>
      {alerts.map((alert) => <article key={alert.id} className={alert.status.toLowerCase()}>
        <div><strong>{alert.titulo}</strong><small>{alert.acaoTitulo} · {formatDateTime(alert.disparadoEm)}</small></div>
        {resolvingAlert === alert.id ? <div className="territorial-alert-resolution">
          <input aria-label="Resolução do alerta" value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} placeholder="Como o alerta foi resolvido?" />
          <button className="secondary-button compact" onClick={() => setResolvingAlert(null)}>Voltar</button>
          <button className="primary-button compact" disabled={saving || resolutionNote.trim().length < 3} onClick={() => updateAlert(alert, "RESOLVIDO", resolutionNote)}>Resolver</button>
        </div> : <div className="territorial-alert-actions">
          {alert.status === "ATIVO" && <button className="secondary-button compact" disabled={saving} onClick={() => updateAlert(alert, "RECONHECIDO")}>Reconhecer</button>}
          <button className="secondary-button compact" onClick={() => setResolvingAlert(alert.id)}>Resolver</button>
        </div>}
      </article>)}
    </section>}
    <div className="territorial-action-filters">
      <input aria-label="Buscar ações territoriais" placeholder="Buscar no histórico" value={query.q} onChange={(event) => changeQuery("q", event.target.value)} />
      <select aria-label="Filtrar status das ações" value={query.status} onChange={(event) => changeQuery("status", event.target.value)}>
        <option value="ABERTAS">Abertas</option><option value="TODAS">Todas</option>
        <option value="PENDENTE">Pendentes</option><option value="EM_ANDAMENTO">Em andamento</option>
        <option value="CONCLUIDA">Concluídas</option><option value="CANCELADA">Canceladas</option>
      </select>
      <select aria-label="Filtrar tipo de ação" value={query.tipo} onChange={(event) => changeQuery("tipo", event.target.value)}>
        <option value="">Todos os tipos</option>{["TAREFA", "AGENDA", "VISITA", "ROTEIRO", "ENCAMINHAMENTO"].map((value) => <option key={value} value={value}>{territorialActionTypeLabel(value)}</option>)}
      </select>
      <select aria-label="Filtrar prazo das ações" value={query.prazoEstado} onChange={(event) => changeQuery("prazoEstado", event.target.value)}>
        <option value="">Todos os prazos</option><option value="VENCIDA">Vencidas</option>
        <option value="PROXIMA">Próximas 24h</option><option value="NO_PRAZO">No prazo</option>
        <option value="SEM_PRAZO">Sem prazo</option><option value="ENCERRADA">Encerradas</option>
      </select>
    </div>
    {(error || localError) && <p className="form-error" role="alert">{error || localError}</p>}
    {!actions.length ? <p className="muted-copy">Nenhuma ação encontrada neste recorte.</p> : (
      <div className="territorial-action-list">
        {actions.map((action) => <article key={action.id}>
          <div className="territorial-action-heading">
            <span className={`territorial-action-type ${action.tipo.toLowerCase()}`}>{territorialActionTypeLabel(action.tipo)}</span>
            <span className={`territorial-action-status ${action.status.toLowerCase()}`}>{territorialActionStatusLabel(action.status)}</span>
          </div>
          <strong>{action.titulo}</strong>
          <small>{action.responsavel} · {action.prazo ? formatDateTime(action.prazo) : "Sem prazo"}</small>
          <span className={`territorial-deadline-state ${action.prazoEstado.toLowerCase()}`}>{territorialDeadlineLabel(action.prazoEstado)}</span>
          {action.solicitacaoIds?.length > 0 && <small>{action.solicitacaoIds.length} solicitação(ões) de referência</small>}
          {action.resultado && <p className="territorial-action-result"><strong>Resultado:</strong> {action.resultado}</p>}
          {!!action.evidenciasEstruturadas?.length && <ul className="territorial-evidence-list">{action.evidenciasEstruturadas.map((item) => <li key={item.id}>
            <span><strong>{item.titulo}</strong><small>{territorialEvidenceTypeLabel(item.tipo)} · {item.autor}</small></span>
            {item.downloadUrl ? <a href={item.downloadUrl}>Baixar</a> : <a href={item.url} target="_blank" rel="noreferrer">Abrir</a>}
          </li>)}</ul>}
          {evidenceAction === action.id && <form className="territorial-evidence-form" onSubmit={(event) => submitEvidence(event, action)}>
            <div><label>Tipo<select value={evidence.tipo} onChange={(event) => setEvidence((current) => ({ ...current, tipo: event.target.value }))}>{["DOCUMENTO", "FOTO", "LINK", "ATA", "COMPROVANTE", "OUTRO"].map((value) => <option key={value} value={value}>{territorialEvidenceTypeLabel(value)}</option>)}</select></label>
            <label>Data<input type="datetime-local" value={evidence.data} onChange={(event) => setEvidence((current) => ({ ...current, data: event.target.value }))} /></label></div>
            <label>Título<input required minLength="3" value={evidence.titulo} onChange={(event) => setEvidence((current) => ({ ...current, titulo: event.target.value }))} /></label>
            <label>Descrição<textarea rows="2" value={evidence.descricao} onChange={(event) => setEvidence((current) => ({ ...current, descricao: event.target.value }))} /></label>
            <label>Arquivo<input type="file" accept=".pdf,.jpg,.jpeg,.png,.txt,.mp3,.mp4,.ogg,.wav,.webm" onChange={(event) => setEvidence((current) => ({ ...current, arquivo: event.target.files?.[0] || null }))} /></label>
            <label>ou URL<input type="url" value={evidence.url} onChange={(event) => setEvidence((current) => ({ ...current, url: event.target.value }))} placeholder="https://" /></label>
            <div><button type="button" className="secondary-button compact" onClick={() => setEvidenceAction(null)}>Voltar</button><button className="primary-button compact" disabled={saving || (!evidence.arquivo && !evidence.url)}>Salvar evidência</button></div>
          </form>}
          {editingId === action.id && <div className="territorial-action-edit">
            <label>Responsável<select value={edit.responsavelId} onChange={(event) => setEdit((current) => ({ ...current, responsavelId: event.target.value }))}><option value="">Não atribuído</option>{users.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
            <label>Prazo<input type="datetime-local" value={edit.prazo} onChange={(event) => setEdit((current) => ({ ...current, prazo: event.target.value }))} /></label>
            <div><button className="secondary-button compact" onClick={() => setEditingId(null)}>Voltar</button><button className="primary-button compact" disabled={saving} onClick={() => saveEdit(action)}>Salvar</button></div>
          </div>}
          {closingId === action.id ? <div className="territorial-action-close">
            <label>Resultado ou justificativa<textarea rows="3" value={result} onChange={(event) => setResult(event.target.value)} /></label>
            <div>
              <button className="secondary-button compact" onClick={() => setClosingId(null)}>Voltar</button>
              {action.permissoes.podeCancelar && <button className="secondary-button compact danger" disabled={saving || result.trim().length < 3} onClick={() => updateAction(action, { status: "CANCELADA", resultado: result })}>Cancelar ação</button>}
              <button className="primary-button compact" disabled={saving || result.trim().length < 3} onClick={() => updateAction(action, { status: "CONCLUIDA", resultado: result })}>Concluir</button>
            </div>
          </div> : editingId !== action.id && action.permissoes.podeMovimentar && !["CONCLUIDA", "CANCELADA"].includes(action.status) && <div className="territorial-action-buttons">
            <button className="secondary-button compact" onClick={() => setEvidenceAction(action.id)}>Adicionar evidência</button>
            {action.permissoes.podeReatribuir && <button className="secondary-button compact" onClick={() => openEdit(action)}>Atribuição e prazo</button>}
            {action.status === "PENDENTE" && <button className="secondary-button compact" disabled={saving} onClick={() => updateAction(action, { status: "EM_ANDAMENTO" })}>Iniciar</button>}
            <button className="secondary-button compact" onClick={() => setClosingId(action.id)}>Encerrar</button>
          </div>}
        </article>)}
      </div>
    )}
    <footer className="territorial-action-pagination">
      <span>{data.total || 0} ação(ões) · Página {data.page || 1} de {data.totalPages || 1}</span>
      <select aria-label="Ações por página" value={query.size} onChange={(event) => changeQuery("size", Number(event.target.value))}>{[10, 25, 50, 100].map((value) => <option key={value} value={value}>{value}</option>)}</select>
      <button className="secondary-button compact" disabled={(data.page || 1) <= 1} onClick={() => changeQuery("page", data.page - 1)}>Anterior</button>
      <button className="secondary-button compact" disabled={(data.page || 1) >= (data.totalPages || 1)} onClick={() => changeQuery("page", data.page + 1)}>Próxima</button>
    </footer>
  </section>;
}

function TerritorialActionModal({ item, filters, users, onClose, onCreated }) {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
  tomorrow.setMinutes(0, 0, 0);
  const [form, setForm] = useState({
    tipo: "TAREFA",
    titulo: `Atuação territorial em ${item.nome}`,
    descricao: "",
    responsavelId: "",
    prazo: localDateTimeValue(tomorrow),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const requestIds = (item.detalhes?.amostra || []).map((requestItem) => requestItem.id).filter(Boolean);

  function change(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await apiRequest("/api/v1/painel/territorial/acoes", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          territorioId: item.id,
          prazo: form.prazo ? new Date(form.prazo).toISOString() : null,
          filtros: { ...filters, territorioId: item.id },
          solicitacaoIds: requestIds,
          origem: {
            tipo: "INTELIGENCIA_TERRITORIAL",
            territorioNome: item.nome,
            comparacao: item.comparacao,
          },
        }),
      });
      onCreated();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="modal territorial-action-modal" role="dialog" aria-modal="true" aria-labelledby="territorial-action-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><p className="eyebrow">{item.nome}</p><h2 id="territorial-action-title">Criar ação territorial</h2></div><button className="icon-button" aria-label="Fechar" onClick={onClose}>×</button></header>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>Tipo<select name="tipo" value={form.tipo} onChange={change}>{["TAREFA", "AGENDA", "VISITA", "ROTEIRO", "ENCAMINHAMENTO"].map((value) => <option key={value} value={value}>{territorialActionTypeLabel(value)}</option>)}</select></label>
          <label>Responsável<select name="responsavelId" value={form.responsavelId} onChange={change}><option value="">Não atribuído</option>{users.map((user) => <option key={user.id} value={user.id}>{user.nome}</option>)}</select></label>
        </div>
        <label>Título<input name="titulo" required minLength="3" maxLength="180" value={form.titulo} onChange={change} /></label>
        <label>Prazo ou data da agenda<input name="prazo" type="datetime-local" value={form.prazo} onChange={change} required={["AGENDA", "VISITA", "ROTEIRO"].includes(form.tipo)} /></label>
        <label>Descrição<textarea name="descricao" rows="4" value={form.descricao} onChange={change} placeholder="Objetivo, orientação e resultado esperado" /></label>
        <p className="territorial-action-provenance">A ação preservará os filtros atuais e {requestIds.length} solicitação(ões) de referência autorizada(s).</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact" disabled={saving}>{saving ? "Criando..." : "Criar ação"}</button></footer>
      </form>
    </section>
  </div>;
}

function territorialActionTypeLabel(value) {
  return { TAREFA: "Tarefa", AGENDA: "Agenda", VISITA: "Visita", ROTEIRO: "Roteiro", ENCAMINHAMENTO: "Encaminhamento" }[value] || value;
}

function territorialActionStatusLabel(value) {
  return { PENDENTE: "Pendente", EM_ANDAMENTO: "Em andamento", CONCLUIDA: "Concluída", CANCELADA: "Cancelada" }[value] || value;
}

function territorialDeadlineLabel(value) {
  return {
    VENCIDA: "Prazo vencido", PROXIMA: "Vence em até 24h", NO_PRAZO: "No prazo",
    SEM_PRAZO: "Sem prazo", ENCERRADA: "Encerrada",
  }[value] || value;
}

function territorialEvidenceTypeLabel(value) {
  return { DOCUMENTO: "Documento", FOTO: "Foto", LINK: "Link", ATA: "Ata", COMPROVANTE: "Comprovante", OUTRO: "Outro" }[value] || value;
}

function localDateTimeValue(value) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

function ReportsWorkspace() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  const [filters, setFilters] = useState({
    inicio: dateInputValue(start),
    fim: dateInputValue(end),
    tipo: "operacional",
  });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  async function loadReport() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams(filters).toString();
      setReport(await apiRequest(`/api/v1/painel/relatorios?${query}`));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function downloadPdf() {
    setDownloading(true);
    setError("");
    try {
      const query = new URLSearchParams(filters).toString();
      const blob = await apiDownload(`/api/v1/painel/relatorios/pdf?${query}`, { method: "GET" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `gabflow-relatorio-${filters.tipo}-${filters.inicio}-${filters.fim}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setDownloading(false);
    }
  }

  const update = (key, value) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setReport(null);
  };

  return (
    <section className="mandate-report-workspace">
      <section className="mandate-report-panel">
        <header>
          <div>
            <span className="report-product-badge">GabFlow Executive Intelligence</span>
            <h2>Relatórios do mandato</h2>
            <p>Transforme a operação do gabinete em resultados claros, comparáveis e prontos para apresentação.</p>
          </div>
          <div className="report-header-mark"><TrendingUp size={22} /></div>
        </header>
        <div className="mandate-report-controls">
          <label>Tipo de relatório<select aria-label="Tipo de relatório" value={filters.tipo} onChange={(event) => update("tipo", event.target.value)}>
            <option value="operacional">Operacional</option>
            <option value="insights_mandato">Insights do Mandato</option>
          </select></label>
          <label>Data início<input aria-label="Data início do relatório" type="date" value={filters.inicio} max={filters.fim} onChange={(event) => update("inicio", event.target.value)} /></label>
          <label>Data fim<input aria-label="Data fim do relatório" type="date" value={filters.fim} min={filters.inicio} onChange={(event) => update("fim", event.target.value)} /></label>
          <button className="primary-button" disabled={loading} onClick={loadReport}>
            <FileText size={16} /> {loading ? "Gerando..." : "Gerar relatório"}
          </button>
          <button className="secondary-button report-download-button" disabled={!report || downloading} onClick={downloadPdf}>
            <Download size={16} /> {downloading ? "Preparando PDF..." : "Baixar PDF executivo"}
          </button>
        </div>
        {error && <p className="form-error">{error}</p>}
        {!report ? (
          <ReportEmptyState type={filters.tipo} />
        ) : (
          <ExecutiveReportContent report={report} onDownload={downloadPdf} downloading={downloading} />
        )}
      </section>
    </section>
  );
}

function ReportEmptyState({ type }) {
  return <section className="report-empty-state">
    <div className="report-empty-visual">
      <span className="report-signal positive" /><span className="report-signal warning" /><span className="report-signal danger" />
      <TrendingUp size={34} />
    </div>
    <div>
      <h3>{type === "operacional" ? "Visão completa da operação" : "Inteligência para posicionar o mandato"}</h3>
      <p>{type === "operacional" ? "Gere rankings, horários de pico, territórios, recorrências, produção legislativa e ações derivadas." : "Conecte demandas, participação cidadã, territórios e entregas em uma narrativa executiva do período."}</p>
    </div>
  </section>;
}

function ExecutiveReportContent({ report, onDownload, downloading }) {
  const summary = report.resumo || {};
  const summaryItems = [
    ["Recebidas", summary.solicitacoesRecebidas, "neutral"],
    ["Movimentadas", summary.solicitacoesMovimentadas, "neutral"],
    ["Resolvidas", summary.resolvidasOuEncerradas, "success"],
    ["Taxa de resolução", formatPercent(summary.taxaResolucaoPercentual), "success"],
    ["No prazo", formatPercent(summary.cumprimentoPrazoPercentual), "success"],
    ["Atrasadas", summary.atrasadas, summary.atrasadas ? "danger" : "success"],
    ["Docs. legislativos", summary.documentosLegislativos, "accent"],
    ["Ações geradas", summary.acoesGeradas, "accent"],
  ];
  return (
    <div className="mandate-report-content">
      <section className="report-executive-hero">
        <div><span>{report.tipo === "OPERACIONAL" ? "Relatório Operacional" : "Insights do Mandato"}</span><h2>{report.titulo}</h2><p>{report.gabinete?.nome} · {report.periodo?.rotulo}</p></div>
        <div className="report-comparison"><small>Volume vs. período anterior</small><strong className={(report.comparacao?.variacaoVolumePercentual || 0) > 0 ? "up" : "down"}>{formatVariation(report.comparacao?.variacaoVolumePercentual)}</strong><button className="secondary-button compact" onClick={onDownload} disabled={downloading}><Download size={15} /> PDF executivo</button></div>
      </section>
      <div className="mandate-report-summary">
        {summaryItems.map(([label, value, tone]) => (
          <article key={label} className={`report-summary-${tone}`}><strong>{value ?? 0}</strong><span>{label}</span></article>
        ))}
      </div>
      <ExecutiveTrafficLights items={report.semaforo || []} />
      <ExecutiveInsights items={report.destaques || []} />
      <PrivacyAggregationNotice summary={report.privacidadeAgregacao} />
      <section className="report-chart-grid report-chart-grid-wide">
        <ReportChartCard title="Volume no período" subtitle="Demandas recebidas ao longo do recorte">
          <ReportLineChart items={report.graficos?.volumePeriodo || []} />
        </ReportChartCard>
        <ReportChartCard title="Horários com mais atendimentos" subtitle={report.picoAtendimento?.total ? `Pico às ${report.picoAtendimento.rotulo}` : "Sem pico identificado"}>
          <ReportHourChart items={report.graficos?.horariosAtendimento || []} />
        </ReportChartCard>
      </section>
      <section className="report-chart-grid">
        <ReportChartCard title="Regiões com maiores demandas" subtitle="Concentração territorial"><ReportBarChart items={report.graficos?.territorios || []} /></ReportChartCard>
        <ReportChartCard title="Demandas mais recorrentes" subtitle="Temas que mais mobilizaram o gabinete"><ReportBarChart items={report.graficos?.demandasRecorrentes || []} /></ReportChartCard>
        <ReportChartCard title="Documentos por demandas" subtitle={`${report.producaoLegislativa?.demandasComDocumento || 0} demandas geraram documentos`}><ReportBarChart items={report.graficos?.producaoLegislativa || []} labelFormatter={reportDocumentTypeLabel} /></ReportChartCard>
        <ReportChartCard title="Ações geradas das demandas" subtitle="Desdobramentos concretos no período"><ReportBarChart items={report.graficos?.acoesGeradas || []} /></ReportChartCard>
      </section>
      <EfficiencyRanking items={report.rankings?.eficienciaEquipe || []} />
      <section className="report-spotlight-grid">
        <ReportSpotlight title="Cidadão mais atuante" value={report.rankings?.cidadaosAtuantes?.[0]?.nome || "Sem recorrência"} helper={report.rankings?.cidadaosAtuantes?.[0] ? `${report.rankings.cidadaosAtuantes[0].total} demandas no período` : "Nenhum destaque no recorte"} />
        <ReportSpotlight title="Horário de pico" value={report.picoAtendimento?.total ? report.picoAtendimento.rotulo : "Sem pico"} helper={report.picoAtendimento?.total ? `${report.picoAtendimento.total} atendimentos registrados` : "Sem dados no período"} />
        <ReportSpotlight title="Território prioritário" value={report.graficos?.territorios?.[0]?.nome || "Sem território"} helper={report.graficos?.territorios?.[0] ? `${report.graficos.territorios[0].total} demandas movimentadas` : "Sem concentração identificada"} />
      </section>
      <details className="report-evidence-disclosure">
        <summary>Evidências rastreáveis <span>{(report.evidencias || []).length} protocolos</span></summary>
        <section className="mandate-report-section">
        {(report.evidencias || []).length ? report.evidencias.map((item) => (
          <article key={item.protocolo}>
            <strong>{item.protocolo} · {item.titulo}</strong>
            <span>{statusLabel(item.status)} · {item.categoria} · {item.territorio}</span>
            <ul>
              {item.eventos.map((event) => (
                <li key={`${item.protocolo}-${event.tipo}-${event.data}`}>
                  <b>{formatDate(event.data)}</b> {evidenceTypeLabel(event.tipo)}: {event.descricao}
                </li>
              ))}
            </ul>
          </article>
        )) : <p className="muted-copy">Sem evidências registradas para o período.</p>}
        </section>
      </details>
    </div>
  );
}

function ExecutiveTrafficLights({ items }) {
  return <section className="report-traffic-section"><header><div><h3>Semáforo executivo</h3><p>Problemas, avisos e resultados positivos do período.</p></div></header><div className="report-traffic-grid">{items.map((item) => <article key={item.titulo} className={`report-traffic-${item.nivel}`}><span className="report-traffic-light" /><div><small>{item.nivel === "problema" ? "Problema" : item.nivel === "aviso" ? "Aviso" : "Positivo"}</small><strong>{item.titulo}</strong><p>{item.descricao}</p></div><b>{item.valor}</b></article>)}</div></section>;
}

function ExecutiveInsights({ items }) {
  if (!items.length) return null;
  return <section className="report-insights"><header><h3>Insights do período</h3><p>Sinais para orientar prioridades e comunicação do mandato.</p></header><div>{items.map((item) => <article key={item.titulo}><span><TrendingUp size={16} /></span><div><strong>{item.titulo}</strong><p>{item.descricao}</p></div></article>)}</div></section>;
}

function ReportChartCard({ title, subtitle, children }) {
  return <article className="report-chart-card"><header><div><h3>{title}</h3><p>{subtitle}</p></div></header>{children}</article>;
}

function ReportLineChart({ items }) {
  if (!items.length) return <p className="report-chart-empty">Sem dados suficientes.</p>;
  const maximum = Math.max(...items.map((item) => item.total || 0), 1);
  const points = items.map((item, index) => {
    const x = items.length === 1 ? 50 : (index / (items.length - 1)) * 100;
    const y = 92 - ((item.total || 0) / maximum) * 72;
    return `${x},${y}`;
  }).join(" ");
  return <div className="report-line-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Evolução do volume no período"><defs><linearGradient id="reportLineFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#168e9b" stopOpacity=".28" /><stop offset="100%" stopColor="#168e9b" stopOpacity="0" /></linearGradient></defs><polygon points={`0,100 ${points} 100,100`} fill="url(#reportLineFill)" /><polyline points={points} fill="none" stroke="#0f7582" strokeWidth="2.2" vectorEffect="non-scaling-stroke" /></svg><div><span>{reportPeriodLabel(items[0].nome)}</span><strong>Pico {maximum}</strong><span>{reportPeriodLabel(items.at(-1).nome)}</span></div></div>;
}

function ReportHourChart({ items }) {
  const maximum = Math.max(...items.map((item) => item.total || 0), 1);
  return <div className="report-hour-chart" role="img" aria-label="Distribuição dos atendimentos por hora">{items.map((item) => <span key={item.hora} title={`${item.rotulo}: ${item.total}`}><i style={{ height: `${Math.max(((item.total || 0) / maximum) * 100, item.total ? 5 : 1)}%` }} className={item.total === maximum && item.total ? "peak" : ""} /><small>{item.hora % 3 === 0 ? item.rotulo : ""}</small></span>)}</div>;
}

function ReportBarChart({ items, labelFormatter = (value) => value }) {
  if (!items.length) return <p className="report-chart-empty">Sem dados suficientes.</p>;
  const maximum = Math.max(...items.map((item) => item.total || 0), 1);
  return <div className="report-bar-chart">{items.slice(0, 7).map((item) => <div key={item.nome}><span title={labelFormatter(item.nome)}>{labelFormatter(item.nome)}</span><i><b style={{ width: `${((item.total || 0) / maximum) * 100}%` }} /></i><strong>{item.total}</strong></div>)}</div>;
}

function EfficiencyRanking({ items }) {
  return <section className="report-ranking"><header><div><h3>Ranking de eficiência da equipe</h3><p>Índice combina resolução, cumprimento de prazo e atividade registrada.</p></div></header>{items.length ? <div className="report-ranking-table-wrap"><table className="report-efficiency-table"><colgroup><col className="report-rank-col" /><col className="report-collaborator-col" /><col className="report-score-col" /><col className="report-demands-col" /><col className="report-resolved-col" /><col className="report-deadline-col" /><col className="report-interactions-col" /><col className="report-tasks-col" /></colgroup><thead><tr><th>#</th><th>Colaborador</th><th>Score</th><th>Demandas</th><th>Resolvidas</th><th>No prazo</th><th>Interações</th><th>Tarefas</th></tr></thead><tbody>{items.map((item, index) => <tr key={item.id}><td><span className={`report-rank-position rank-${index + 1}`}>{index + 1}</span></td><td><strong>{item.nome}</strong></td><td><b>{formatNumber(item.score)}</b></td><td>{item.demandas}</td><td>{item.resolvidas}</td><td>{formatPercent(item.cumprimentoPrazoPercentual)}</td><td>{item.interacoes}</td><td>{item.tarefasConcluidas}</td></tr>)}</tbody></table></div> : <p className="muted-copy">Sem atividade suficiente para compor o ranking.</p>}</section>;
}

function ReportSpotlight({ title, value, helper }) {
  return <article><span>{title}</span><strong>{value}</strong><small>{helper}</small></article>;
}

function reportDocumentTypeLabel(value) {
  return String(value || "").replaceAll("_", " ").toLocaleLowerCase("pt-BR").replace(/^./, (letter) => letter.toUpperCase());
}

function reportPeriodLabel(value) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return formatDate(`${value}T12:00:00`);
  return periodLabel(value);
}

function OperationalMetricsPanel({ metrics = {} }) {
  const items = [
    {
      label: "Primeira resposta",
      value: formatHours(metrics.tempoMedioPrimeiraRespostaHoras),
      helper: `${metrics.primeirasRespostasRegistradas || 0} com resposta`,
      Icon: MessageSquareReply,
    },
    {
      label: "Primeiro encaminhamento",
      value: formatHours(metrics.tempoMedioPrimeiroEncaminhamentoHoras),
      helper: `${metrics.encaminhamentosRegistrados || 0} encaminhadas`,
      Icon: Forward,
    },
    {
      label: "Encerramento",
      value: formatHours(metrics.tempoMedioEncerramentoHoras),
      helper: `${metrics.encerramentosRegistrados || 0} encerradas`,
      Icon: FileCheck2,
    },
    {
      label: "Resolução",
      value: formatHours(metrics.tempoMedioResolucaoHoras),
      helper: `${metrics.resolucoesRegistradas || 0} resolvidas`,
      Icon: CheckCircle2,
    },
    {
      label: "Reaberturas",
      value: metrics.reaberturas || 0,
      helper: "casos reabertos",
      Icon: RotateCcw,
    },
  ];

  return (
    <section className="operational-metrics">
      <header>
        <div>
          <h2>Métricas operacionais</h2>
          <p>Tempos médios e reaberturas para acompanhar a eficiência do atendimento.</p>
        </div>
      </header>
      <div>
        {items.map(({ label, value, helper, Icon }) => (
          <article key={label}>
            <Icon size={17} />
            <span>
              <strong>{value}</strong>
              <small>{label}</small>
              <em>{helper}</em>
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

function DemandAlertsPanel({ alerts = {} }) {
  const recurrences = alerts.reincidencias || [];
  const anomalies = alerts.crescimentosAnormais || [];
  const hasAlerts = recurrences.length > 0 || anomalies.length > 0;

  return (
    <section className="demand-alerts-panel">
      <header>
        <div>
          <h2>Alertas de demanda</h2>
          <p>Reincidência e crescimento anormal detectados por regras auditáveis.</p>
        </div>
      </header>
      {!hasAlerts ? (
        <p className="muted-copy">Nenhum padrão relevante detectado nas janelas atuais.</p>
      ) : (
        <div className="demand-alert-columns">
          <DemandAlertList
            title="Demandas reincidentes"
            icon={Repeat2}
            empty="Sem reincidências no período."
            items={recurrences}
            renderItem={(item) => (
              <>
                <strong>{item.categoria} · {item.territorio}</strong>
                <span>{item.total} demandas · {item.abertas} abertas · {item.atrasadas} atrasadas</span>
                <small>{item.regra}</small>
              </>
            )}
          />
          <DemandAlertList
            title="Crescimento anormal"
            icon={TrendingUp}
            empty="Sem crescimento anormal."
            items={anomalies}
            renderItem={(item) => (
              <>
                <strong>{item.categoria} · {item.territorio}</strong>
                <span>{item.atual} recentes · base semanal {formatNumber(item.baseSemanal)}</span>
                <small>{item.fatorCrescimento ? `${item.fatorCrescimento}x acima da base` : "Sem histórico na base"}</small>
              </>
            )}
          />
        </div>
      )}
    </section>
  );
}

function DemandAlertList({ title, icon: Icon, empty, items, renderItem }) {
  return (
    <section>
      <h3><Icon size={15} /> {title}</h3>
      {items.length ? items.slice(0, 4).map((item) => (
        <article key={`${title}-${item.categoria}-${item.territorio}-${item.celula || item.atual}`}>
          {renderItem(item)}
        </article>
      )) : <p className="muted-copy">{empty}</p>}
    </section>
  );
}

function TerritorialPanel({ data, busy, onGeocode, selectedTerritoryId, onSelectTerritory, onOpenRequest, onCreateTerritorialAction, expanded = false }) {
  const points = data?.pontos || [];
  const heatmap = data?.heatmap || [];
  const jurisdiction = data?.jurisdicao;
  const privacy = data?.privacidade;
  const quality = data?.qualidadeDados || {};
  const locationReviews = data?.revisoesLocalizacao || { total: 0, content: [], detalhesTecnicosPermitidos: false };
  const [mapSelection, setMapSelection] = useState(null);
  const selectedRequests = mapSelection?.type === "request"
    ? points.filter((item) => item.id === mapSelection.id)
    : points.filter((item) => (
      mapSelection?.territorioId
        ? item.territorioId === mapSelection.territorioId
        : item.territorio === mapSelection?.territorio
    )).slice(0, 8);
  const hasSuppressedTerritorialData = Boolean(
    privacy?.pontosSuprimidos || privacy?.hotspotsSuprimidos,
  );
  return (
    <section className={`breakdown territorial-panel${expanded ? " territorial-panel-expanded" : ""}`}>
      <header>
        <div>
          <h2>Inteligência territorial</h2>
          <p>Geocodificação local e concentração por território.</p>
          <small>{data?.metodo === "POSTGIS" ? "PostGIS ativo" : "Geografia aproximada"}</small>
        </div>
        <button className="secondary-button compact" disabled={busy || !data?.semCoordenadas} onClick={onGeocode}>
          <MapPinned size={15} /> {busy ? "Geocodificando..." : "Geocodificar"}
        </button>
      </header>
      <div className="territorial-coverage">
        <MapPin size={18} />
        <span><strong>{formatPercent(quality.territorioIdentificadoPercentual)}</strong><small>território identificado</small></span>
        <span><strong>{quality.coordenadasAproximadas || 0}</strong><small>coordenadas aproximadas</small></span>
        <span><strong>{quality.coordenadasVerificadas || 0}</strong><small>coordenadas verificadas</small></span>
        <span><strong>{quality.semCoordenadas || 0}</strong><small>sem coordenadas</small></span>
        <span><strong>{(quality.coordenadasAmbiguas || 0) + (quality.foraDaJurisdicao || 0)}</strong><small>exigem revisão</small></span>
      </div>
      {jurisdiction && <div className="territorial-jurisdiction">
        <strong>{jurisdiction.nome}</strong>
        <span>{jurisdiction.tipoCasa === "ASSEMBLEIA_LEGISLATIVA" ? "Assembleia Legislativa" : "Câmara Municipal"} · {jurisdiction.uf}</span>
      </div>}
      {hasSuppressedTerritorialData && (
        <div className="territorial-privacy-note">
          <ShieldCheck size={15} />
          <span>Dados territoriais com menos de {privacy.minimoPorGrupo} solicitações foram ocultados para evitar reidentificação.</span>
        </div>
      )}
      <div className="territorial-heatmap">
        <h3>Mapa de calor</h3>
        <TerritorialHeatmapMap
          cells={heatmap}
          points={points}
          jurisdiction={jurisdiction}
          selectedTerritoryId={selectedTerritoryId}
          onSelectTerritory={onSelectTerritory}
          onSelectFeature={(feature) => {
            setMapSelection(feature);
            if (feature.territorioId) onSelectTerritory?.(feature.territorioId);
          }}
          expanded={expanded}
        />
        {mapSelection && <section className="territorial-map-selection" aria-label="Demandas selecionadas no mapa">
          <header>
            <div><h4>{mapSelection.type === "request" ? "Solicitação selecionada" : mapSelection.territorio || "Concentração selecionada"}</h4><p>{selectedRequests.length ? `${selectedRequests.length} demanda(s) autorizada(s) neste recorte` : "Dados individuais indisponíveis para este perfil"}</p></div>
            <button className="icon-button" aria-label="Fechar seleção do mapa" onClick={() => setMapSelection(null)}>×</button>
          </header>
          {!!selectedRequests.length && <div className="territorial-map-request-list">{selectedRequests.map((request) => <article key={request.id}>
            <span><strong>{request.protocolo}</strong><small>{request.categoria} · {statusLabels[request.status] || request.status}{request.atrasada ? " · Atrasada" : ""}</small></span>
            <button className="secondary-button compact" onClick={() => onOpenRequest?.(request)}>Abrir solicitação</button>
          </article>)}</div>}
          <footer><button className="primary-button compact" disabled={!mapSelection.territorioId} onClick={() => onCreateTerritorialAction?.(mapSelection)}>Criar ação territorial</button></footer>
        </section>}
        {!heatmap.length && <p className="muted-copy">Sem células de calor calculadas.</p>}
      </div>
      <section className="territorial-location-review">
        <header><div><h3>Localizações que exigem revisão</h3><p>Registros ambíguos, fora da jurisdição ou com baixa precisão.</p></div><strong>{locationReviews.total || 0}</strong></header>
        {locationReviews.detalhesTecnicosPermitidos ? (
          locationReviews.content?.length ? <div className="territorial-location-review-list">
            {locationReviews.content.slice(0, expanded ? 8 : 4).map((item) => <article key={item.id}>
              <span><strong>{item.protocolo}</strong><small>{locationReviewLabel(item.status)} · {item.territorio}</small></span>
              <button className="secondary-button compact" onClick={() => onOpenRequest?.(item)}>Revisar</button>
              <details><summary>Detalhes técnicos</summary><p>{coordinateLabel(item)} · confiança {formatConfidence(item.confianca)} · {item.metodo || "método não informado"}</p></details>
            </article>)}
          </div> : <p className="muted-copy">Nenhuma localização pendente de revisão.</p>
        ) : <p className="muted-copy">Detalhes individuais disponíveis somente para administradores e gestores responsáveis pela qualidade dos dados.</p>}
      </section>
    </section>
  );
}

function TerritorialHeatmapMap({ cells = [], points = [], jurisdiction = null, selectedTerritoryId = null, onSelectTerritory, onSelectFeature, expanded = false }) {
  const mapProps = { cells, points, jurisdiction, selectedTerritoryId, onSelectTerritory, onSelectFeature, expanded };
  return <TerritorialMap {...mapProps} fallback={<TerritorialFallbackMap {...mapProps} />} />;
}

function TerritorialFallbackMap({ cells = [], points = [], jurisdiction = null, selectedTerritoryId = null, onSelectTerritory, onSelectFeature, expanded = false }) {
  const geojsonCoordinates = extractGeojsonCoordinates(jurisdiction?.geojson);
  const coordinates = [...cells, ...points].filter(hasCoordinates);
  const mapCoordinates = coordinates.length ? coordinates : geojsonCoordinates;
  if (!mapCoordinates.length) {
    return (
      <div className="territorial-map empty">
        <MapPin size={20} />
        <span>Sem coordenadas para desenhar o mapa.</span>
      </div>
    );
  }

  const bounds = coordinateBounds(mapCoordinates, jurisdiction?.limites);
  const jurisdictionName = jurisdiction?.nome || "Território atendido";
  const jurisdictionType = jurisdiction?.tipoCasa === "ASSEMBLEIA_LEGISLATIVA" ? "Estado" : "Município";
  const jurisdictionCenter = jurisdiction?.centro && hasCoordinates(jurisdiction.centro)
    ? projectCoordinate(jurisdiction.centro, bounds)
    : { x: 160, y: 105 };
  const maxTotal = Math.max(...cells.map((item) => item.total || 0), 1);
  const projectedCells = cells.filter(hasCoordinates).map((item) => ({
    ...item,
    ...projectCoordinate(item, bounds),
    radius: 16 + Math.sqrt((item.total || 1) / maxTotal) * 32,
    opacity: 0.22 + ((item.total || 1) / maxTotal) * 0.46,
  }));
  const projectedPoints = points.filter(hasCoordinates).slice(0, 40).map((item) => ({
    ...item,
    ...projectCoordinate(item, bounds),
  }));
  const fallbackBoundary = "M66 28 C101 14 151 20 191 35 C238 53 281 76 286 113 C291 149 257 181 212 190 C169 199 121 191 85 168 C49 144 36 111 44 77 C49 54 50 38 66 28 Z";
  const boundaryPaths = geojsonPaths(jurisdiction?.geojson, bounds);
  const clipPaths = boundaryPaths.length ? boundaryPaths : [fallbackBoundary];

  return (
    <div className={`territorial-map${expanded ? " expanded" : ""}`} aria-label="Mapa visual de calor territorial" role="img">
      <svg viewBox="0 0 320 210" preserveAspectRatio="none">
        <defs>
          <linearGradient id="territorialMapBase" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#eefbfc" />
            <stop offset="100%" stopColor="#f8fbff" />
          </linearGradient>
          <clipPath id="territorialJurisdictionClip">
            {clipPaths.map((path, index) => <path key={`clip-${index}`} d={path} />)}
          </clipPath>
        </defs>
        <rect className="territorial-map-base" x="0" y="0" width="320" height="210" rx="8" />
        {clipPaths.map((path, index) => <path key={`boundary-${index}`} className="territorial-map-boundary" d={path} />)}
        <g clipPath="url(#territorialJurisdictionClip)">
          <path className="territorial-map-water" d="M0 164 C52 144 92 188 143 166 S248 134 320 158 L320 210 L0 210 Z" />
          <path className="territorial-map-road primary" d="M22 42 C74 76 108 68 146 105 S242 146 300 116" />
          <path className="territorial-map-road" d="M46 178 C76 126 121 123 162 83 S232 45 294 38" />
          <path className="territorial-map-road" d="M18 108 C72 102 113 139 158 132 S242 85 304 94" />
        {projectedCells.map((item) => (
          <g
            key={`${item.territorio}-${item.latitude}-${item.longitude}`}
            className={item.territorioId === selectedTerritoryId ? "selected" : ""}
            role="button"
            tabIndex="0"
            onClick={() => {
              onSelectTerritory?.(item.territorioId || "sem-territorio");
              onSelectFeature?.({ type: "concentration", ...item });
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                onSelectTerritory?.(item.territorioId || "sem-territorio");
                onSelectFeature?.({ type: "concentration", ...item });
              }
            }}
          >
            <circle
              className="territorial-map-heat"
              cx={item.x}
              cy={item.y}
              r={item.radius}
              style={{ opacity: item.opacity }}
            />
            <circle className="territorial-map-core" cx={item.x} cy={item.y} r={Math.max(item.radius * 0.22, 5)} />
            <title>{`${item.territorio}: ${item.total} demanda(s), ${item.abertas} aberta(s)`}</title>
          </g>
        ))}
        {projectedPoints.map((item) => (
          <circle
            key={item.id || `${item.latitude}-${item.longitude}`}
            className="territorial-map-point"
            role="button"
            tabIndex="0"
            aria-label={`Abrir solicitação ${item.protocolo}`}
            cx={item.x}
            cy={item.y}
            r="3.8"
            onClick={() => onSelectFeature?.({ type: "request", ...item })}
            onKeyDown={(event) => {
              if (["Enter", " "].includes(event.key)) onSelectFeature?.({ type: "request", ...item });
            }}
          >
            <title>{`${item.protocolo || item.territorio}: ${item.titulo || "Solicitação"}`}</title>
          </circle>
        ))}
        </g>
        <circle className="territorial-map-center" cx={jurisdictionCenter.x} cy={jurisdictionCenter.y} r="4.8">
          <title>Centro configurado da jurisdição</title>
        </circle>
        <text className="territorial-map-title" x="18" y="25">{jurisdictionName}</text>
        <text className="territorial-map-subtitle" x="18" y="42">{jurisdictionType} atendido pelo gabinete</text>
        <text className="territorial-map-bounds" x="302" y="194" textAnchor="end">Limites da jurisdição</text>
      </svg>
      <div className="territorial-map-legend">
        <span><i className="low" /> Menor concentração</span>
        <span><i className="high" /> Maior concentração</span>
      </div>
    </div>
  );
}

function Breakdown({ title, items, labelFormatter = (value) => value }) {
  const maximum = Math.max(...items.map((item) => item.total), 1);
  return <section className="breakdown"><h2>{title}</h2>{items.length === 0 ? <p className="muted-copy">Sem dados.</p> : items.slice(0, 6).map((item) => <div key={item.nome}><span>{labelFormatter(item.nome)}</span><strong>{item.total}</strong><i style={{ width: `${(item.total / maximum) * 100}%` }} /></div>)}</section>;
}

function dashboardDefaultPeriod() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return { inicio: dateInputValue(start), fim: dateInputValue(end) };
}

function dateInputValue(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatPeriodRange(period) {
  if (!period?.inicio || !period?.fim) return "Período indisponível";
  return `${formatDate(`${period.inicio}T12:00:00`)} – ${formatDate(`${period.fim}T12:00:00`)}`;
}

function formatVariation(value) {
  if (value === null || value === undefined) return "Sem base";
  return `${value > 0 ? "+" : ""}${formatNumber(value)}%`;
}

function formatPoints(value) {
  if (value === null || value === undefined) return "Sem base";
  return `${value > 0 ? "+" : ""}${formatNumber(value)} p.p.`;
}

function recordTerritorialMetric(event, filters = {}) {
  const quantidadeFiltros = Object.entries(filters).filter(
    ([key, value]) => value && !(key === "granularidade" && value === "dia"),
  ).length;
  apiRequest("/api/v1/painel/territorial/metricas-fluxo", {
    method: "POST",
    body: JSON.stringify({ evento: event, quantidadeFiltros }),
  }).catch(() => {});
}

function statusLabel(value) {
  return statusLabels[value] || value;
}

function sourceLabel(value) {
  const labels = {
    PRESENCIAL: "Presencial",
    TELEFONE: "Telefone",
    WHATSAPP: "WhatsApp",
    EMAIL: "E-mail",
    FORMULARIO: "Formulário",
    REDE_SOCIAL: "Rede social",
    VISITA: "Visita",
  };
  return labels[value] || value;
}

function evidenceTypeLabel(value) {
  const labels = {
    encerramento: "Encerramento",
    encaminhamento: "Encaminhamento",
    resposta_orgao: "Resposta do órgão",
    comunicacao_cidadao: "Comunicação ao cidadão",
  };
  return labels[value] || value;
}

function periodLabel(value) {
  if (/^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split("-");
    return `${month}/${year}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatDate(`${value}T00:00:00`);
  }
  return value;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(value));
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function formatHours(value) {
  if (value === null || value === undefined) return "Sem dados";
  if (value >= 24) {
    return `${(value / 24).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dias`;
  }
  return `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
}

function coordinateLabel(item) {
  if (!hasCoordinates(item)) return "Sem coordenadas";
  return `${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}`;
}

function locationReviewLabel(value) {
  return {
    APPROXIMATE: "Baixa precisão",
    AMBIGUOUS: "Localização ambígua",
    OUTSIDE_JURISDICTION: "Fora da jurisdição",
  }[value] || value;
}

function formatConfidence(value) {
  if (value === null || value === undefined) return "não informada";
  return formatPercent(Number(value) * 100);
}

function hasCoordinates(item) {
  return Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude));
}

function coordinateBounds(items, jurisdictionBounds = null) {
  if (validBounds(jurisdictionBounds)) {
    return jurisdictionBounds;
  }
  const latitudes = items.map((item) => Number(item.latitude));
  const longitudes = items.map((item) => Number(item.longitude));
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  return {
    minLatitude,
    maxLatitude: maxLatitude === minLatitude ? maxLatitude + 0.01 : maxLatitude,
    minLongitude,
    maxLongitude: maxLongitude === minLongitude ? maxLongitude + 0.01 : maxLongitude,
  };
}

function validBounds(bounds) {
  return bounds
    && Number.isFinite(Number(bounds.minLatitude))
    && Number.isFinite(Number(bounds.maxLatitude))
    && Number.isFinite(Number(bounds.minLongitude))
    && Number.isFinite(Number(bounds.maxLongitude))
    && Number(bounds.minLatitude) < Number(bounds.maxLatitude)
    && Number(bounds.minLongitude) < Number(bounds.maxLongitude);
}

function extractGeojsonCoordinates(geojson) {
  return geojsonRings(geojson)
    .flat()
    .map(([longitude, latitude]) => ({ latitude, longitude }))
    .filter(hasCoordinates);
}

function geojsonPaths(geojson, bounds) {
  return geojsonRings(geojson)
    .map((ring) => ring
      .map(([longitude, latitude], index) => {
        const point = projectCoordinate({ latitude, longitude }, bounds);
        return `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
      })
      .join(" "))
    .filter(Boolean)
    .map((path) => `${path} Z`);
}

function geojsonRings(geojson) {
  if (!geojson || geojson.type !== "FeatureCollection" || !Array.isArray(geojson.features)) {
    return [];
  }
  return geojson.features.flatMap((feature) => {
    const geometry = feature?.geometry;
    if (geometry?.type === "Polygon") return outerRings([geometry.coordinates]);
    if (geometry?.type === "MultiPolygon") return outerRings(geometry.coordinates);
    return [];
  });
}

function outerRings(polygons) {
  if (!Array.isArray(polygons)) return [];
  return polygons
    .map((polygon) => Array.isArray(polygon) ? polygon[0] : null)
    .filter((ring) => Array.isArray(ring) && ring.length >= 3)
    .map((ring) => ring.filter((coordinate) => (
      Array.isArray(coordinate)
      && coordinate.length >= 2
      && Number.isFinite(Number(coordinate[0]))
      && Number.isFinite(Number(coordinate[1]))
    )).map((coordinate) => [Number(coordinate[0]), Number(coordinate[1])]));
}

function projectCoordinate(item, bounds) {
  const width = 320;
  const height = 210;
  const margin = 24;
  const latitudeRange = bounds.maxLatitude - bounds.minLatitude;
  const longitudeRange = bounds.maxLongitude - bounds.minLongitude;
  return {
    x: margin + ((Number(item.longitude) - bounds.minLongitude) / longitudeRange) * (width - margin * 2),
    y: height - margin - ((Number(item.latitude) - bounds.minLatitude) / latitudeRange) * (height - margin * 2),
  };
}
