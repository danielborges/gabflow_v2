function percentage(value) {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 2,
  }).format(value);
}

export function CandidateHistory({ response, loading, selectedCandidateId, onReview }) {
  if (loading) return <p aria-live="polite">Carregando histórico eleitoral...</p>;
  if (!response?.items?.length) return null;
  return (
    <section className="electoral-analysis-card" aria-labelledby="candidate-history-title">
      <header><div><p className="eyebrow">Comparação entre eleições</p><h2 id="candidate-history-title">Histórico da candidatura</h2></div></header>
      {!response.identity.reviewed && <p className="electoral-warning" role="status">{response.identity.warning}</p>}
      {!response.identity.reviewed && response.items.length > 1 && (
        <button type="button" className="secondary-button" onClick={() => onReview(response.items.map((item) => item.candidate.id).filter((id) => id !== selectedCandidateId))}>Confirmar vínculo de identidade</button>
      )}
      {response.warnings?.map((warning) => <p className="electoral-warning" key={warning.code}>{warning.message}</p>)}
      <div className="electoral-table-wrap">
        <table>
          <caption>Candidaturas publicadas associadas à mesma pessoa</caption>
          <thead><tr><th>Ano</th><th>Partido</th><th>Número</th><th>Votos</th><th>Participação</th><th>Posição</th></tr></thead>
          <tbody>{response.items.map((item) => (
            <tr key={item.candidate.candidacy_id}>
              <td>{item.candidate.election.year}</td><td>{item.candidate.party.acronym}</td><td>{item.candidate.number}</td>
              <td>{item.candidate_total_votes.toLocaleString("pt-BR")}</td><td>{percentage(item.territory?.share)}</td>
              <td>{item.territory?.rank ? `${item.territory.rank}º` : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}
