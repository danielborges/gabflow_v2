import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";

const metrics = {
  votes: { label: "Votos", format: (value) => value.toLocaleString("pt-BR") },
  share: { label: "Participação", format: (value) => new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2 }).format(value) },
  rank: { label: "Posição", format: (value) => `${value}º` },
};

export function CandidateComparison({
  elections = [],
  electionId,
  onElectionChange,
  selected,
  response,
  loading,
  onCompare,
  onToggle,
  onRemove,
  onSave,
  saved = [],
  onLoadSaved,
  onDeleteSaved,
  onError,
}) {
  const [metric, setMetric] = useState("votes");
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    setOptions([]);
    setSearched(false);
  }, [electionId]);

  async function searchCandidates(event) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!electionId || normalizedQuery.length < 2) return;
    setSearching(true);
    setSearched(true);
    try {
      const params = new URLSearchParams({ election_id: electionId, q: normalizedQuery });
      const result = await apiRequest(`/api/v1/electoral/candidates?${params}`);
      setOptions(result.items || []);
    } catch (requestError) {
      setOptions([]);
      onError?.(requestError.message);
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="electoral-analysis-card electoral-comparison-card" aria-labelledby="candidate-comparison-title">
      <header>
        <div>
          <p className="eyebrow">Comparação eleitoral</p>
          <h2 id="candidate-comparison-title">Comparar candidaturas</h2>
          <p>Pesquise e reúna de duas a cinco candidaturas da mesma eleição.</p>
        </div>
        <small className="electoral-comparison-count">{selected.length}/5 selecionadas</small>
      </header>

      <section className="electoral-comparison-selector" aria-labelledby="comparison-selector-title">
        <h3 id="comparison-selector-title">Escolha as candidaturas</h3>
        <div className="electoral-comparison-controls">
          <label htmlFor="comparison-election">
            <span>Eleição</span>
            <span className="electoral-select-control">
              <select id="comparison-election" value={electionId} onChange={(event) => onElectionChange(event.target.value)} required>
                <option value="">Selecione uma eleição</option>
                {elections.map((election) => <option key={election.id} value={election.id}>
                  {election.nome || election.name || election.year}
                </option>)}
              </select>
            </span>
          </label>
          <form className="electoral-comparison-search" onSubmit={searchCandidates}>
            <label htmlFor="comparison-candidate-query">
              <span>Buscar candidatura</span>
              <input
                id="comparison-candidate-query"
                value={query}
                minLength={2}
                maxLength={120}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Digite nome ou número"
              />
            </label>
            <button type="submit" className="secondary-button" disabled={!electionId || query.trim().length < 2 || searching}>
              <Search size={17} aria-hidden="true" />
              {searching ? "Buscando..." : "Buscar"}
            </button>
          </form>
        </div>

        {options.length > 0 && <div className="electoral-comparison-options" aria-label="Candidaturas encontradas">
          {options.map((candidate) => {
            const isSelected = selected.some((item) => item.id === candidate.id);
            const limitReached = selected.length >= 5 && !isSelected;
            return <button
              type="button"
              key={candidate.id}
              className={isSelected ? "selected" : ""}
              aria-pressed={isSelected}
              disabled={limitReached}
              onClick={() => onToggle(candidate)}
            >
              <span><strong>{candidate.ballot_name}</strong><small>{candidate.full_name}</small></span>
              <span>{candidate.number} · {candidate.party?.acronym}</span>
              <b>{isSelected ? "Selecionada" : limitReached ? "Limite atingido" : "Selecionar"}</b>
            </button>;
          })}
        </div>}
        {searched && !searching && options.length === 0 && <p className="electoral-comparison-hint" role="status">Nenhuma candidatura encontrada para esta busca.</p>}
        {!searched && selected.length === 0 && <p className="electoral-comparison-hint">Busque por nome ou número para iniciar a comparação.</p>}

        {selected.length > 0 && <div className="electoral-comparison-selected" aria-label="Candidaturas selecionadas">
          <strong>Selecionadas</strong>
          <div>{selected.map((candidate) => <span key={candidate.id}>
            {candidate.ballot_name}
            <button type="button" aria-label={`Remover ${candidate.ballot_name}`} onClick={() => onRemove(candidate.id)}><X size={14} aria-hidden="true" /></button>
          </span>)}</div>
        </div>}
      </section>

      <div className="electoral-comparison-actionbar">
        <label htmlFor="comparison-metric">
          <span>Métrica</span>
          <span className="electoral-select-control">
            <select id="comparison-metric" value={metric} onChange={(event) => setMetric(event.target.value)}>
              {Object.entries(metrics).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
            </select>
          </span>
        </label>
        <div>
          {selected.length === 1 && <small>Selecione mais uma candidatura para continuar.</small>}
          <button className="primary-button" type="button" disabled={selected.length < 2 || loading} onClick={onCompare}>
            {loading ? "Comparando..." : `Comparar ${selected.length} candidaturas`}
          </button>
        </div>
      </div>

      {response?.items?.length > 0 && <>
        <p className="electoral-method"><strong>Denominador:</strong> {response.denominator.label}.</p>
        <div className="electoral-save-comparison"><label>Nome do comparativo<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Vereadores de Juiz de Fora" /></label><button type="button" className="secondary-button" disabled={!name.trim()} onClick={() => { onSave(name.trim()); setName(""); }}>Salvar comparativo</button></div>
        <div className="electoral-table-wrap"><table>
          <caption>Comparativo territorial por {metrics[metric].label.toLowerCase()}</caption>
          <thead><tr><th>Território</th>{response.candidates.map((candidate) => <th key={candidate.id}>{candidate.ballot_name}</th>)}<th>Denominador</th></tr></thead>
          <tbody>{response.items.map((territory) => <tr key={territory.territory_code}>
            <td>{territory.territory_name}</td>
            {response.candidates.map((candidate) => {
              const series = territory.series.find((item) => item.candidate_id === candidate.id);
              return <td key={candidate.id}>{series ? metrics[metric].format(series[metric]) : "—"}</td>;
            })}
            <td>{territory.denominator_value.toLocaleString("pt-BR")}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
      {saved.length > 0 && <div className="electoral-saved-list"><h3>Comparativos salvos</h3><ul>{saved.map((item) => <li key={item.id}><button type="button" className="electoral-territory-link" onClick={() => onLoadSaved(item)}>{item.name}</button><button type="button" className="secondary-button" aria-label={`Excluir comparativo ${item.name}`} onClick={() => onDeleteSaved(item.id)}>Excluir</button></li>)}</ul></div>}
    </section>
  );
}
