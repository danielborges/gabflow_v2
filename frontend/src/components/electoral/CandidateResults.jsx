function percentage(value) {
  return new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2 }).format(value);
}

export function CandidateResults({ response, loading, level, onLevelChange, onSort, onPageChange, selectedTerritoryCode, onTerritorySelect }) {
  if (loading) return <p aria-live="polite">Calculando resultado territorial...</p>;
  if (!response) return null;
  const candidate = response.candidate;
  return (
    <section className="electoral-analysis-card" aria-labelledby="candidate-results-title">
      <header className="electoral-results-header">
        <div>
          <p className="eyebrow">Resultado oficial</p>
          <h2 id="candidate-results-title">{candidate.ballot_name}</h2>
          <p>{candidate.number} · {candidate.party.acronym} · {candidate.office.name}</p>
        </div>
        <label>
          Nível territorial
          <select value={level} onChange={(event) => onLevelChange(event.target.value)}>
            <option value="municipality">Município</option>
            <option value="electoral_zone">Zona eleitoral</option>
          </select>
        </label>
      </header>

      <div className="electoral-result-summary">
        <div><span>Total do candidato</span><strong>{response.candidate_total_votes.toLocaleString("pt-BR")}</strong></div>
        <div><span>Dataset</span><strong>{response.dataset_version.slice(0, 8)}</strong></div>
        <div><span>Qualidade</span><strong>{response.quality_score}</strong></div>
      </div>
      <p className="electoral-method">
        <strong>Denominador:</strong> {response.denominator.label}. Fórmula: {response.denominator.formula}.
      </p>

      {response.items.length === 0 ? (
        <p className="electoral-empty" role="status">Não há resultado nesse nível territorial.</p>
      ) : (
        <div className="electoral-table-wrap">
          <table>
            <caption>Desempenho territorial de {candidate.ballot_name}</caption>
            <thead>
              <tr>
                <th scope="col"><button type="button" onClick={() => onSort("name")}>Território</button></th>
                <th scope="col"><button type="button" onClick={() => onSort("votes")}>Votos</button></th>
                <th scope="col"><button type="button" onClick={() => onSort("share")}>Participação</button></th>
                <th scope="col"><button type="button" onClick={() => onSort("rank")}>Posição</button></th>
                <th scope="col">Denominador</th>
              </tr>
            </thead>
            <tbody>
              {response.items.map((item) => (
                <tr key={item.territory_id} className={selectedTerritoryCode === item.territory_code ? "selected" : ""}>
                  <td><button type="button" className="electoral-territory-link" onClick={() => onTerritorySelect(item.territory_code)}>{item.territory_name}</button>{item.quality_warning && <small>{item.quality_warning}</small>}</td>
                  <td>{item.votes.toLocaleString("pt-BR")}</td>
                  <td>{percentage(item.share)}</td>
                  <td>{item.rank}º</td>
                  <td>{item.denominator_value.toLocaleString("pt-BR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {response.total > 0 && (
        <div className="electoral-pagination" aria-label="Paginação de resultados territoriais">
          <button type="button" className="secondary-button" disabled={response.page <= 1} onClick={() => onPageChange(response.page - 1)}>Anterior</button>
          <span>Página {response.page}</span>
          <button type="button" className="secondary-button" disabled={response.page * response.perPage >= response.total} onClick={() => onPageChange(response.page + 1)}>Próxima</button>
        </div>
      )}
      <footer className="electoral-provenance">
        Fonte: <a href={response.source} target="_blank" rel="noreferrer">Tribunal Superior Eleitoral</a>
        <span>Versão {response.dataset_version}</span>
      </footer>
    </section>
  );
}
