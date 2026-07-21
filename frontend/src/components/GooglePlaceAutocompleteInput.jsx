import { useEffect, useRef, useState } from "react";

const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
let googleMapsPromise;

export function GooglePlaceAutocompleteInput({ value, onChange, placeholder }) {
  const inputRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!googleMapsApiKey || !inputRef.current) return undefined;
    let listener;
    let autocomplete;
    let disposed = false;

    loadGoogleMapsPlaces(googleMapsApiKey)
      .then(() => {
        if (disposed || !inputRef.current || !window.google?.maps?.places) return;
        autocomplete = new window.google.maps.places.Autocomplete(inputRef.current, {
          componentRestrictions: { country: "br" },
          fields: ["formatted_address", "geometry", "name", "place_id"],
        });
        listener = autocomplete.addListener("place_changed", () => {
          const place = autocomplete.getPlace();
          const nextValue = place.formatted_address || place.name || inputRef.current.value;
          onChangeRef.current(nextValue);
        });
        setEnabled(true);
      })
      .catch(() => {
        setEnabled(false);
      });

    return () => {
      disposed = true;
      listener?.remove();
      autocomplete?.unbindAll?.();
    };
  }, []);

  return (
    <span className="maps-autocomplete-field">
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => onChangeRef.current(event.target.value)}
        placeholder={placeholder}
      />
      {googleMapsApiKey && (
        <small>{enabled ? "Sugestões do Google Maps ativas" : "Carregando Google Maps..."}</small>
      )}
    </span>
  );
}

function loadGoogleMapsPlaces(apiKey) {
  if (window.google?.maps?.places) return Promise.resolve();
  if (googleMapsPromise) return googleMapsPromise;

  googleMapsPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const params = new URLSearchParams({
      key: apiKey,
      libraries: "places",
      language: "pt-BR",
      region: "BR",
      loading: "async",
    });
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.onerror = () => reject(new Error("Google Maps failed to load"));
    script.onload = () => resolve();
    document.head.appendChild(script);
  });
  return googleMapsPromise;
}
