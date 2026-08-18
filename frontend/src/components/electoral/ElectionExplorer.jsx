import { CheckCircle2, RefreshCw, Search, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../api";

const identityMessages = {
  manual_confirmed: {
    title: "Participação eleitoral confirmada",
    text: "A candidatura foi vinculada pela confirmação manual porque o cadastro oficial não permitiu validar o CPF automaticamente.",
  },
  verified: {
    title: "Identidade eleitoral verificada",
    text: "As participações encontradas pelo CPF cadastrado foram vinculadas automaticamente.",
  },
  cpf_missing: {
    title: "CPF não cadastrado",
    text: "Cadastre o CPF do parlamentar para ativar a vinculação automática. Enquanto isso, a confirmação manual permanece disponível.",
  },
  official_data_unavailable: {
    title: "Cadastro oficial ainda não sincronizado",
    text: "Não foi possível validar automaticamente esta participação. A confirmação manual está disponível como contingência.",
  },
  not_found: {
    title: "CPF não localizado no cadastro sincronizado",
    text: "Confira o CPF cadastrado. Se os dados oficiais estiverem divergentes, use a confirmação manual de contingência.",
  },
};

export function ElectionExplorer({ identity, onIdentityChanged, onError }) {
  const [elections, setElections] = useState([]);
  const [electionId, setElectionId] = useState("");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [searching, setSearching] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    apiRequest("/api/v1/electoral/elections/explore")
      .then((response) => {
        const items = response.items || [];
        setElections(items);
        setElectionId((current) => current || items[0]?.id || "");
      })
      .catch((requestError) => onError?.(requestError.message));
  }, [onError]);

  const confirmedIds = new Set((identity?.candidacies || []).map((item) => item.candidacy_id));
  const hasConfirmedCandidacies = confirmedIds.size > 0;
  const displayIdentityStatus = identity?.identityStatus === "verified"
    ? "verified"
    : hasConfirmedCandidacies ? "manual_confirmed" : identity?.identityStatus;
  const identityMessage = identityMessages[displayIdentityStatus] || identityMessages.official_data_unavailable;
  const identityConfirmed = displayIdentityStatus === "verified" || displayIdentityStatus === "manual_confirmed";

  function changeElection(nextElectionId) {
    setElectionId(nextElectionId);
    setCandidates([]);
    setResult(null);
  }

  async function reconcile() {
    setReconciling(true);
    try {
      await apiRequest("/api/v1/electoral/identity/reconcile", { method: "POST" });
      await onIdentityChanged?.();
    } catch (requestError) {
      onError?.(requestError.message);
    } finally {
      setReconciling(false);
    }
  }

  async function searchCandidates(event) {
    event.preventDefault();
    if (!electionId || query.trim().length < 2) return;
    setSearching(true);
    setResult(null);
    try {
      const params = new URLSearchParams({
        election_id: electionId,
        q: query.trim(),
        explore: "true",
      });
      const response = await apiRequest(`/api/v1/electoral/candidates?${params}`);
      setCandidates(response.items || []);
    } catch (requestError) {
      onError?.(requestError.message);
    } finally {
      setSearching(false);
    }
  }

  async function confirmManually(candidate) {
    setBusyId(candidate.candidacy_id);
    try {
      await apiRequest("/api/v1/electoral/identity/candidacies", {
        method: "POST",
        body: JSON.stringify({ candidacy_id: candidate.candidacy_id }),
      });
      await onIdentityChanged?.();
    } catch (requestError) {
      onError?.(requestError.message);
    } finally {
      setBusyId("");
    }
  }

  async function remove(candidacyId) {
    setBusyId(candidacyId);
    try {
      await apiRequest(`/api/v1/electoral/identity/candidacies/${candidacyId}`, {
        method: "DELETE",
      });
      await onIdentityChanged?.();
    } catch (requestError) {
      onError?.(requestError.message);
    } finally {
      setBusyId("");
    }
  }

  async function viewResult(candidate) {
    setBusyId(candidate.candidacy_id);
    try {
      const params = new URLSearchParams({
        election_id: electionId,
        level: "municipality",
        explore: "true",
      });
      setResult(await apiRequest(
        `/api/v1/electoral/candidates/${candidate.id}/results?${params}`,
      ));
    } catch (requestError) {
      onError?.(requestError.message);
    } finally {
      setBusyId("");
    }
  }

  return <section className="electoral-analysis-card electoral-explorer" aria-labelledby="electoral-explorer-title">
    <header>
      <div>
        <p className="eyebrow">Pesquisa eleitoral geral</p>
        <h2 id="electoral-explorer-title">Explorar outras eleições</h2>
        <p>Consulte o catálogo público sem alterar o contexto das análises do mandato.</p>
      </div>
    </header>

    <section className={`electoral-identity-status ${identityConfirmed ? "verified" : "pending"}`} aria-live="polite">
      {identityConfirmed ? <ShieldCheck size={21} aria-hidden="true" /> : <TriangleAlert size={21} aria-hidden="true" />}
      <span><strong>{identityMessage.title}</strong><small>{identityMessage.text}</small></span>
      {identity?.canManage && identity?.identityStatus !== "verified" && <button type="button" className="secondary-button" onClick={reconcile} disabled={reconciling}>
        <RefreshCw size={16} aria-hidden="true" /> {reconciling ? "Verificando..." : "Verificar novamente"}
      </button>}
    </section>

    {(identity?.candidacies || []).length > 0 && <section className="electoral-own-candidacies" aria-labelledby="own-candidacies-title">
      <h3 id="own-candidacies-title">Minhas participações</h3>
      <ul>{identity.candidacies.map((item) => <li key={item.id}>
        <span>
          <CheckCircle2 size={17} aria-hidden="true" />
          <span><strong>{item.candidate.ballot_name}</strong><small>{item.election.nome} · {item.candidate.number} · {item.candidate.party.acronym}</small></span>
        </span>
        <span className="electoral-identity-link-actions">
          <span className="electoral-confirmed-label">{item.automatic ? "Verificada pelo CPF" : "Confirmação manual"}</span>
          {identity.canManage && !item.automatic && <button type="button" className="secondary-button danger" disabled={busyId === item.candidacy_id} onClick={() => remove(item.candidacy_id)}>
            <Trash2 size={15} aria-hidden="true" /> Remover
          </button>}
        </span>
      </li>)}</ul>
    </section>}

    <form className="electoral-explorer-search" onSubmit={searchCandidates}>
      <label htmlFor="explorer-election">
        <span>Eleição</span>
        <span className="electoral-select-control">
          <select id="explorer-election" value={electionId} onChange={(event) => changeElection(event.target.value)} required>
            <option value="">Selecione uma eleição</option>
            {elections.map((election) => <option key={election.id} value={election.id}>{election.nome || election.name || election.year}</option>)}
          </select>
        </span>
      </label>
      <label htmlFor="explorer-query">
        <span>Nome ou número da candidatura</span>
        <input id="explorer-query" value={query} minLength={2} maxLength={120} onChange={(event) => setQuery(event.target.value)} placeholder="Digite nome ou número" />
      </label>
      <button type="submit" className="primary-button" disabled={!electionId || query.trim().length < 2 || searching}>
        <Search size={17} aria-hidden="true" /> {searching ? "Buscando..." : "Buscar"}
      </button>
    </form>

    {candidates.length > 0 && <div className="electoral-explorer-results" aria-label="Candidaturas encontradas">
      {candidates.map((candidate) => {
        const confirmed = confirmedIds.has(candidate.candidacy_id);
        return <article key={candidate.candidacy_id} className={confirmed ? "confirmed" : ""}>
          <span><strong>{candidate.ballot_name}</strong><small>{candidate.full_name}</small></span>
          <span>{candidate.number} · {candidate.party?.acronym} · {candidate.office?.name}</span>
          <div>
            <button type="button" className="secondary-button" disabled={busyId === candidate.candidacy_id} onClick={() => viewResult(candidate)}>Ver resultado público</button>
            {confirmed
              ? <span className="electoral-confirmed-label"><CheckCircle2 size={15} /> Participação vinculada</span>
              : identity?.canManage && identity?.manualFallbackAllowed && <button type="button" className="secondary-button" disabled={busyId === candidate.candidacy_id} onClick={() => confirmManually(candidate)}>Confirmar manualmente</button>}
          </div>
        </article>;
      })}
    </div>}

    {result && <section className="electoral-explorer-result" aria-labelledby="explorer-result-title">
      <header><h3 id="explorer-result-title">Resultado público de {result.candidate.ballot_name}</h3><strong>{result.candidate_total_votes.toLocaleString("pt-BR")} votos</strong></header>
      <div className="electoral-table-wrap"><table><thead><tr><th>Território</th><th>Votos</th><th>Participação</th><th>Posição</th></tr></thead><tbody>
        {result.items.map((item) => <tr key={item.territory_id}><td>{item.territory_name}</td><td>{item.votes.toLocaleString("pt-BR")}</td><td>{(item.share * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%</td><td>{item.rank}º</td></tr>)}
      </tbody></table></div>
    </section>}
  </section>;
}
