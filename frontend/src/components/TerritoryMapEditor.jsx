import { Check, LocateFixed, MousePointer2, Pentagon, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const MAP_WIDTH = 900;
const MAP_HEIGHT = 500;
const FALLBACK_BOUNDS = [-74, -34, -34, 6];
const COLORS = ["#1688ef", "#14a38b", "#8b5cf6", "#f59e0b", "#e85d75", "#0f7282"];

export function TerritoryMapEditor({
  territories,
  jurisdiction,
  selectedId,
  draftGeometry,
  draftName,
  draftAliases,
  onSelect,
  onGeometryChange,
}) {
  const svgRef = useRef(null);
  const [mode, setMode] = useState("select");
  const [drawing, setDrawing] = useState([]);
  const [activePolygon, setActivePolygon] = useState(0);
  const [selectedVertex, setSelectedVertex] = useState(null);
  const [draggingVertex, setDraggingVertex] = useState(null);
  const geometry = useMemo(() => normalizeGeometry(draftGeometry), [draftGeometry]);
  const jurisdictionGeometries = useMemo(
    () => extractGeometries(jurisdiction?.geojson),
    [jurisdiction?.geojson],
  );
  const mapTerritories = useMemo(() => territories.map((item) => ({
    ...item,
    geometria: item.id === selectedId ? geometry : normalizeGeometry(item.geometria),
  })), [geometry, selectedId, territories]);
  const bounds = useMemo(
    () => mapBounds(jurisdictionGeometries, mapTerritories, geometry, drawing),
    [drawing, geometry, jurisdictionGeometries, mapTerritories],
  );
  const polygons = geometryPolygons(geometry);
  const activeRing = polygons[activePolygon]?.[0] || [];
  const openActiveRing = activeRing.slice(0, -1);
  const aliasList = parseAliases(draftAliases);

  useEffect(() => {
    setActivePolygon(0);
    setSelectedVertex(null);
    setDrawing([]);
    setMode("select");
  }, [selectedId]);

  function mapPoint(event) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect?.height) return null;
    const x = ((event.clientX - rect.left) / rect.width) * MAP_WIDTH;
    const y = ((event.clientY - rect.top) / rect.height) * MAP_HEIGHT;
    return unprojectPoint([x, y], bounds);
  }

  function handleMapClick(event) {
    if (mode !== "draw" || draggingVertex !== null) return;
    const point = mapPoint(event);
    if (point) setDrawing((current) => [...current, point]);
  }

  function finishDrawing() {
    if (drawing.length < 3) return;
    const ring = [...drawing, drawing[0]];
    const nextPolygons = [...polygons, [ring]];
    onGeometryChange(geometryFromPolygons(nextPolygons));
    setActivePolygon(nextPolygons.length - 1);
    setDrawing([]);
    setMode("edit");
  }

  function updateVertex(index, point) {
    const nextPolygons = clonePolygons(polygons);
    const ring = nextPolygons[activePolygon]?.[0];
    if (!ring || index >= ring.length - 1) return;
    ring[index] = point;
    if (index === 0) ring[ring.length - 1] = point;
    onGeometryChange(geometryFromPolygons(nextPolygons));
  }

  function removeVertex() {
    if (selectedVertex === null || openActiveRing.length <= 3) return;
    const nextPolygons = clonePolygons(polygons);
    const points = nextPolygons[activePolygon][0].slice(0, -1);
    points.splice(selectedVertex, 1);
    nextPolygons[activePolygon][0] = [...points, points[0]];
    onGeometryChange(geometryFromPolygons(nextPolygons));
    setSelectedVertex(null);
  }

  function removePolygon() {
    if (!polygons.length) return;
    const nextPolygons = clonePolygons(polygons);
    nextPolygons.splice(activePolygon, 1);
    onGeometryChange(geometryFromPolygons(nextPolygons));
    setActivePolygon(Math.max(0, activePolygon - 1));
    setSelectedVertex(null);
  }

  function moveVertexWithKeyboard(event, index) {
    if (!event.key.startsWith("Arrow")) return;
    event.preventDefault();
    const [minX, minY, maxX, maxY] = bounds;
    const stepX = (maxX - minX) / 300;
    const stepY = (maxY - minY) / 300;
    const [longitude, latitude] = openActiveRing[index];
    updateVertex(index, [
      longitude + (event.key === "ArrowRight" ? stepX : event.key === "ArrowLeft" ? -stepX : 0),
      latitude + (event.key === "ArrowUp" ? stepY : event.key === "ArrowDown" ? -stepY : 0),
    ]);
  }

  const selectedCoordinate = selectedVertex === null ? null : openActiveRing[selectedVertex];
  const centerLabel = jurisdiction?.nome
    || [jurisdiction?.municipio, jurisdiction?.uf].filter(Boolean).join(" / ")
    || "Área territorial";

  return (
    <section className="territory-map-editor" aria-label="Editor cartográfico territorial">
      <header className="territory-map-editor-header">
        <div>
          <span className="eyebrow">Gestão cartográfica</span>
          <strong>Mapa de territórios</strong>
          <small>{centerLabel} · clique em um polígono para editar</small>
        </div>
        <div className="territory-map-tools" role="toolbar" aria-label="Ferramentas do mapa">
          <button type="button" className={mode === "select" ? "active" : ""} onClick={() => setMode("select")}>
            <MousePointer2 size={15} /> Explorar
          </button>
          <button type="button" className={mode === "edit" ? "active" : ""} disabled={!geometry} onClick={() => setMode("edit")}>
            <LocateFixed size={15} /> Editar vértices
          </button>
          <button type="button" className={mode === "draw" ? "active" : ""} onClick={() => { setMode("draw"); setDrawing([]); }}>
            <Pentagon size={15} /> Desenhar polígono
          </button>
        </div>
      </header>

      <div className="territory-map-layout">
        <div className={`territory-canvas mode-${mode}`}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
            role="application"
            aria-label="Mapa para visualizar e editar polígonos territoriais"
            onClick={handleMapClick}
            onPointerMove={(event) => {
              if (draggingVertex === null) return;
              const point = mapPoint(event);
              if (point) updateVertex(draggingVertex, point);
            }}
            onPointerUp={() => setDraggingVertex(null)}
            onPointerLeave={() => setDraggingVertex(null)}
          >
            <defs>
              <pattern id="territory-grid" width="50" height="50" patternUnits="userSpaceOnUse">
                <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#d9e7ef" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width={MAP_WIDTH} height={MAP_HEIGHT} className="territory-map-background" />
            <rect width={MAP_WIDTH} height={MAP_HEIGHT} fill="url(#territory-grid)" />
            {jurisdictionGeometries.map((item, index) => (
              <GeometryShape key={`jurisdiction-${index}`} geometry={item} bounds={bounds} className="territory-jurisdiction-shape" />
            ))}
            {mapTerritories.map((item, index) => item.geometria && (
              <g
                key={item.id}
                className={`territory-map-feature ${item.id === selectedId ? "selected" : ""} ${item.ativa ? "" : "inactive"}`}
                onClick={(event) => { if (mode !== "draw") { event.stopPropagation(); onSelect(item); } }}
                role="button"
                tabIndex="0"
                aria-label={`${item.nome}${item.aliases?.length ? `, aliases ${item.aliases.join(", ")}` : ""}`}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(item); }}
              >
                <GeometryShape geometry={item.geometria} bounds={bounds} style={{ "--territory-color": COLORS[index % COLORS.length] }} />
                <GeometryLabel geometry={item.geometria} bounds={bounds} name={item.nome} />
              </g>
            ))}
            {!selectedId && geometry && (
              <g className="territory-map-feature selected draft">
                <GeometryShape geometry={geometry} bounds={bounds} />
                <GeometryLabel geometry={geometry} bounds={bounds} name={draftName || "Novo território"} />
              </g>
            )}
            {mode === "edit" && openActiveRing.map((point, index) => {
              const [x, y] = projectPoint(point, bounds);
              return (
                <circle
                  key={`${index}-${point.join("-")}`}
                  cx={x}
                  cy={y}
                  r={selectedVertex === index ? 9 : 7}
                  className={`territory-vertex ${selectedVertex === index ? "selected" : ""}`}
                  role="button"
                  tabIndex="0"
                  aria-label={`Vértice ${index + 1}`}
                  onClick={(event) => { event.stopPropagation(); setSelectedVertex(index); }}
                  onPointerDown={(event) => { event.stopPropagation(); setSelectedVertex(index); setDraggingVertex(index); }}
                  onKeyDown={(event) => moveVertexWithKeyboard(event, index)}
                />
              );
            })}
            {drawing.length > 0 && (
              <g className="territory-drawing">
                <polyline points={drawing.map((point) => projectPoint(point, bounds).join(",")).join(" ")} />
                {drawing.map((point, index) => {
                  const [x, y] = projectPoint(point, bounds);
                  return <circle key={`${point.join("-")}-${index}`} cx={x} cy={y} r="6" />;
                })}
              </g>
            )}
          </svg>
          <div className="territory-map-status" aria-live="polite">
            {mode === "draw" && <span>Clique no mapa para marcar os vértices · {drawing.length} ponto(s)</span>}
            {mode === "edit" && <span>Arraste os vértices ou use as setas do teclado</span>}
            {mode === "select" && <span>{mapTerritories.filter((item) => item.geometria).length} polígono(s) visível(is)</span>}
            <span>Lng/Lat · GeoJSON</span>
          </div>
        </div>

        <aside className="territory-map-inspector">
          <div className="territory-inspector-title">
            <span className="territory-color-dot" />
            <div><strong>{draftName || "Novo território"}</strong><small>{geometry ? geometry.type : "Sem polígono"}</small></div>
          </div>
          <div className="territory-map-metrics">
            <span><strong>{polygons.length}</strong> parte(s)</span>
            <span><strong>{polygons.reduce((total, polygon) => total + Math.max(0, (polygon[0]?.length || 1) - 1), 0)}</strong> vértices</span>
          </div>
          <div className="territory-alias-preview">
            <strong>Aliases de resolução</strong>
            {aliasList.length ? <div>{aliasList.map((alias) => <span key={alias}>{alias}</span>)}</div> : <small>Nenhum alias informado.</small>}
          </div>
          {polygons.length > 1 && (
            <label>Parte do território
              <select value={activePolygon} onChange={(event) => { setActivePolygon(Number(event.target.value)); setSelectedVertex(null); }}>
                {polygons.map((_, index) => <option key={index} value={index}>Polígono {index + 1}</option>)}
              </select>
            </label>
          )}
          {selectedCoordinate && (
            <div className="territory-coordinate-editor">
              <strong>Vértice {selectedVertex + 1}</strong>
              <label>Longitude<input type="number" step="0.000001" value={selectedCoordinate[0]} onChange={(event) => updateVertex(selectedVertex, [Number(event.target.value), selectedCoordinate[1]])} /></label>
              <label>Latitude<input type="number" step="0.000001" value={selectedCoordinate[1]} onChange={(event) => updateVertex(selectedVertex, [selectedCoordinate[0], Number(event.target.value)])} /></label>
              <button type="button" className="danger-soft" disabled={openActiveRing.length <= 3} onClick={removeVertex}><Trash2 size={14} /> Remover vértice</button>
            </div>
          )}
          {mode === "draw" && (
            <div className="territory-drawing-actions">
              <button type="button" className="primary-button compact" disabled={drawing.length < 3} onClick={finishDrawing}><Check size={16} /> Concluir desenho</button>
              <button type="button" className="secondary-button compact" disabled={!drawing.length} onClick={() => setDrawing((current) => current.slice(0, -1))}>Desfazer ponto</button>
            </div>
          )}
          {geometry && mode !== "draw" && <button type="button" className="danger-soft territory-remove-polygon" onClick={removePolygon}><Trash2 size={14} /> Remover parte selecionada</button>}
          <small className="territory-map-help">As alterações do mapa são aplicadas ao formulário. Use “Salvar território” para persistir e auditar.</small>
        </aside>
      </div>
    </section>
  );
}

function GeometryShape({ geometry, bounds, className = "", style }) {
  return geometryPolygons(geometry).map((polygon, index) => (
    <path key={index} d={polygonPath(polygon, bounds)} className={className} style={style} fillRule="evenodd" />
  ));
}

function GeometryLabel({ geometry, bounds, name }) {
  const ring = geometryPolygons(geometry)[0]?.[0];
  if (!ring?.length) return null;
  const center = ring.slice(0, -1).reduce((result, point) => [result[0] + point[0], result[1] + point[1]], [0, 0]);
  const count = Math.max(1, ring.length - 1);
  const [x, y] = projectPoint([center[0] / count, center[1] / count], bounds);
  return <text x={x} y={y} className="territory-feature-label" textAnchor="middle">{name}</text>;
}

function polygonPath(polygon, bounds) {
  return polygon.map((ring) => ring.map((point, index) => {
    const [x, y] = projectPoint(point, bounds);
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ") + " Z").join(" ");
}

function geometryPolygons(geometry) {
  if (!geometry) return [];
  return geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
}

function geometryFromPolygons(polygons) {
  if (!polygons.length) return null;
  return polygons.length === 1
    ? { type: "Polygon", coordinates: polygons[0] }
    : { type: "MultiPolygon", coordinates: polygons };
}

function clonePolygons(polygons) {
  return polygons.map((polygon) => polygon.map((ring) => ring.map((point) => [...point])));
}

function extractGeometries(value) {
  if (!value) return [];
  if (value.type === "FeatureCollection") return value.features.flatMap((feature) => extractGeometries(feature));
  if (value.type === "Feature") return extractGeometries(value.geometry);
  const geometry = normalizeGeometry(value);
  return geometry ? [geometry] : [];
}

function normalizeGeometry(value) {
  if (!value) return null;
  const geometry = value.type === "Feature" ? value.geometry : value;
  if (!geometry || !["Polygon", "MultiPolygon"].includes(geometry.type) || !Array.isArray(geometry.coordinates)) return null;
  return geometry;
}

function allCoordinates(geometry) {
  return geometryPolygons(geometry).flat(2).filter((point) => Array.isArray(point) && point.length >= 2 && point.every(Number.isFinite));
}

function mapBounds(jurisdictionGeometries, territories, draftGeometry, drawing) {
  const jurisdictionPoints = jurisdictionGeometries.flatMap(allCoordinates);
  const territoryPoints = territories.flatMap((item) => allCoordinates(item.geometria));
  const points = jurisdictionPoints.length ? jurisdictionPoints : [...territoryPoints, ...allCoordinates(draftGeometry), ...drawing];
  if (!points.length) return FALLBACK_BOUNDS;
  const longitudes = points.map((point) => point[0]);
  const latitudes = points.map((point) => point[1]);
  let minX = Math.min(...longitudes);
  let maxX = Math.max(...longitudes);
  let minY = Math.min(...latitudes);
  let maxY = Math.max(...latitudes);
  const padX = Math.max((maxX - minX) * 0.08, 0.005);
  const padY = Math.max((maxY - minY) * 0.08, 0.005);
  minX -= padX;
  maxX += padX;
  minY -= padY;
  maxY += padY;
  return [minX, minY, maxX, maxY];
}

function projectPoint([longitude, latitude], [minX, minY, maxX, maxY]) {
  return [
    ((longitude - minX) / (maxX - minX || 1)) * MAP_WIDTH,
    MAP_HEIGHT - ((latitude - minY) / (maxY - minY || 1)) * MAP_HEIGHT,
  ];
}

function unprojectPoint([x, y], [minX, minY, maxX, maxY]) {
  return [
    roundCoordinate(minX + (x / MAP_WIDTH) * (maxX - minX)),
    roundCoordinate(minY + ((MAP_HEIGHT - y) / MAP_HEIGHT) * (maxY - minY)),
  ];
}

function roundCoordinate(value) {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function parseAliases(value) {
  if (Array.isArray(value)) return value;
  return String(value || "").split(/[\n,;]/).map((item) => item.trim()).filter(Boolean);
}
