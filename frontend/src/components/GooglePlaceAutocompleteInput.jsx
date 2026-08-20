import { useEffect, useId, useRef, useState } from "react";

const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
let googleMapsPromise;
let googleMapsCallbackId = 0;

export function GooglePlaceAutocompleteInput({ value, onChange, placeholder, territoryBounds, inputProps = {}, hideStatus = false }) {
  const listboxId = useId();
  const onChangeRef = useRef(onChange);
  const requestIdRef = useRef(0);
  const sessionTokenRef = useRef(null);
  const placesLibraryRef = useRef(null);
  const [status, setStatus] = useState(googleMapsApiKey ? "loading" : "disabled");
  const [editing, setEditing] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  useEffect(() => {
    if (!googleMapsApiKey) return undefined;
    let active = true;
    loadGoogleMapsPlaces(googleMapsApiKey)
      .then(async () => {
        const places = await window.google.maps.importLibrary("places");
        if (!active) return;
        placesLibraryRef.current = places;
        sessionTokenRef.current = new places.AutocompleteSessionToken();
        setStatus("ready");
      })
      .catch(() => { if (active) setStatus("error"); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const query = String(value || "").trim();
    if (!editing || status !== "ready" || query.length < 3) {
      setSuggestions([]);
      setLoadingSuggestions(false);
      return undefined;
    }
    const requestId = ++requestIdRef.current;
    setLoadingSuggestions(true);
    const timer = setTimeout(async () => {
      try {
        const places = placesLibraryRef.current;
        if (!sessionTokenRef.current) sessionTokenRef.current = new places.AutocompleteSessionToken();
        const restriction = googleLocationRestriction(territoryBounds);
        const result = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
          input: query,
          language: "pt-BR",
          region: "br",
          sessionToken: sessionTokenRef.current,
          ...(restriction ? { locationRestriction: restriction } : {}),
        });
        if (requestId !== requestIdRef.current) return;
        setSuggestions((result.suggestions || []).filter((item) => item.placePrediction));
        setActiveIndex(-1);
      } catch {
        if (requestId === requestIdRef.current) {
          setSuggestions([]);
          setStatus("error");
        }
      } finally {
        if (requestId === requestIdRef.current) setLoadingSuggestions(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [editing, status, territoryBounds, value]);

  async function selectSuggestion(suggestion) {
    const prediction = suggestion.placePrediction;
    const place = prediction.toPlace();
    setLoadingSuggestions(true);
    try {
      await place.fetchFields({ fields: ["addressComponents", "displayName", "formattedAddress", "id", "location"] });
      const nextValue = place.formattedAddress || place.displayName || prediction.text.toString();
      onChangeRef.current(nextValue, placeDetails(place, nextValue));
      setEditing(false);
      setSuggestions([]);
      setActiveIndex(-1);
      sessionTokenRef.current = new placesLibraryRef.current.AutocompleteSessionToken();
    } catch {
      setStatus("error");
    } finally {
      setLoadingSuggestions(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "ArrowDown" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, suggestions.length - 1));
    } else if (event.key === "ArrowUp" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      void selectSuggestion(suggestions[activeIndex]);
    } else if (event.key === "Escape") {
      setEditing(false);
      setSuggestions([]);
      setActiveIndex(-1);
    }
    inputProps.onKeyDown?.(event);
  }

  const optionsOpen = editing && (loadingSuggestions || suggestions.length > 0);
  return <span className="maps-autocomplete-field" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setEditing(false);
      setSuggestions([]);
      setActiveIndex(-1);
    }
  }}>
    <input
      {...inputProps}
      role="combobox"
      aria-autocomplete="list"
      aria-controls={listboxId}
      aria-expanded={optionsOpen}
      aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
      value={value}
      onChange={(event) => {
        setEditing(true);
        onChangeRef.current(event.target.value);
        inputProps.onChange?.(event);
      }}
      onFocus={(event) => { setEditing(true); inputProps.onFocus?.(event); }}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
    />
    {optionsOpen && <span id={listboxId} className="maps-autocomplete-options" role="listbox" aria-busy={loadingSuggestions}>
      {loadingSuggestions ? <span className="maps-autocomplete-message">Buscando endereços...</span> : suggestions.map((suggestion, index) => <button
        id={`${listboxId}-${index}`}
        key={suggestion.placePrediction.placeId || suggestion.placePrediction.text.toString()}
        type="button"
        role="option"
        aria-selected={index === activeIndex}
        className={index === activeIndex ? "is-active" : ""}
        onMouseDown={(event) => event.preventDefault()}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => void selectSuggestion(suggestion)}
      >{suggestion.placePrediction.text.toString()}</button>)}
    </span>}
    {!hideStatus && <small>{statusLabel(status, territoryBounds)}</small>}
  </span>;
}

function placeDetails(place, formattedAddress) {
  const components = place.addressComponents || [];
  const component = (...types) => components.find((item) => types.some((type) => item.types.includes(type)));
  return {
    endereco: formattedAddress,
    logradouro: component("route")?.longText || "",
    numero: component("street_number")?.longText || "",
    bairro: component("neighborhood", "sublocality_level_1", "administrative_area_level_4")?.longText || "",
    cidade: component("administrative_area_level_2", "locality")?.longText || "",
    uf: component("administrative_area_level_1")?.shortText || "",
    cep: component("postal_code")?.longText || "",
    latitude: coordinateValue(place.location, "lat"),
    longitude: coordinateValue(place.location, "lng"),
    placeId: place.id || null,
  };
}

function coordinateValue(location, key) {
  const value = location?.[key];
  return typeof value === "function" ? value.call(location) : Number.isFinite(Number(value)) ? Number(value) : null;
}

function loadGoogleMapsPlaces(apiKey) {
  if (window.google?.maps?.importLibrary) return Promise.resolve();
  if (googleMapsPromise) return googleMapsPromise;
  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = `__gabflowGoogleMapsReady${++googleMapsCallbackId}`;
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => { cleanup(); reject(new Error("Google Maps load timeout")); }, 12000);
    window[callbackName] = () => {
      cleanup();
      if (window.google?.maps?.importLibrary) resolve();
      else reject(new Error("Google Places library unavailable"));
    };
    const params = new URLSearchParams({ key: apiKey, libraries: "places", language: "pt-BR", region: "BR", v: "weekly", loading: "async", callback: callbackName });
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.defer = true;
    script.onerror = () => { cleanup(); reject(new Error("Google Maps failed to load")); };
    document.head.appendChild(script);
    function cleanup() {
      window.clearTimeout(timeout);
      delete window[callbackName];
    }
  });
  return googleMapsPromise;
}

function statusLabel(status, bounds) {
  if (status === "disabled") return "Google Maps não configurado; busca de endereço indisponível";
  if (status === "ready" && hasValidBounds(bounds)) return "Sugestões do Google Maps restritas ao território";
  if (status === "ready") return "Sugestões do Google Maps ativas";
  if (status === "error") return "Google Maps indisponível; verifique a chave e a Places API (New)";
  return "Carregando Google Maps...";
}

function googleLocationRestriction(bounds) {
  if (!hasValidBounds(bounds)) return null;
  return { west: Number(bounds.minLongitude), north: Number(bounds.maxLatitude), east: Number(bounds.maxLongitude), south: Number(bounds.minLatitude) };
}

function hasValidBounds(bounds) {
  if (!bounds) return false;
  const minLatitude = Number(bounds.minLatitude);
  const maxLatitude = Number(bounds.maxLatitude);
  const minLongitude = Number(bounds.minLongitude);
  const maxLongitude = Number(bounds.maxLongitude);
  return Number.isFinite(minLatitude) && Number.isFinite(maxLatitude) && Number.isFinite(minLongitude) && Number.isFinite(maxLongitude) && minLatitude < maxLatitude && minLongitude < maxLongitude;
}
