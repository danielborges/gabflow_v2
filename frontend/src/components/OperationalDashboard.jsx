import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  ListTodo,
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
          <p>Prioridades, prazos e distribuição das demandas em um único lugar.</p>
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
        </div>
      </section>
    </>
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
