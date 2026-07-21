import { useEffect, useRef, useState } from "react";

const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
let googleMapsPromise;
let googleMapsCallbackId = 0;

export function GooglePlaceAutocompleteInput({ value, onChange, placeholder }) {
  const inputRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const [status, setStatus] = useState(googleMapsApiKey ? "loading" : "disabled");

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
        setStatus("ready");
      })
      .catch(() => {
        setStatus("error");
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
      {googleMapsApiKey && <small>{statusLabel(status)}</small>}
    </span>
  );
}

function loadGoogleMapsPlaces(apiKey) {
  if (window.google?.maps?.places) return Promise.resolve();
  if (googleMapsPromise) return googleMapsPromise;

  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = `__gabflowGoogleMapsReady${++googleMapsCallbackId}`;
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("Google Maps load timeout"));
    }, 12000);
    window[callbackName] = () => {
      cleanup();
      if (window.google?.maps?.places) {
        resolve();
      } else {
        reject(new Error("Google Places library unavailable"));
      }
    };
    const params = new URLSearchParams({
      key: apiKey,
      libraries: "places",
      language: "pt-BR",
      region: "BR",
      callback: callbackName,
    });
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.defer = true;
    script.onerror = () => {
      cleanup();
      reject(new Error("Google Maps failed to load"));
    };
    document.head.appendChild(script);

    function cleanup() {
      window.clearTimeout(timeout);
      delete window[callbackName];
    }
  });
  return googleMapsPromise;
}

function statusLabel(status) {
  if (status === "ready") return "Sugestões do Google Maps ativas";
  if (status === "error") return "Google Maps indisponível; use texto livre";
  return "Carregando Google Maps...";
}
