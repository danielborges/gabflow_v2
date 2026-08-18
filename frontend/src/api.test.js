import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "./api";

describe("apiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("não exibe uma página HTML devolvida pela camada de segurança", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: { get: () => "text/html" },
      text: () => Promise.resolve("<html><body><h1>403 Forbidden</h1></body></html>"),
    }));

    await expect(apiRequest("/api/v1/admin/parlamentar", { method: "PATCH", body: "{}" }))
      .rejects.toThrow("A operação foi bloqueada pela camada de segurança. Tente novamente ou contate o suporte.");
  });

  it("preserva a mensagem JSON fornecida pela API em respostas 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ message: "Acesso não autorizado para este perfil." }),
    }));

    await expect(apiRequest("/api/v1/admin/parlamentar", { method: "PATCH", body: "{}" }))
      .rejects.toThrow("Acesso não autorizado para este perfil.");
  });
});
