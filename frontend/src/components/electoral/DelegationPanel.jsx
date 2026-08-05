import { KeyRound, UserRoundPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api";

const options = [
  ["consultar_dados_publicos", "Consultar dados públicos"],
  ["comparar_candidatos", "Comparar candidatos"],
  ["ver_camadas_mandato", "Ver camadas do mandato"],
  ["usar_ia", "Usar IA"],
  ["criar_cenario", "Criar cenário"],
  ["exportar", "Exportar relatórios"],
];

export function DelegationPanel({ onError }) {
  const [data, setData] = useState({ content: [], eligible_users: [] });
  const [grantee, setGrantee] = useState("");
  const [capabilities, setCapabilities] = useState(["consultar_dados_publicos"]);
  const [days, setDays] = useState(7);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await apiRequest("/api/v1/electoral/delegations"));
    } catch (error) {
      onError(error.message);
    }
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  function toggle(capability) {
    setCapabilities((current) => current.includes(capability)
      ? current.filter((item) => item !== capability)
      : [...current, capability]);
  }

  async function grant(event) {
    event.preventDefault();
    try {
      await apiRequest("/api/v1/electoral/delegations", {
        method: "POST",
        body: JSON.stringify({ grantee_user_id: grantee, capabilities, valid_days: days, reason }),
      });
      setReason("");
      await load();
    } catch (error) {
      onError(error.message);
    }
  }

  async function revoke(id) {
    try {
      await apiRequest(`/api/v1/electoral/delegations/${id}`, { method: "DELETE" });
      await load();
    } catch (error) {
      onError(error.message);
    }
  }

  return (
    <section className="electoral-analysis-card electoral-delegation-panel" aria-labelledby="delegation-title">
      <header className="electoral-results-header"><div><p className="eyebrow">Acesso temporário</p><h2 id="delegation-title">Delegação granular</h2></div><KeyRound size={26} aria-hidden="true" /></header>
      <form className="electoral-delegation-form" onSubmit={grant}>
        <label>Assessor
          <select value={grantee} onChange={(event) => setGrantee(event.target.value)} required><option value="">Selecione</option>{data.eligible_users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select>
        </label>
        <label>Prazo em dias<input type="number" min="1" max="90" value={days} onChange={(event) => setDays(Number(event.target.value))} /></label>
        <fieldset><legend>Capacidades</legend>{options.map(([value, label]) => <label key={value}><input type="checkbox" checked={capabilities.includes(value)} onChange={() => toggle(value)} /> {label}</label>)}</fieldset>
        <label className="electoral-delegation-reason">Motivo obrigatório<input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} /></label>
        <button className="primary-button" disabled={!grantee || !capabilities.length || reason.trim().length < 10}><UserRoundPlus size={16} /> Conceder acesso</button>
      </form>
      <div className="electoral-job-list">{data.content.map((item) => <article className="electoral-job-row" key={item.id}><div><strong>{item.grantee_name}</strong><small>{item.capabilities.join(", ")}</small><span>{item.active ? `Ativa até ${new Date(item.valid_until).toLocaleDateString("pt-BR")}` : "Inativa"}</span></div>{item.active && <button className="danger-button" type="button" onClick={() => revoke(item.id)}>Revogar</button>}</article>)}</div>
    </section>
  );
}
