import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  FileCheck2,
  Forward,
  ListTodo,
  MapPin,
  MapPinned,
  MessageSquareReply,
  Navigation,
  RotateCcw,
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

export function OperationalDashboard({ onOpenRequests }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [geocoding, setGeocoding] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await apiRequest("/api/v1/painel/operacional"));
    } catch (requestError) {
      setError(requestError.message);
    }
  }, []);

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
          <TerritorialPanel data={data.territorial} busy={geocoding} onGeocode={geocodePending} />
        </div>
      </section>
    </>
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

function TerritorialPanel({ data, busy, onGeocode }) {
  const points = data?.pontos || [];
  const hotspots = data?.hotspots || [];
  const heatmap = data?.heatmap || [];
  return (
    <section className="breakdown territorial-panel">
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
      <div className="territorial-hotspots">
        <h3>Hotspots</h3>
        {hotspots.length ? hotspots.slice(0, 4).map((item) => (
          <div key={item.nome}>
            <span>{item.nome}</span>
            <strong>{item.abertas} abertas</strong>
          </div>
        )) : <p className="muted-copy">Sem agrupamentos territoriais.</p>}
      </div>
      <div className="territorial-heatmap">
        <h3>Mapa de calor</h3>
        <TerritorialHeatmapMap cells={heatmap} points={points} />
        {heatmap.length ? heatmap.slice(0, 4).map((item) => (
          <article key={`${item.territorio}-${item.latitude}-${item.longitude}`}>
            <span>{item.territorio}</span>
            <strong>{item.total} demanda(s)</strong>
            <small>{Number(item.latitude).toFixed(4)}, {Number(item.longitude).toFixed(4)}</small>
          </article>
        )) : <p className="muted-copy">Sem células de calor calculadas.</p>}
      </div>
      <div className="territorial-points">
        <h3>Pontos geocodificados</h3>
        {points.length ? points.slice(0, 4).map((item) => (
          <article key={item.id}>
            <Navigation size={14} />
            <span><strong>{item.protocolo}</strong><small>{item.territorio} · {coordinateLabel(item)}</small></span>
          </article>
        )) : <p className="muted-copy">Nenhuma solicitação com coordenadas.</p>}
      </div>
    </section>
  );
}

function TerritorialHeatmapMap({ cells = [], points = [] }) {
  const coordinates = [...cells, ...points].filter(hasCoordinates);
  if (!coordinates.length) {
    return (
      <div className="territorial-map empty">
        <MapPin size={20} />
        <span>Sem coordenadas para desenhar o mapa.</span>
      </div>
    );
  }

  const bounds = coordinateBounds(coordinates);
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

  return (
    <div className="territorial-map" aria-label="Mapa visual de calor territorial" role="img">
      <svg viewBox="0 0 320 210" preserveAspectRatio="none">
        <defs>
          <linearGradient id="territorialMapBase" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#eefbfc" />
            <stop offset="100%" stopColor="#f8fbff" />
          </linearGradient>
        </defs>
        <rect className="territorial-map-base" x="0" y="0" width="320" height="210" rx="8" />
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

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(value));
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
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

function coordinateBounds(items) {
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
