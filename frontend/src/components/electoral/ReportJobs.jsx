import { Download, FileDown, RefreshCw, ShieldX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api";

const statusLabels = {
  QUEUED: "Na fila",
  PROCESSING: "Gerando",
  COMPLETED: "Concluída",
  FAILED: "Falhou",
  REVOKED: "Revogada",
};

export function ReportJobs({ electionId, selectedCandidate, comparisonCandidates, level, onError }) {
  const [jobs, setJobs] = useState([]);
  const [format, setFormat] = useState("PDF");
  const [reportType, setReportType] = useState("candidate");
  const [purpose, setPurpose] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadJobs = useCallback(async () => {
    try {
      const response = await apiRequest("/api/v1/electoral/report-jobs");
      setJobs(response.content || []);
    } catch (error) {
      onError(error.message);
    }
  }, [onError]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!jobs.some((job) => ["QUEUED", "PROCESSING"].includes(job.status))) return undefined;
    const timer = window.setInterval(loadJobs, 3000);
    return () => window.clearInterval(timer);
  }, [jobs, loadJobs]);

  const candidateIds = reportType === "candidate"
    ? selectedCandidate ? [selectedCandidate.id] : []
    : comparisonCandidates.map((candidate) => candidate.id);
  const selectionValid = reportType === "candidate" ? candidateIds.length === 1 : candidateIds.length >= 2;

  async function createJob(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const created = await apiRequest("/api/v1/electoral/report-jobs", {
        method: "POST",
        body: JSON.stringify({
          format,
          report_type: reportType,
          purpose,
          election_id: electionId,
          candidate_ids: candidateIds,
          level,
        }),
      });
      setJobs((current) => [created, ...current]);
      setPurpose("");
    } catch (error) {
      onError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function action(job, actionName, method = "POST") {
    try {
      const suffix = actionName ? `/${actionName}` : "";
      const response = await apiRequest(`/api/v1/electoral/report-jobs/${job.id}${suffix}`, { method });
      if (actionName === "share") {
        window.location.assign(response.download_url);
      } else {
        await loadJobs();
      }
    } catch (error) {
      onError(error.message);
    }
  }

  return (
    <section className="electoral-analysis-card electoral-report-panel" aria-labelledby="electoral-reports-title">
      <header className="electoral-results-header">
        <div><p className="eyebrow">Exportações auditáveis</p><h2 id="electoral-reports-title">Relatórios e tabelas</h2></div>
        <FileDown size={26} aria-hidden="true" />
      </header>
      <form className="electoral-export-form" onSubmit={createJob}>
        <label>Conteúdo
          <select value={reportType} onChange={(event) => setReportType(event.target.value)}>
            <option value="candidate">Candidato selecionado</option>
            <option value="comparison">Comparação atual</option>
          </select>
        </label>
        <label>Formato
          <select value={format} onChange={(event) => setFormat(event.target.value)}>
            <option value="PDF">PDF</option><option value="CSV">CSV</option><option value="XLSX">XLSX</option>
          </select>
        </label>
        <label className="electoral-export-purpose">Finalidade obrigatória
          <input value={purpose} maxLength={500} onChange={(event) => setPurpose(event.target.value)} placeholder="Ex.: análise interna para planejamento territorial" />
        </label>
        <button className="primary-button" disabled={submitting || !selectionValid || purpose.trim().length < 10}>
          {submitting ? "Enfileirando..." : "Gerar exportação"}
        </button>
      </form>
      {!selectionValid && <p className="electoral-method">Selecione um candidato ou monte uma comparação com pelo menos dois.</p>}
      <div className="electoral-job-list">
        {jobs.length === 0 && <p className="electoral-empty">Nenhuma exportação solicitada.</p>}
        {jobs.map((job) => (
          <article key={job.id} className="electoral-job-row">
            <div><strong>{job.format} · {job.report_type === "candidate" ? "Candidato" : "Comparação"}</strong><small>{job.purpose}</small><span className={`electoral-job-status status-${job.status.toLowerCase()}`}>{statusLabels[job.status]}</span></div>
            <div className="electoral-job-actions">
              {job.status === "COMPLETED" && job.report?.available && <button type="button" className="secondary-button" onClick={() => action(job, "share")}><Download size={16} /> Baixar</button>}
              {job.status === "FAILED" && <button type="button" className="secondary-button" onClick={() => action(job, "retry")}><RefreshCw size={16} /> Tentar novamente</button>}
              {!job.revoked_at && <button type="button" className="danger-button" onClick={() => action(job, "", "DELETE")}><ShieldX size={16} /> Revogar</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
