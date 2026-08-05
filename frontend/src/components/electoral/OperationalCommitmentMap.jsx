import { useMemo } from "react";

function geometryPoints(geometry) {
  const points = [];
  function visit(value) {
    if (Array.isArray(value) && typeof value[0] === "number") points.push(value);
    else if (Array.isArray(value)) value.forEach(visit);
  }
  visit(geometry?.coordinates || []);
  return points;
}

function boundaryGeometries(boundary) {
  if (!boundary) return [];
  if (boundary.type === "FeatureCollection") return boundary.features.map((item) => item.geometry);
  if (boundary.type === "Feature") return [boundary.geometry];
  return [boundary];
}

function pathForGeometry(geometry, project) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.flatMap((polygon) => polygon.map((ring) => ring.map((point, index) => {
    const [x, y] = project(point);
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ") + " Z")).join(" ");
}

export function OperationalCommitmentMap({ response, selectedId, onSelect }) {
  const geometries = boundaryGeometries(response?.boundary);
  const projection = useMemo(() => {
    const boundary = boundaryGeometries(response?.boundary).flatMap(geometryPoints);
    const markers = response?.features?.flatMap((item) => geometryPoints(item.geometry)) || [];
    const points = boundary.length ? boundary : markers;
    if (!points.length) return null;
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    const minX = Math.min(...xs); const maxX = Math.max(...xs);
    const minY = Math.min(...ys); const maxY = Math.max(...ys);
    const scale = Math.min(680 / Math.max(maxX - minX, 0.001), 360 / Math.max(maxY - minY, 0.001));
    const width = (maxX - minX) * scale; const height = (maxY - minY) * scale;
    return (point) => [360 - width / 2 + (point[0] - minX) * scale, 210 + height / 2 - (point[1] - minY) * scale];
  }, [response]);

  if (!response) return <p aria-live="polite">Carregando camada cartográfica...</p>;
  if (!projection) return <p className="electoral-empty">Não há geometria oficial ou pontos públicos para exibir.</p>;
  return (
    <div className="electoral-operational-map-wrap">
      {response.warnings?.map((warning) => <p className="electoral-warning" key={warning}>{warning}</p>)}
      <svg className="electoral-map electoral-operational-map" viewBox="0 0 720 420" role="img" aria-label="Mapa operacional de compromissos públicos">
        {geometries.map((geometry, index) => <path key={index} d={pathForGeometry(geometry, projection)} className="operational-boundary" />)}
        {response.features.map((feature) => {
          const [x, y] = projection(feature.geometry.coordinates);
          const selected = selectedId === feature.properties.commitment_id;
          return <circle key={feature.id} cx={x} cy={y} r={selected ? 10 : 7} className={selected ? "commitment-marker selected" : "commitment-marker"} tabIndex="0" role="button" aria-label={`${feature.properties.title}: ${feature.properties.progress}%`} onClick={() => onSelect(feature.properties.commitment_id)} onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) onSelect(feature.properties.commitment_id); }} />;
        })}
      </svg>
      <footer className="electoral-provenance"><span>Fonte: <a href={response.source.url} target="_blank" rel="noreferrer">{response.source.name}</a></span><span>{response.features.length} compromissos localizados · {response.unmapped_commitments} sem ponto público</span></footer>
    </div>
  );
}
