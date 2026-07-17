import { Activity, BrainCircuit, CheckCircle2, Clock3, RefreshCw, UserCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

export function AIQualityPage() {
  const [days, setDays] = useState("30");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await apiRequest(`/api/v1/ia/qualidade-triagem?dias=${days}`));
    } catch (requestError) {
      setError(requestError.message);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <p className="form-error dashboard-error">{error}</p>;
  if (!data) return <div className="table-message dashboard-loading">Carregando qualidade da IA...</div>;

  const metrics = [
    ["Execuções", data.indicadores.execucoes, BrainCircuit],
    ["Taxa de conclusão", percentage(data.indicadores.taxaConclusao), CheckCircle2],
    ["Aceitação humana", percentage(data.indicadores.taxaAceitacao), UserCheck],
    ["Intervenção humana", percentage(data.indicadores.taxaIntervencaoHumana), Activity],
    ["Confiança média", percentage(data.indicadores.confiancaMedia), Activity],
    ["Latência média", duration(data.indicadores.latenciaMediaMs), Clock3],
  ];

  return (
    <>
      <section className="page-heading ai-quality-heading">
        <div>
          <p className="eyebrow">Governança de IA</p>
          <h1>Qualidade da triagem</h1>
          <p>Acompanhe confiança, revisão humana e cobertura das sugestões do tenant.</p>
        </div>
        <div className="quality-controls">
          <label>
            <span>Período</span>
            <select value={days} onChange={(event) => setDays(event.target.value)}>
              <option value="30">30 dias</option>
              <option value="90">90 dias</option>
              <option value="180">180 dias</option>
              <option value="365">12 meses</option>
            </select>
          </label>
          <button className="icon-button" onClick={load} title="Atualizar métricas" aria-label="Atualizar métricas"><RefreshCw size={19} /></button>
        </div>
      </section>

      {!data.amostraMinimaAtingida && (
        <p className="quality-sample-note">Amostra inicial: as taxas ganham maior estabilidade após 30 revisões humanas.</p>
      )}

      <section className="metric-grid ai-quality-metrics">
        {metrics.map(([label, value, Icon]) => (
          <article key={label} className="metric-neutral">
            <Icon size={20} />
            <div><strong>{value}</strong><span>{label}</span></div>
          </article>
        ))}
      </section>

      <section className="ai-quality-layout">
        <QualityBreakdown title="Revisão humana" rows={[
          ["Pendentes", data.revisoes.pendentes],
          ["Aceitas", data.revisoes.aceitas],
          ["Editadas", data.revisoes.editadas],
          ["Rejeitadas", data.revisoes.rejeitadas],
        ]} />
        <QualityBreakdown title="Cobertura da análise" rows={[
          ["Com entidades", data.cobertura.entidadesExtraidas],
          ["Com órgão sugerido", data.cobertura.orgaosSugeridos],
          ["Linguagem sensível", data.cobertura.conteudoOfensivoSinalizado],
          ["Possíveis emergências", data.cobertura.emergenciasSinalizadas],
          ["Análises de duplicidade", data.cobertura.analisesDuplicidade],
          ["Candidatos similares", data.cobertura.candidatosDuplicidade],
          ["Áudios transcritos", data.cobertura.audiosTranscritos],
          ["Transcrições revisadas", data.cobertura.transcricoesRevisadas],
          ["Falhas de transcrição", data.cobertura.falhasTranscricao],
          ["Documentos com OCR", data.cobertura.documentosProcessadosOcr],
          ["OCRs revisados", data.cobertura.ocrRevisados],
          ["Confiança média do OCR", percentage(data.cobertura.confiancaMediaOcr)],
          ["Falhas de OCR", data.cobertura.falhasOcr],
        ]} />
        <QualityBreakdown title="Controles" rows={[
          ["Concordância de categoria", percentage(data.indicadores.concordanciaCategoria)],
          ["Uso de fallback", percentage(data.indicadores.taxaFallback)],
          ["Falhas", data.indicadores.falhas],
          ["Revisadas", data.indicadores.revisadas],
        ]} />
      </section>

      <section className="ai-model-table">
        <header><h2>Desempenho por modelo</h2><p>Comparação das execuções registradas no período.</p></header>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Provedor</th><th>Modelo</th><th>Execuções</th><th>Confiança</th><th>Latência</th></tr></thead>
            <tbody>{data.porModelo.map((item) => <tr key={`${item.provedor}-${item.modelo}`}>
              <td>{item.provedor}</td><td><strong>{item.modelo}</strong></td><td>{item.execucoes}</td><td>{percentage(item.confiancaMedia)}</td><td>{duration(item.latenciaMediaMs)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function QualityBreakdown({ title, rows }) {
  return <section className="quality-breakdown"><h2>{title}</h2>{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? "—"}</strong></div>)}</section>;
}

function percentage(value) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function duration(value) {
  if (value == null) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}
