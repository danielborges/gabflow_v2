import { useMemo } from "react";

const metricLabels = {
  votes: "Votos",
  share: "Participação",
  rank: "Posição",
  variation: "Variação",
};

function coordinatesFromGeometry(geometry) {
  const points = [];
  function visit(value) {
    if (Array.isArray(value) && typeof value[0] === "number") points.push(value);
    else if (Array.isArray(value)) value.forEach(visit);
  }
  visit(geometry.coordinates);
  return points;
}

function pathForGeometry(geometry, project) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.flatMap((polygon) => polygon.map((ring) => ring.map((point, index) => {
    const [x, y] = project(point);
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ") + " Z")).join(" ");
}

export function CandidateMap({ response, metric, onMetricChange, selectedCode, onSelect }) {
  const projection = useMemo(() => {
    const points = response?.features?.flatMap((feature) => coordinatesFromGeometry(feature.geometry)) || [];
    if (!points.length) return null;
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    const minX = Math.min(...xs); const maxX = Math.max(...xs);
    const minY = Math.min(...ys); const maxY = Math.max(...ys);
    const scale = Math.min(680 / Math.max(maxX - minX, 0.001), 380 / Math.max(maxY - minY, 0.001));
    return (point) => [20 + (point[0] - minX) * scale, 400 - (point[1] - minY) * scale];
  }, [response]);
  if (!response) return null;
  if (!response.geometry_available) {
    return <section className="electoral-analysis-card"><h2>Mapa territorial</h2><p className="electoral-warning">{response.warning}</p></section>;
  }
  const values = response.features.map((feature) => feature.properties[metric]).filter((value) => value != null);
  const min = Math.min(...values); const max = Math.max(...values);
  function fill(value) {
    if (value == null) return "#e5e7eb";
    const normalized = max === min ? 0.75 : (value - min) / (max - min);
    const intensity = metric === "rank" ? 1 - normalized : normalized;
    return `rgba(20, 99, 155, ${0.25 + intensity * 0.7})`;
  }
  return (
    <section className="electoral-analysis-card" aria-labelledby="candidate-map-title">
      <header className="electoral-results-header">
        <div><p className="eyebrow">Geometria oficial</p><h2 id="candidate-map-title">Mapa territorial</h2></div>
        <label>Métrica<select value={metric} onChange={(event) => onMetricChange(event.target.value)}>{Object.entries(metricLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </header>
      {response.warnings?.map((warning) => <p className="electoral-warning" key={warning}>{warning}</p>)}
      <svg className="electoral-map" viewBox="0 0 720 420" role="img" aria-label={`Mapa por ${metricLabels[metric].toLowerCase()}`}>
        {response.features.map((feature) => (
          <path
            key={feature.id}
            d={pathForGeometry(feature.geometry, projection)}
            fill={fill(feature.properties[metric])}
            className={selectedCode === feature.properties.territory_code ? "selected" : ""}
            tabIndex="0"
            role="button"
            aria-label={`${feature.properties.territory_name}: ${feature.properties[metric] ?? "sem dado"}`}
            onClick={() => onSelect(feature.properties.territory_code)}
            onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) onSelect(feature.properties.territory_code); }}
          />
        ))}
      </svg>
      <footer className="electoral-provenance">Fonte: <a href={response.source} target="_blank" rel="noreferrer">IBGE</a><span>Malha {response.reference_year} · versão {response.geometry_version.slice(0, 8)}</span></footer>
    </section>
  );
}
