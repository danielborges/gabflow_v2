import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("GooglePlaceAutocompleteInput", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    delete window.google;
  });

  it("busca sugestões e entrega endereço estruturado para resolver bairro e território", async () => {
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "browser-key");
    const place = {
      id: "google-place-1",
      formattedAddress: "Rua Halfeld, 500 - Centro, Juiz de Fora - MG, 36010-001",
      displayName: "Rua Halfeld, 500",
      location: { lat: () => -21.7601, lng: () => -43.3498 },
      addressComponents: [
        { types: ["route"], longText: "Rua Halfeld", shortText: "R. Halfeld" },
        { types: ["street_number"], longText: "500", shortText: "500" },
        { types: ["sublocality_level_1"], longText: "Centro", shortText: "Centro" },
        { types: ["administrative_area_level_2"], longText: "Juiz de Fora", shortText: "Juiz de Fora" },
        { types: ["administrative_area_level_1"], longText: "Minas Gerais", shortText: "MG" },
        { types: ["postal_code"], longText: "36010-001", shortText: "36010-001" },
      ],
      fetchFields: vi.fn().mockResolvedValue(undefined),
    };
    const prediction = {
      placeId: "google-place-1",
      text: { toString: () => "Rua Halfeld, 500 - Centro, Juiz de Fora - MG" },
      toPlace: () => place,
    };
    const fetchAutocompleteSuggestions = vi.fn().mockResolvedValue({
      suggestions: [{ placePrediction: prediction }],
    });
    class AutocompleteSessionToken {}
    window.google = {
      maps: {
        importLibrary: vi.fn().mockResolvedValue({
          AutocompleteSessionToken,
          AutocompleteSuggestion: { fetchAutocompleteSuggestions },
        }),
      },
    };
    const { GooglePlaceAutocompleteInput } = await import("./GooglePlaceAutocompleteInput");
    const changed = vi.fn();

    function Harness() {
      const [value, setValue] = useState("");
      return <GooglePlaceAutocompleteInput
        value={value}
        onChange={(nextValue, details) => {
          setValue(nextValue);
          changed(nextValue, details);
        }}
        territoryBounds={{ minLatitude: -22, maxLatitude: -21, minLongitude: -44, maxLongitude: -43 }}
        inputProps={{ "aria-label": "Endereço" }}
      />;
    }

    render(<Harness />);
    expect(await screen.findByText("Sugestões do Google Maps restritas ao território")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Endereço" }), { target: { value: "Halfeld" } });
    fireEvent.click(await screen.findByRole("option", { name: /Rua Halfeld, 500/ }));

    await waitFor(() => expect(changed).toHaveBeenLastCalledWith(
      place.formattedAddress,
      expect.objectContaining({
        bairro: "Centro",
        cidade: "Juiz de Fora",
        uf: "MG",
        latitude: -21.7601,
        longitude: -43.3498,
        placeId: "google-place-1",
      }),
    ));
    expect(fetchAutocompleteSuggestions).toHaveBeenCalledWith(expect.objectContaining({
      input: "Halfeld",
      region: "br",
      locationRestriction: { west: -44, north: -21, east: -43, south: -22 },
    }));
  });
});
