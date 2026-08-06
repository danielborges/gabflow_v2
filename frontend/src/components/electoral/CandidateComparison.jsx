import { useState } from "react";

const metrics = {
  votes: { label: "Votos", format: (value) => value.toLocaleString("pt-BR") },
  share: { label: "Participação", format: (value) => new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2 }).format(value) },
  rank: { label: "Posição", format: (value) => `${value}º` },
};

export function CandidateComparison({ selected, response, loading, onCompare, onRemove, onSave, saved = [], onLoadSaved, onDeleteSaved }) {
  const [metric, setMetric] = useState("votes");
  const [name, setName] = useState("");
  return (
    <section className="electoral-analysis-card" aria-labelledby="candidate-comparison-title">
      <header className="electoral-results-header">
        <div><p className="eyebrow">Incremento 3</p><h2 id="candidate-comparison-title">Comparar candidaturas</h2></div>
        <label>Métrica<select value={metric} onChange={(event) => setMetric(event.target.value)}>{Object.entries(metrics).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select></label>
      </header>
      {!selected.length && <div className="electoral-empty electoral-empty-guidance">
        <strong>Nenhuma candidatura selecionada.</strong>
        <span>Abra Resultados eleitorais e marque de duas a cinco candidaturas.</span>
      </div>}
      <div className="electoral-comparison-basket">{selected.map((candidate) => (
        <span key={candidate.id}>{candidate.ballot_name}<button type="button" aria-label={`Remover ${candidate.ballot_name}`} onClick={() => onRemove(candidate.id)}>×</button></span>
      ))}</div>
      {selected.length > 0 && <button className="primary-button" type="button" disabled={selected.length < 2 || loading} onClick={onCompare}>{loading ? "Comparando..." : `Comparar ${selected.length} candidaturas`}</button>}
      {selected.length === 1 && <p className="electoral-empty">Selecione pelo menos duas candidaturas da mesma eleição.</p>}
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
