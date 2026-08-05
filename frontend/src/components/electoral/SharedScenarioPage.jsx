import { ArrowLeft, Eye, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";

export function SharedScenarioPage({ token }) {
  const [scenario, setScenario] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest(`/api/v1/electoral/scenarios/shared/${encodeURIComponent(token)}`)
      .then(setScenario)
      .catch((requestError) => setError(requestError.message));
  }, [token]);

  if (error) return <main className="shared-scenario-page">
    <section className="electoral-analysis-card" role="alert">
      <h1>Compartilhamento indisponível</h1>
      <p>{error}</p>
      <a className="secondary-button" href="/"><ArrowLeft size={17} /> Voltar ao GabFlow</a>
    </section>
  </main>;

  if (!scenario) return <main className="shared-scenario-page" aria-live="polite">
    <p>Carregando cenário compartilhado...</p>
  </main>;

  const candidate = scenario.baseline_snapshot?.candidate || {};
  const interval = scenario.result?.uncertainty_interval;
  return <main className="shared-scenario-page">
    <section className="electoral-analysis-card shared-scenario-document" aria-labelledby="shared-title">
      <header className="electoral-results-header">
        <div>
          <p className="eyebrow">Inteligência Eleitoral</p>
          <h1 id="shared-title">{scenario.name}</h1>
        </div>
        <span className="shared-readonly-badge"><Eye size={17} /> Somente leitura</span>
      </header>
      <p className="electoral-simulation-warning">{scenario.disclaimer}</p>
      <div className="shared-scenario-summary">
        <article><span>Candidatura</span><strong>{candidate.name || candidate.ballot_name || "Candidatura selecionada"}</strong></article>
        <article><span>Resultado oficial na base</span><strong>{scenario.result.baseline_total_votes.toLocaleString("pt-BR")} votos</strong></article>
        <article><span>Resultado no cenário</span><strong>{scenario.result.projected_total_votes.toLocaleString("pt-BR")} votos</strong></article>
        {interval && <article><span>Faixa de premissas</span><strong>{interval.lower_votes.toLocaleString("pt-BR")}–{interval.upper_votes.toLocaleString("pt-BR")}</strong></article>}
      </div>
      {interval && <p className="scenario-statistical-note"><ShieldCheck size={17} /> {interval.disclaimer || "Faixa determinística; não é intervalo de confiança estatístico."}</p>}
      <h2>Premissas territoriais</h2>
      <div className="electoral-table-wrapper"><table className="electoral-table">
        <thead><tr><th>Território</th><th>Participação</th><th>Denominador</th><th>Incertezas</th><th>Justificativa</th></tr></thead>
        <tbody>{scenario.assumptions.map((assumption) => {
          const territory = scenario.result.territories.find((item) => item.territory_id === assumption.territory_id);
          return <tr key={assumption.territory_id}>
            <td>{territory?.territory_name || assumption.territory_id}</td>
            <td>{formatPercentPoints(assumption.candidate_share_delta)}</td>
            <td>{formatPercent(assumption.denominator_delta)}</td>
            <td>±{formatPercentPoints(assumption.candidate_share_uncertainty)} / ±{formatPercent(assumption.denominator_uncertainty)}</td>
            <td>{assumption.rationale}</td>
          </tr>;
        })}</tbody>
      </table></div>
      <h2>Resultado territorial</h2>
      <div className="electoral-table-wrapper"><table className="electoral-table">
        <thead><tr><th>Território</th><th>Base oficial</th><th>Cenário</th><th>Diferença</th><th>Faixa</th></tr></thead>
        <tbody>{scenario.result.territories.map((territory) => <tr key={territory.territory_id}>
          <td>{territory.territory_name}</td>
          <td>{territory.baseline_votes.toLocaleString("pt-BR")}</td>
          <td>{territory.projected_votes.toLocaleString("pt-BR")}</td>
          <td>{signedNumber(territory.vote_difference)}</td>
          <td>{territory.uncertainty_interval.lower_votes.toLocaleString("pt-BR")}–{territory.uncertainty_interval.upper_votes.toLocaleString("pt-BR")}</td>
        </tr>)}</tbody>
      </table></div>
      <footer className="shared-scenario-footer">
        <span>Dataset {scenario.baseline_snapshot.dataset_version} · {scenario.methodology_version}</span>
        <span>Visualização protegida e sem ações de alteração.</span>
      </footer>
    </section>
  </main>;
}

function formatPercent(value = 0) { return `${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`; }
function formatPercentPoints(value = 0) { return `${value >= 0 ? "+" : ""}${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} p.p.`; }
function signedNumber(value) { return `${value >= 0 ? "+" : ""}${value.toLocaleString("pt-BR")}`; }
