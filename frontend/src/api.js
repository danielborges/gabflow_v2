function getCookie(name) {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];
}

export async function apiRequest(path, options = {}) {
  const method = options.method || "GET";
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...options.headers,
  };
  const csrfToken = getCookie("csrf_access_token");

  if (!options.skipCsrf && !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) && csrfToken) {
    headers["X-CSRF-TOKEN"] = decodeURIComponent(csrfToken);
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: options.credentials || "include",
  });
  const data = await readResponsePayload(response);

  if (!response.ok) {
    throw new Error(errorMessageFor(response, data, "Não foi possível concluir a operação."));
  }
  return data;
}

export async function apiDownload(path, options = {}) {
  const method = options.method || "POST";
  const headers = { ...options.headers };
  const csrfToken = getCookie("csrf_access_token");
  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) && csrfToken) {
    headers["X-CSRF-TOKEN"] = decodeURIComponent(csrfToken);
  }
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const data = await readResponsePayload(response);
    throw new Error(errorMessageFor(response, data, "Não foi possível gerar o arquivo."));
  }
  return response.blob();
}

async function readResponsePayload(response) {
  const contentType = response.headers?.get?.("content-type") || "";
  if (contentType.includes("application/json") || (!contentType && response.json)) {
    return response.json().catch(() => ({}));
  }
  const text = await response.text?.().catch(() => "");
  return text ? { message: text } : {};
}

function errorMessageFor(response, data, fallback) {
  if (response.status === 413) {
    return "O arquivo enviado excede o limite permitido. Para a base documental RAG, use arquivos de até 25 MB.";
  }
  return data.message || data.error || fallback;
}
