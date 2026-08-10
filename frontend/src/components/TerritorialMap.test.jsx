import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TerritorialMap } from "./TerritorialMap";

const mapMock = vi.hoisted(() => ({ instances: [] }));

vi.mock("maplibre-gl", () => ({
  Map: class {
    constructor(options) {
      this.options = options;
      this.layers = [];
      this.sources = new Map();
      mapMock.instances.push(this);
    }

    addControl() {}

    once(event, callback) {
      if (event === "load") callback();
    }

    on() {}

    addSource(id, source) {
      this.sources.set(id, { ...source, setData: vi.fn() });
    }

    addLayer(layer) {
      this.layers.push(layer);
    }

    getSource(id) {
      return this.sources.get(id);
    }

    getLayer(id) {
      return this.layers.find((layer) => layer.id === id);
    }

    setFilter() {}

    fitBounds() {}

    getCanvas() {
      return { style: {} };
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
  },
};

afterEach(() => {
  cleanup();
  mapMock.instances.length = 0;
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
    expect(map.layers.map((layer) => layer.id)).toEqual(expect.arrayContaining([
      "gabflow-jurisdiction-line",
      "gabflow-heatmap",
      "gabflow-request-points",
    ]));
  });

  it("mantém o mapa de contingência quando o ambiente é produção", () => {
    vi.stubEnv("VITE_APP_ENV", "production");
    vi.stubEnv("VITE_TERRITORIAL_MAP_ENABLED", "true");
    vi.stubEnv("VITE_GEOAPIFY_MAP_API_KEY", "browser-key");

    render(<TerritorialMap {...territorialData} fallback={<div>Mapa de contingência</div>} />);

    expect(screen.getByText("Mapa de contingência")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mapa interativo de calor territorial")).not.toBeInTheDocument();
  });
});
