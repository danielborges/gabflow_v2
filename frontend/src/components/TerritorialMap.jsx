import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";

const SOURCE_IDS = {
  jurisdiction: "gabflow-jurisdiction",
  heatmap: "gabflow-heatmap",
  points: "gabflow-points",
  center: "gabflow-jurisdiction-center",
};

const INTERACTIVE_LAYER_IDS = ["gabflow-heatmap-circles", "gabflow-request-points"];

export function TerritorialMap({
  cells = [],
  points = [],
  jurisdiction = null,
  selectedTerritoryId = null,
  onSelectTerritory,
  onSelectFeature,
  expanded = false,
  fallback,
}) {
  const appEnvironment = (import.meta.env.VITE_APP_ENV || import.meta.env.MODE || "production").toLowerCase();
  const enabled = import.meta.env.VITE_TERRITORIAL_MAP_ENABLED === "true"
    && ["development", "homologation", "staging", "test"].includes(appEnvironment);
  const apiKey = (import.meta.env.VITE_GEOAPIFY_MAP_API_KEY || "").trim();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const selectRef = useRef(onSelectTerritory);
  const [mapReady, setMapReady] = useState(false);
  const [mapFailed, setMapFailed] = useState(false);
  const [mapDiagnostic, setMapDiagnostic] = useState("waiting");
  const [overlay, setOverlay] = useState(null);
  const mapData = useMemo(
    () => buildMapData(cells, points, jurisdiction),
    [cells, points, jurisdiction],
  );

  useEffect(() => {
    selectRef.current = onSelectTerritory;
  }, [onSelectTerritory]);

  useEffect(() => {
    if (!enabled || !apiKey || mapFailed || !containerRef.current || !mapData.hasCoordinates) return undefined;

    let active = true;
    let map = null;
    let stylePoll = null;
    async function initializeMap() {
      try {
        const maplibregl = await import("maplibre-gl");
        if (!active || !containerRef.current) return;
        map = new maplibregl.Map({
          container: containerRef.current,
          style: geoapifyRasterStyle(apiKey),
          center: mapData.center,
          zoom: 11,
          ...(mapData.bounds ? {
            bounds: mapData.bounds,
            fitBoundsOptions: { padding: 18, maxZoom: 13, duration: 0 },
          } : {}),
          minZoom: 3,
          maxZoom: 20,
          attributionControl: true,
        });
        mapRef.current = map;
        setMapDiagnostic("style-wait");
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

        let operationalLayersInstalled = false;
        const installWhenStyleIsReady = () => {
          if (!active || operationalLayersInstalled || !styleAcceptsOperationalLayers(map)) return;
          operationalLayersInstalled = true;
          try {
            setMapDiagnostic("installing");
            installOperationalLayers(map, mapData);
            installOperationalInteractions(map, selectRef);
            fitOperationalBounds(map, mapData.bounds);
            const installedLayerCount = map.getStyle().layers
              .filter((layer) => layer.id.startsWith("gabflow-")).length;
            setMapDiagnostic(`ready:${installedLayerCount}:${mapData.heatmap.features.length}`);
            const refreshOverlay = () => {
              if (active) setOverlay(projectOperationalOverlay(map, mapData));
            };
            map.on("move", refreshOverlay);
            map.on("resize", refreshOverlay);
            refreshOverlay();
            setMapReady(true);
            if (stylePoll) window.clearInterval(stylePoll);
            map.once("idle", () => {
              if (active) fitOperationalBounds(map, mapData.bounds);
            });
          } catch (error) {
            setMapDiagnostic(`layer-error:${error?.message || "unknown"}`);
            setMapFailed(true);
          }
        };
        map.on("styledata", installWhenStyleIsReady);
        map.once("load", installWhenStyleIsReady);
        stylePoll = window.setInterval(installWhenStyleIsReady, 100);
        installWhenStyleIsReady();
      } catch {
        if (active) setMapFailed(true);
      }
    }
    initializeMap();

    return () => {
      active = false;
      if (stylePoll) window.clearInterval(stylePoll);
      mapRef.current = null;
      setMapReady(false);
      setOverlay(null);
      map?.remove();
    };
  }, [apiKey, enabled, mapData, mapFailed]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    setSourceData(map, SOURCE_IDS.jurisdiction, mapData.jurisdiction);
    setSourceData(map, SOURCE_IDS.heatmap, mapData.heatmap);
    setSourceData(map, SOURCE_IDS.points, mapData.points);
    setSourceData(map, SOURCE_IDS.center, mapData.centerPoint);
    fitOperationalBounds(map, mapData.bounds);
  }, [mapData, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map?.getLayer("gabflow-selected-territory")) return;
    map.setFilter("gabflow-selected-territory", [
      "==",
      ["get", "territorioId"],
      selectedTerritoryId || "__none__",
    ]);
  }, [mapReady, selectedTerritoryId]);

  if (!enabled || !apiKey || mapFailed || !mapData.hasCoordinates) return fallback;

  return (
    <div className={`territorial-map territorial-map-interactive${expanded ? " expanded" : ""}`}>
      <div className="territorial-map-stage">
        <div
          ref={containerRef}
          className="territorial-map-canvas"
          data-map-state={mapDiagnostic}
          aria-label="Mapa interativo de calor territorial"
          role="region"
        />
        {mapReady && overlay && (
          <svg
            className="territorial-map-operational-overlay"
            data-testid="territorial-map-operational-overlay"
            viewBox={`0 0 ${overlay.width} ${overlay.height}`}
          >
            <defs>
              <radialGradient id="territorialOperationalHeat">
                <stop offset="0%" stopColor="#ef4444" stopOpacity="0.88" />
                <stop offset="42%" stopColor="#f97316" stopOpacity="0.68" />
                <stop offset="75%" stopColor="#fb923c" stopOpacity="0.32" />
                <stop offset="100%" stopColor="#fed7aa" stopOpacity="0" />
              </radialGradient>
            </defs>
            {!!overlay.boundaries.length && (
              <path
                className="territorial-map-outside-mask"
                d={`M0 0H${overlay.width}V${overlay.height}H0Z ${overlay.boundaries.join(" ")}`}
                fillRule="evenodd"
              />
            )}
            {overlay.heat.map((item) => (
              <circle
                key={item.id}
                className="territorial-map-overlay-heat"
                role="button"
                tabIndex="0"
                aria-label={`Abrir concentração em ${item.properties.territorio}`}
                cx={item.x}
                cy={item.y}
                r={24 + item.weight * 34}
                onClick={() => onSelectFeature?.({ type: "concentration", ...item.properties })}
                onKeyDown={(event) => {
                  if (["Enter", " "].includes(event.key)) onSelectFeature?.({ type: "concentration", ...item.properties });
                }}
              />
            ))}
            {overlay.boundaries.map((path, index) => (
              <path key={`boundary-${index}`} className="territorial-map-overlay-boundary" d={path} />
            ))}
            {overlay.points.map((item) => (
              <circle
                key={item.id}
                className="territorial-map-overlay-point"
                role="button"
                tabIndex="0"
                aria-label={`Abrir solicitação ${item.properties.protocolo}`}
                cx={item.x}
                cy={item.y}
                r="4.5"
                onClick={() => onSelectFeature?.({ type: "request", id: item.id, ...item.properties })}
                onKeyDown={(event) => {
                  if (["Enter", " "].includes(event.key)) onSelectFeature?.({ type: "request", id: item.id, ...item.properties });
                }}
              />
            ))}
          </svg>
        )}
      </div>
      <div className="territorial-map-legend" aria-label="Legenda do mapa">
        <span><i className="low" /> Menor concentração</span>
        <span><i className="high" /> Maior concentração</span>
        <span><i className="request-point" /> Solicitação</span>
      </div>
    </div>
  );
}

function buildMapData(cells = [], points = [], jurisdiction = null) {
  const jurisdictionGeojson = normalizeJurisdictionGeojson(jurisdiction?.geojson);
  const jurisdictionCoordinates = geometryCoordinates(jurisdictionGeojson);
  const validCells = cells.filter((item) => (
    hasCoordinates(item) && coordinateInsideJurisdiction(item, jurisdictionGeojson)
  ));
  const validPoints = points.filter((item) => (
    hasCoordinates(item) && coordinateInsideJurisdiction(item, jurisdictionGeojson)
  ));
  const maximumTotal = Math.max(...validCells.map((item) => Number(item.total || 0)), 1);
  const heatmap = featureCollection(validCells.map((item, index) => ({
    type: "Feature",
    id: `heat-${index}`,
    properties: {
      territorio: item.territorio || "Sem território",
      territorioId: item.territorioId || "",
      total: Number(item.total || 0),
      abertas: Number(item.abertas || 0),
      peso: Math.max(Number(item.total || 0) / maximumTotal, 0.25),
    },
    geometry: pointGeometry(item),
  })));
  const requestPoints = featureCollection(validPoints.map((item, index) => ({
    type: "Feature",
    id: item.id || `request-${index}`,
    properties: {
      protocolo: item.protocolo || "",
      titulo: item.titulo || "Solicitação",
      territorioId: item.territorioId || "",
      atrasada: Boolean(item.atrasada),
    },
    geometry: pointGeometry(item),
  })));
  const centerItem = hasCoordinates(jurisdiction?.centro)
    ? jurisdiction.centro
    : cells.find(hasCoordinates) || points.find(hasCoordinates) || null;
  const center = centerItem
    ? [Number(centerItem.longitude), Number(centerItem.latitude)]
    : [-43.3496, -21.7619];
  const centerPoint = featureCollection(centerItem ? [{
    type: "Feature",
    properties: {},
    geometry: pointGeometry(centerItem),
  }] : []);
  const coordinatePairs = [
    ...jurisdictionCoordinates,
    ...validCells.map((item) => [Number(item.longitude), Number(item.latitude)]),
    ...validPoints.map((item) => [Number(item.longitude), Number(item.latitude)]),
  ];
  const configuredBounds = normalizeBounds(jurisdiction?.limites);
  const jurisdictionBounds = boundsFromCoordinates(jurisdictionCoordinates);

  return {
    jurisdiction: jurisdictionGeojson,
    heatmap,
    points: requestPoints,
    center,
    centerPoint,
    bounds: jurisdictionBounds || configuredBounds || boundsFromCoordinates(coordinatePairs),
    hasCoordinates: coordinatePairs.length > 0 || Boolean(centerItem),
  };
}

function geoapifyRasterStyle(apiKey) {
  const encodedKey = encodeURIComponent(apiKey);
  return {
    version: 8,
    sources: {
      geoapify: {
        type: "raster",
        tiles: [`https://maps.geoapify.com/v1/tile/osm-bright/{z}/{x}/{y}.png?apiKey=${encodedKey}`],
        tileSize: 256,
        maxzoom: 20,
        attribution: "Powered by Geoapify | © OpenMapTiles © OpenStreetMap contributors",
      },
    },
    layers: [{ id: "geoapify-basemap", type: "raster", source: "geoapify" }],
  };
}

function installOperationalLayers(map, data) {
  map.addSource(SOURCE_IDS.jurisdiction, { type: "geojson", data: data.jurisdiction });
  map.addLayer({
    id: "gabflow-jurisdiction-fill",
    type: "fill",
    source: SOURCE_IDS.jurisdiction,
    paint: { "fill-color": "#17a9b8", "fill-opacity": 0.04 },
  });
  map.addLayer({
    id: "gabflow-jurisdiction-line",
    type: "line",
    source: SOURCE_IDS.jurisdiction,
    paint: {
      "line-color": "#087f8c",
      "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 13, 4],
    },
  });

  map.addSource(SOURCE_IDS.heatmap, { type: "geojson", data: data.heatmap });
  map.addLayer({
    id: "gabflow-heatmap",
    type: "heatmap",
    source: SOURCE_IDS.heatmap,
    paint: {
      "heatmap-weight": ["get", "peso"],
      "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 5, 0.9, 15, 2.2],
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 24, 15, 58],
      "heatmap-opacity": 0.88,
      "heatmap-color": [
        "interpolate", ["linear"], ["heatmap-density"],
        0, "rgba(254, 215, 170, 0)",
        0.18, "#fed7aa",
        0.42, "#fb923c",
        0.72, "#f97316",
        1, "#ef4444",
      ],
    },
  });
  map.addLayer({
    id: INTERACTIVE_LAYER_IDS[0],
    type: "circle",
    source: SOURCE_IDS.heatmap,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "total"], 1, 5, 20, 12],
      "circle-color": "#ef4444",
      "circle-opacity": 0.78,
      "circle-stroke-color": "#fff7ed",
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "gabflow-selected-territory",
    type: "circle",
    source: SOURCE_IDS.heatmap,
    filter: ["==", ["get", "territorioId"], "__none__"],
    paint: {
      "circle-radius": 15,
      "circle-color": "rgba(0, 0, 0, 0)",
      "circle-stroke-color": "#08285c",
      "circle-stroke-width": 4,
    },
  });

  map.addSource(SOURCE_IDS.points, { type: "geojson", data: data.points });
  map.addLayer({
    id: INTERACTIVE_LAYER_IDS[1],
    type: "circle",
    source: SOURCE_IDS.points,
    paint: {
      "circle-radius": 4,
      "circle-color": ["case", ["get", "atrasada"], "#b91c1c", "#08285c"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
    },
  });

  map.addSource(SOURCE_IDS.center, { type: "geojson", data: data.centerPoint });
  map.addLayer({
    id: "gabflow-jurisdiction-center",
    type: "circle",
    source: SOURCE_IDS.center,
    paint: {
      "circle-radius": 5,
      "circle-color": "#17a9b8",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

function styleAcceptsOperationalLayers(map) {
  try {
    return Boolean(map.getStyle()?.layers?.length);
  } catch {
    return false;
  }
}

function installOperationalInteractions(map, selectRef) {
  map.on("click", (event) => {
    const features = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYER_IDS });
    const territoryId = features.find((feature) => feature.properties?.territorioId)?.properties?.territorioId;
    if (territoryId) selectRef.current?.(territoryId);
  });
  map.on("mouseenter", INTERACTIVE_LAYER_IDS[0], () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", INTERACTIVE_LAYER_IDS[0], () => { map.getCanvas().style.cursor = ""; });
  map.on("mouseenter", INTERACTIVE_LAYER_IDS[1], () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", INTERACTIVE_LAYER_IDS[1], () => { map.getCanvas().style.cursor = ""; });
}

function projectOperationalOverlay(map, data) {
  const canvas = map.getCanvas();
  const width = canvas.clientWidth || canvas.width || 1;
  const height = canvas.clientHeight || canvas.height || 1;
  const projectFeature = (feature) => {
    const projected = map.project(feature.geometry.coordinates);
    return {
      id: feature.id,
      x: projected.x,
      y: projected.y,
      weight: Number(feature.properties?.peso || 0.25),
      properties: feature.properties || {},
    };
  };
  return {
    width,
    height,
    boundaries: projectedJurisdictionPaths(map, data.jurisdiction),
    heat: data.heatmap.features.map(projectFeature),
    points: data.points.features.map(projectFeature),
  };
}

function projectedJurisdictionPaths(map, geojson) {
  const paths = [];
  const addPolygon = (polygon) => polygon.forEach((ring) => {
    const commands = ring.map((coordinates, index) => {
      const point = map.project(coordinates);
      return `${index ? "L" : "M"}${point.x} ${point.y}`;
    });
    if (commands.length) paths.push(`${commands.join(" ")}Z`);
  });
  geojson.features.forEach((feature) => {
    const geometry = feature?.geometry;
    if (geometry?.type === "Polygon") addPolygon(geometry.coordinates);
    if (geometry?.type === "MultiPolygon") geometry.coordinates.forEach(addPolygon);
  });
  return paths;
}

function setSourceData(map, sourceId, data) {
  map.getSource(sourceId)?.setData(data);
}

function fitOperationalBounds(map, bounds) {
  if (!bounds) return;
  map.resize();
  map.fitBounds(bounds, { padding: 18, maxZoom: 13, duration: 0 });
}

function pointGeometry(item) {
  return { type: "Point", coordinates: [Number(item.longitude), Number(item.latitude)] };
}

function hasCoordinates(item) {
  return Number.isFinite(Number(item?.latitude)) && Number.isFinite(Number(item?.longitude));
}

function featureCollection(features = []) {
  return { type: "FeatureCollection", features };
}

function normalizeJurisdictionGeojson(value) {
  if (!value) return featureCollection();
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      return featureCollection();
    }
  }
  if (parsed.type === "FeatureCollection") return parsed;
  if (parsed.type === "Feature") return featureCollection([parsed]);
  if (parsed.type && parsed.coordinates) {
    return featureCollection([{ type: "Feature", properties: {}, geometry: parsed }]);
  }
  return featureCollection();
}

function coordinateInsideJurisdiction(item, geojson) {
  if (!geojson.features.length) return true;
  const point = [Number(item.longitude), Number(item.latitude)];
  return geojson.features.some((feature) => geometryContainsPoint(feature?.geometry, point));
}

function geometryContainsPoint(geometry, point) {
  if (geometry?.type === "Polygon") return polygonContainsPoint(geometry.coordinates, point);
  if (geometry?.type === "MultiPolygon") {
    return geometry.coordinates.some((polygon) => polygonContainsPoint(polygon, point));
  }
  return false;
}

function polygonContainsPoint(rings, point) {
  if (!rings?.length || !ringContainsPoint(rings[0], point)) return false;
  return !rings.slice(1).some((ring) => ringContainsPoint(ring, point));
}

function ringContainsPoint(ring, [longitude, latitude]) {
  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const [currentLongitude, currentLatitude] = ring[index];
    const [previousLongitude, previousLatitude] = ring[previous];
    const intersects = ((currentLatitude > latitude) !== (previousLatitude > latitude))
      && longitude < ((previousLongitude - currentLongitude) * (latitude - currentLatitude))
        / (previousLatitude - currentLatitude) + currentLongitude;
    if (intersects) inside = !inside;
  }
  return inside;
}

function geometryCoordinates(geojson) {
  const pairs = [];
  function visit(value) {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))) {
      pairs.push([Number(value[0]), Number(value[1])]);
      return;
    }
    value.forEach(visit);
  }
  geojson.features.forEach((feature) => visit(feature?.geometry?.coordinates));
  return pairs;
}

function normalizeBounds(bounds) {
  const west = Number(bounds?.minLongitude);
  const south = Number(bounds?.minLatitude);
  const east = Number(bounds?.maxLongitude);
  const north = Number(bounds?.maxLatitude);
  if (![west, south, east, north].every(Number.isFinite) || west >= east || south >= north) return null;
  return [[west, south], [east, north]];
}

function boundsFromCoordinates(coordinates) {
  if (!coordinates.length) return null;
  const longitudes = coordinates.map(([longitude]) => longitude);
  const latitudes = coordinates.map(([, latitude]) => latitude);
  let west = Math.min(...longitudes);
  let east = Math.max(...longitudes);
  let south = Math.min(...latitudes);
  let north = Math.max(...latitudes);
  if (west === east) { west -= 0.01; east += 0.01; }
  if (south === north) { south -= 0.01; north += 0.01; }
  return [[west, south], [east, north]];
}
