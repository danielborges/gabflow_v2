export function CandidateSearch({
  elections,
  filters,
  onFiltersChange,
  onSubmit,
  loading,
  response,
  selectedCandidateId,
  onSelect,
  onPageChange,
  comparisonCandidates = [],
  onToggleComparison,
  favorites = [],
  onToggleFavorite,
}) {
  return (
    <section className="electoral-analysis-card" aria-labelledby="candidate-search-title">
      <header>
        <div>
          <p className="eyebrow">Primeira fatia analítica</p>
          <h2 id="candidate-search-title">Pesquisar candidatura</h2>
        </div>
      </header>
      <form className="electoral-search-form" onSubmit={onSubmit}>
        <label>
          Eleição
          <select
            value={filters.electionId}
            onChange={(event) => onFiltersChange({ electionId: event.target.value })}
            required
          >
            <option value="">Selecione</option>
            {elections.map((election) => (
              <option key={election.id} value={election.id}>
                {election.year} · {election.nome || election.name} · {election.uf}
              </option>
            ))}
          </select>
        </label>
        <label className="electoral-search-query">
          Nome ou número
          <input
            value={filters.q}
            onChange={(event) => onFiltersChange({ q: event.target.value })}
            placeholder="Ex.: Maurício Delgado ou 18010"
            minLength={2}
            maxLength={120}
            required
          />
        </label>
        <label>
          Partido
          <input
            value={filters.party}
            onChange={(event) => onFiltersChange({ party: event.target.value })}
            placeholder="Ex.: REDE"
          />
        </label>
        <label>
          Cargo
          <input
            value={filters.office}
            onChange={(event) => onFiltersChange({ office: event.target.value })}
            placeholder="Ex.: Vereador"
          />
        </label>
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? "Pesquisando..." : "Pesquisar"}
        </button>
      </form>

      {response && response.total === 0 && (
        <p className="electoral-empty" role="status">Nenhuma candidatura encontrada para os filtros.</p>
      )}
      {response?.items?.length > 0 && (
        <>
        <div className="electoral-table-wrap">
          <table>
            <caption>{response.total} candidatura(s) encontrada(s)</caption>
            <thead>
              <tr>
                <th scope="col">Candidatura</th>
                <th scope="col">Número</th>
                <th scope="col">Partido</th>
                <th scope="col">Cargo</th>
                <th scope="col">Comparar</th>
                <th scope="col">Favorito</th>
                <th scope="col"><span className="sr-only">Ação</span></th>
              </tr>
            </thead>
            <tbody>
              {response.items.map((candidate) => (
                <tr key={candidate.candidacy_id}>
                  <td><strong>{candidate.ballot_name}</strong><small>{candidate.full_name}</small></td>
                  <td>{candidate.number}</td>
                  <td>{candidate.party.acronym} · {candidate.party.number}</td>
                  <td>{candidate.office.name}</td>
                  <td>
                    <label>
                      <input
                        type="checkbox"
                        checked={comparisonCandidates.some((item) => item.id === candidate.id)}
                        disabled={comparisonCandidates.length >= 5 && !comparisonCandidates.some((item) => item.id === candidate.id)}
                        onChange={() => onToggleComparison(candidate)}
                      />
                      Incluir
                    </label>
                  </td>
                  <td><button type="button" className="secondary-button" aria-label={`${favorites.some((item) => item.target_id === candidate.id) ? "Remover dos" : "Adicionar aos"} favoritos: ${candidate.ballot_name}`} onClick={() => onToggleFavorite(candidate)}>{favorites.some((item) => item.target_id === candidate.id) ? "★" : "☆"}</button></td>
                  <td>
                    <button
                      type="button"
                      className={candidate.id === selectedCandidateId ? "secondary-button active" : "secondary-button"}
                      onClick={() => onSelect(candidate)}
                    >
                      {candidate.id === selectedCandidateId ? "Selecionado" : "Ver resultado"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="electoral-pagination" aria-label="Paginação de candidaturas">
          <button type="button" className="secondary-button" disabled={response.page <= 1} onClick={() => onPageChange(response.page - 1)}>Anterior</button>
          <span>Página {response.page}</span>
          <button type="button" className="secondary-button" disabled={response.page * response.perPage >= response.total} onClick={() => onPageChange(response.page + 1)}>Próxima</button>
        </div>
        </>
      )}
    </section>
  );
}
