import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TerritorialMap } from "./TerritorialMap";

const mapMock = vi.hoisted(() => ({ instances: [], failOperationalLayer: false }));

vi.mock("maplibre-gl", () => ({
  Map: class {
    constructor(options) {
      this.options = options;
      this.layers = [];
      this.sources = new Map();
      this.fitBounds = vi.fn();
      this.resize = vi.fn();
      mapMock.instances.push(this);
    }

    addControl() {}

    getStyle() {
      return { layers: [{ id: "geoapify-basemap" }] };
    }

    once(event, callback) {
      if (event === "idle") callback();
    }

    on() {}

    addSource(id, source) {
      this.sources.set(id, { ...source, setData: vi.fn() });
    }

    addLayer(layer) {
      if (mapMock.failOperationalLayer) throw new Error("invalid operational layer");
      this.layers.push(layer);
    }

    getSource(id) {
      return this.sources.get(id);
    }

    getLayer(id) {
      return this.layers.find((layer) => layer.id === id);
    }

    setFilter() {}

    getCanvas() {
      return { style: {}, clientWidth: 800, clientHeight: 420 };
    }

    project([longitude, latitude]) {
      return { x: (longitude + 44) * 100, y: (-latitude - 21) * 100 };
    }

    remove() {}
  },
  NavigationControl: class {},
}));

const territorialData = {
  cells: [{
    territorio: "Centro",
    territorioId: "territory-1",
    latitude: -21.7619,
    longitude: -43.3496,
    total: 8,
    abertas: 3,
  }],
  points: [{
    id: "request-1",
    territorioId: "territory-1",
    latitude: -21.762,
    longitude: -43.35,
    atrasada: true,
  }],
  jurisdiction: {
    centro: { latitude: -21.7619, longitude: -43.3496 },
    limites: {
      minLatitude: -21.92,
      maxLatitude: -21.58,
      minLongitude: -43.58,
      maxLongitude: -43.17,
    },
    geojson: {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [[
            [-43.58, -21.92], [-43.17, -21.92], [-43.17, -21.58],
            [-43.58, -21.58], [-43.58, -21.92],
          ]],
        },
      }],
    },
  },
};

afterEach(() => {
  cleanup();
  mapMock.instances.length = 0;
  mapMock.failOperationalLayer = false;
  vi.unstubAllEnvs();
});

describe("TerritorialMap", () => {
  it("usa Geoapify e instala as camadas operacionais em homologação", async () => {
    vi.stubEnv("VITE_APP_ENV", "homologation");
    vi.stubEnv("VITE_TERRITORIAL_MAP_ENABLED", "true");
    vi.stubEnv("VITE_GEOAPIFY_MAP_API_KEY", "browser-key");

    render(
      <TerritorialMap
        {...territorialData}
        fallback={<div>Mapa de contingência</div>}
      />,
    );

    expect(await screen.findByLabelText("Mapa interativo de calor territorial")).toBeInTheDocument();
    await waitFor(() => expect(mapMock.instances).toHaveLength(1));
    const map = mapMock.instances[0];
    expect(map.options.style.sources.geoapify.tiles[0]).toContain("apiKey=browser-key");
    expect(map.options.bounds).toEqual([[-43.58, -21.92], [-43.17, -21.58]]);
    expect(map.options.fitBoundsOptions).toEqual({ padding: 18, maxZoom: 13, duration: 0 });
    expect(map.layers.map((layer) => layer.id)).toEqual(expect.arrayContaining([
      "gabflow-jurisdiction-line",
      "gabflow-heatmap",
      "gabflow-request-points",
    ]));
    expect(map.resize).toHaveBeenCalled();
    expect(map.fitBounds).toHaveBeenCalledWith(
      [[-43.58, -21.92], [-43.17, -21.58]],
      { padding: 18, maxZoom: 13, duration: 0 },
    );
    const heatmapLayer = map.layers.find((layer) => layer.id === "gabflow-heatmap");
    expect(heatmapLayer.paint["heatmap-weight"]).toEqual(["get", "peso"]);
    expect(map.sources.get("gabflow-heatmap").data.features[0].properties.peso).toBe(1);
    const overlay = await screen.findByTestId("territorial-map-operational-overlay");
    expect(overlay.querySelectorAll(".territorial-map-overlay-heat")).toHaveLength(1);
    expect(overlay.querySelectorAll(".territorial-map-overlay-boundary").length).toBeGreaterThan(0);
  });

  it("remove do calor pontos fora do limite oficial", async () => {
    vi.stubEnv("VITE_APP_ENV", "homologation");
    vi.stubEnv("VITE_TERRITORIAL_MAP_ENABLED", "true");
    vi.stubEnv("VITE_GEOAPIFY_MAP_API_KEY", "browser-key");

    render(<TerritorialMap
      {...territorialData}
      cells={[...territorialData.cells, {
        territorio: "Fora",
        territorioId: "outside",
        latitude: -20,
        longitude: -40,
        total: 30,
        abertas: 20,
      }]}
      fallback={<div>Mapa de contingÃªncia</div>}
    />);

    await waitFor(() => expect(mapMock.instances).toHaveLength(1));
    const features = mapMock.instances[0].sources.get("gabflow-heatmap").data.features;
    expect(features).toHaveLength(1);
    expect(features[0].properties.territorio).toBe("Centro");
  });

  it("mantém o mapa de contingência quando o ambiente é produção", () => {
    vi.stubEnv("VITE_APP_ENV", "production");
    vi.stubEnv("VITE_TERRITORIAL_MAP_ENABLED", "true");
    vi.stubEnv("VITE_GEOAPIFY_MAP_API_KEY", "browser-key");

    render(<TerritorialMap {...territorialData} fallback={<div>Mapa de contingência</div>} />);

    expect(screen.getByText("Mapa de contingência")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mapa interativo de calor territorial")).not.toBeInTheDocument();
  });

  it("usa contingência em vez de deixar somente o mapa-base quando uma camada falha", async () => {
    vi.stubEnv("VITE_APP_ENV", "homologation");
    vi.stubEnv("VITE_TERRITORIAL_MAP_ENABLED", "true");
    vi.stubEnv("VITE_GEOAPIFY_MAP_API_KEY", "browser-key");
    mapMock.failOperationalLayer = true;

    render(<TerritorialMap {...territorialData} fallback={<div>Mapa de contingência</div>} />);

    expect(await screen.findByText("Mapa de contingência")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mapa interativo de calor territorial")).not.toBeInTheDocument();
  });
});
