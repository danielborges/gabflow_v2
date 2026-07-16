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

  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) && csrfToken) {
    headers["X-CSRF-TOKEN"] = decodeURIComponent(csrfToken);
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "include",
  });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.message || "Não foi possível concluir a operação.");
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
    const data = await response.json().catch(() => ({}));
    throw new Error(data.message || "Não foi possível gerar o arquivo.");
  }
  return response.blob();
}
