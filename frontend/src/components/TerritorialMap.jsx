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
    async function initializeMap() {
      try {
        const maplibregl = await import("maplibre-gl");
        if (!active || !containerRef.current) return;
        map = new maplibregl.Map({
          container: containerRef.current,
          style: geoapifyRasterStyle(apiKey),
          center: mapData.center,
          zoom: 11,
          minZoom: 3,
          maxZoom: 20,
          attributionControl: true,
        });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

        map.once("load", () => {
          if (!active) return;
          installOperationalLayers(map, mapData);
          fitOperationalBounds(map, mapData.bounds);
          setMapReady(true);
        });
        map.on("error", (event) => {
          if (active && event?.error) setMapFailed(true);
        });
        map.on("click", (event) => {
          const features = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYER_IDS });
          const territoryId = features.find((feature) => feature.properties?.territorioId)?.properties?.territorioId;
          if (territoryId) selectRef.current?.(territoryId);
        });
        map.on("mouseenter", INTERACTIVE_LAYER_IDS[0], () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", INTERACTIVE_LAYER_IDS[0], () => { map.getCanvas().style.cursor = ""; });
        map.on("mouseenter", INTERACTIVE_LAYER_IDS[1], () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", INTERACTIVE_LAYER_IDS[1], () => { map.getCanvas().style.cursor = ""; });
      } catch {
        if (active) setMapFailed(true);
      }
    }
    initializeMap();

    return () => {
      active = false;
      mapRef.current = null;
      setMapReady(false);
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
      <div
        ref={containerRef}
        className="territorial-map-canvas"
        aria-label="Mapa interativo de calor territorial"
        role="region"
      />
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
  const heatmap = featureCollection(cells.filter(hasCoordinates).map((item, index) => ({
    type: "Feature",
    id: `heat-${index}`,
    properties: {
      territorio: item.territorio || "Sem território",
      territorioId: item.territorioId || "",
      total: Number(item.total || 0),
      abertas: Number(item.abertas || 0),
    },
    geometry: pointGeometry(item),
  })));
  const requestPoints = featureCollection(points.filter(hasCoordinates).map((item, index) => ({
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
    ...geometryCoordinates(jurisdictionGeojson),
    ...cells.filter(hasCoordinates).map((item) => [Number(item.longitude), Number(item.latitude)]),
    ...points.filter(hasCoordinates).map((item) => [Number(item.longitude), Number(item.latitude)]),
  ];
  const configuredBounds = normalizeBounds(jurisdiction?.limites);

  return {
    jurisdiction: jurisdictionGeojson,
    heatmap,
    points: requestPoints,
    center,
    centerPoint,
    bounds: configuredBounds || boundsFromCoordinates(coordinatePairs),
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
    paint: { "fill-color": "#17a9b8", "fill-opacity": 0.08 },
  });
  map.addLayer({
    id: "gabflow-jurisdiction-line",
    type: "line",
    source: SOURCE_IDS.jurisdiction,
    paint: { "line-color": "#168e9b", "line-width": 2.5 },
  });

  map.addSource(SOURCE_IDS.heatmap, { type: "geojson", data: data.heatmap });
  map.addLayer({
    id: "gabflow-heatmap",
    type: "heatmap",
    source: SOURCE_IDS.heatmap,
    paint: {
      "heatmap-weight": ["interpolate", ["linear"], ["get", "total"], 0, 0, 20, 1],
      "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 5, 0.7, 15, 1.8],
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 18, 15, 42],
      "heatmap-opacity": 0.72,
      "heatmap-color": [
        "interpolate", ["linear"], ["heatmap-density"],
        0, "rgba(254, 215, 170, 0)",
        0.3, "#fed7aa",
        0.55, "#fb923c",
        0.8, "#f97316",
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

function setSourceData(map, sourceId, data) {
  map.getSource(sourceId)?.setData(data);
}

function fitOperationalBounds(map, bounds) {
  if (!bounds) return;
  map.fitBounds(bounds, { padding: 36, maxZoom: 15, duration: 0 });
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
