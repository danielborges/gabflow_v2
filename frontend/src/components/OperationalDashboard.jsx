import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FileText,
  Forward,
  ListTodo,
  MapPin,
  MapPinned,
  MessageSquareReply,
  Navigation,
  Repeat2,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
  UserMinus,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

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

const defaultDashboardFilters = {
  inicio: "",
  fim: "",
  categoria: "",
  canal: "",
  territorioId: "",
  orgaoId: "",
  granularidade: "dia",
};

export function OperationalDashboard({ onOpenRequests }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [activePanel, setActivePanel] = useState("operation");
  const [filters, setFilters] = useState(defaultDashboardFilters);

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

  async function geocodePending() {
    setGeocoding(true);
    setError("");
    try {
      await apiRequest("/api/v1/painel/territorial/geocodificar", { method: "POST" });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setGeocoding(false);
    }
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
        <button className="secondary-button" onClick={load}>Atualizar</button>
      </section>
      <DashboardFilters
        filters={filters}
        options={data.filtros?.opcoes}
        onChange={setFilters}
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
      <div className="dashboard-tabs segmented-control" aria-label="Seções do painel operacional">
        <button className={activePanel === "operation" ? "active" : ""} onClick={() => setActivePanel("operation")}>
          Operação
        </button>
        <button className={activePanel === "territorial" ? "active" : ""} onClick={() => setActivePanel("territorial")}>
          Inteligência territorial
        </button>
        <button className={activePanel === "report" ? "active" : ""} onClick={() => setActivePanel("report")}>
          Relatório mensal
        </button>
      </div>
      {activePanel === "operation" && <section className="dashboard-layout">
        <div className="dashboard-main">
          <OperationalMetricsPanel metrics={data.metricasOperacionais} />
          <PrivacyAggregationNotice summary={data.privacidadeAgregacao} />
          <DemandAlertsPanel alerts={data.alertasDemanda} />
          <header><div><h2>Fila prioritária</h2><p>Demandas abertas ordenadas por atraso e prazo.</p></div><button className="secondary-button" onClick={onOpenRequests}>Ver solicitações</button></header>
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
      </section>}
      {activePanel === "territorial" && (
        <TerritorialWorkspace data={data} busy={geocoding} onGeocode={geocodePending} />
      )}
      {activePanel === "report" && <MonthlyMandateReport />}
    </>
  );
}

function DashboardFilters({ filters, options = {}, onChange, onClear }) {
  const update = (key, value) => onChange((current) => ({ ...current, [key]: value }));
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

function TerritorialWorkspace({ data, busy, onGeocode }) {
  return (
    <section className="territorial-workspace">
      <TerritorialPanel data={data.territorial} busy={busy} onGeocode={onGeocode} expanded />
      <aside className="territorial-support">
        <Breakdown title="Por território" items={data.porTerritorio} />
        <Breakdown title="Por categoria" items={data.porCategoria} />
        <DemandAlertsPanel alerts={data.alertasDemanda} />
      </aside>
    </section>
  );
}

function MonthlyMandateReport() {
  const now = new Date();
  const [year, setYear] = useState(String(now.getFullYear()));
  const [month, setMonth] = useState(String(now.getMonth() + 1).padStart(2, "0"));
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadReport() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ ano: year, mes: month }).toString();
      setReport(await apiRequest(`/api/v1/painel/relatorio-mensal?${query}`));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mandate-report-workspace">
      <section className="mandate-report-panel">
        <header>
          <div>
            <h2>Relatório mensal do mandato</h2>
            <p>Resumo auditável do período, com indicadores agregados e evidências por protocolo.</p>
          </div>
          <FileText size={20} />
        </header>
        <div className="mandate-report-controls">
          <label>Mês<select value={month} onChange={(event) => setMonth(event.target.value)}>
            {Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, "0")).map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select></label>
          <label>Ano<input value={year} onChange={(event) => setYear(event.target.value)} inputMode="numeric" /></label>
          <button className="primary-button" disabled={loading} onClick={loadReport}>
            <FileText size={16} /> {loading ? "Gerando..." : "Gerar relatório"}
          </button>
        </div>
        {error && <p className="form-error">{error}</p>}
        {!report ? (
          <p className="muted-copy">Selecione o período e gere o relatório para revisar os resultados do mês.</p>
        ) : (
          <MonthlyReportContent report={report} />
        )}
      </section>
    </section>
  );
}

function MonthlyReportContent({ report }) {
  const summary = report.resumo || {};
  const summaryItems = [
    ["Recebidas", summary.solicitacoesRecebidas],
    ["Movimentadas", summary.solicitacoesMovimentadas],
    ["Encaminhadas", summary.encaminhadas],
    ["Resolvidas/encerradas", summary.resolvidasOuEncerradas],
    ["Em aberto", summary.emAbertoAoFimDoMes],
    ["Atrasadas", summary.atrasadasAoFimDoMes],
  ];
  return (
    <div className="mandate-report-content">
      <div className="mandate-report-period">
        <strong>{report.periodo?.rotulo}</strong>
        <span>{formatDate(`${report.periodo?.inicio}T00:00:00`)} a {formatDate(`${report.periodo?.fim}T00:00:00`)}</span>
      </div>
      <div className="mandate-report-summary">
        {summaryItems.map(([label, value]) => (
          <article key={label}><strong>{value || 0}</strong><span>{label}</span></article>
        ))}
      </div>
      <PrivacyAggregationNotice summary={report.privacidadeAgregacao} />
      <section className="mandate-report-section">
        <h3>Destaques</h3>
        {(report.destaques || []).length ? report.destaques.map((item) => (
          <article key={`${item.tipo}-${item.titulo}`}>
            <strong>{item.titulo}</strong>
            <span>{item.descricao}</span>
          </article>
        )) : <p className="muted-copy">Sem destaques com agregação mínima no período.</p>}
      </section>
      <section className="mandate-report-breakdowns">
        <Breakdown title="Por categoria" items={report.indicadores?.porCategoria || []} />
        <Breakdown title="Por território" items={report.indicadores?.porTerritorio || []} />
        <Breakdown title="Por órgão" items={report.indicadores?.porOrgao || []} />
      </section>
      <section className="mandate-report-section">
        <h3>Evidências rastreáveis</h3>
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
    </div>
  );
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

function TerritorialPanel({ data, busy, onGeocode, expanded = false }) {
  const points = data?.pontos || [];
  const hotspots = data?.hotspots || [];
  const heatmap = data?.heatmap || [];
  const jurisdiction = data?.jurisdicao;
  const privacy = data?.privacidade;
  const hasSuppressedTerritorialData = Boolean(
    privacy?.pontosSuprimidos || privacy?.hotspotsSuprimidos,
  );
  const visibleLimit = expanded ? 8 : 4;
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
        <span><strong>{formatPercent(data?.coberturaPercentual)}</strong><small>cobertura geográfica</small></span>
        <span><strong>{data?.semCoordenadas || 0}</strong><small>sem coordenadas</small></span>
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
      <div className="territorial-hotspots">
        <h3>Hotspots</h3>
        {hotspots.length ? hotspots.slice(0, visibleLimit).map((item) => (
          <div key={item.nome}>
            <span>{item.nome}</span>
            <strong>{item.abertas} abertas</strong>
          </div>
        )) : <p className="muted-copy">Sem agrupamentos territoriais.</p>}
      </div>
      <div className="territorial-heatmap">
        <h3>Mapa de calor</h3>
        <TerritorialHeatmapMap cells={heatmap} points={points} jurisdiction={jurisdiction} expanded={expanded} />
        {heatmap.length ? heatmap.slice(0, visibleLimit).map((item) => (
          <article key={`${item.territorio}-${item.latitude}-${item.longitude}`}>
            <span>{item.territorio}</span>
            <strong>{item.total} demanda(s)</strong>
            <small>{Number(item.latitude).toFixed(4)}, {Number(item.longitude).toFixed(4)}</small>
          </article>
        )) : <p className="muted-copy">Sem células de calor calculadas.</p>}
      </div>
      <div className="territorial-points">
        <h3>Pontos geocodificados</h3>
        {points.length ? points.slice(0, expanded ? 12 : 4).map((item) => (
          <article key={item.id}>
            <Navigation size={14} />
            <span><strong>{item.protocolo}</strong><small>{item.territorio} · {coordinateLabel(item)}</small></span>
          </article>
        )) : <p className="muted-copy">Nenhuma solicitação com coordenadas.</p>}
      </div>
    </section>
  );
}

function TerritorialHeatmapMap({ cells = [], points = [], jurisdiction = null, expanded = false }) {
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
          <g key={`${item.territorio}-${item.latitude}-${item.longitude}`}>
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
          <circle key={item.id || `${item.latitude}-${item.longitude}`} className="territorial-map-point" cx={item.x} cy={item.y} r="2.8">
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
  return `${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}`;
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
