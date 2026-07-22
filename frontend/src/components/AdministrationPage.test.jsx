import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AdministrationPage } from "./AdministrationPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const emptyCollection = { content: [] };

function mockAdminApi(path, options = {}) {
  if (options.method === "PATCH" && path === "/api/v1/admin/perfil-gabinete") {
    return Promise.resolve({});
  }

  const responses = {
    "/api/v1/admin/categorias": emptyCollection,
    "/api/v1/admin/territorios": emptyCollection,
    "/api/v1/admin/orgaos": emptyCollection,
    "/api/v1/admin/templates-resposta": emptyCollection,
    "/api/v1/admin/jurisdicao": null,
    "/api/v1/admin/integracoes": emptyCollection,
    "/api/v1/admin/perfil-gabinete": {
      dadosInstitucionais: {
        nomeGabinete: "Gabinete Teste",
        estado: "MG",
        municipio: "Juiz de Fora",
      },
      redesSociais: {},
      identidadeVisual: {},
      chefeGabineteId: "",
    },
    "/api/v1/admin/parlamentar": null,
    "/api/v1/admin/usuarios": emptyCollection,
    "/api/v1/admin/partidos": emptyCollection,
    "/api/v1/admin/auditoria?page=1&perPage=10": {
      content: [],
      page: 1,
      perPage: 10,
      total: 0,
      totalPages: 1,
    },
  };

  return Promise.resolve(responses[path] ?? emptyCollection);
}

describe("AdministrationPage office settings", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation(mockAdminApi);
  });

  it("usa estados cadastrados e filtra municipios pelo estado selecionado", async () => {
    render(<AdministrationPage />);

    const stateSelect = await screen.findByLabelText("Estado");
    expect(stateSelect).toHaveValue("MG");
    expect(screen.getByRole("option", { name: "São Paulo - SP" })).toBeInTheDocument();

    const cityInput = screen.getByRole("combobox", { name: "Município" });
    fireEvent.focus(cityInput);
    fireEvent.change(cityInput, { target: { value: "Juiz" } });

    const minasOptions = await screen.findByRole("listbox");
    expect(within(minasOptions).getByRole("option", { name: /Juiz de Fora/ })).toBeInTheDocument();
    expect(within(minasOptions).queryByRole("option", { name: /São Paulo/ })).not.toBeInTheDocument();

    fireEvent.change(stateSelect, { target: { value: "SP" } });
    expect(cityInput).toHaveValue("");

    fireEvent.focus(cityInput);
    fireEvent.change(cityInput, { target: { value: "Sao Paulo" } });
    fireEvent.click(await within(screen.getByRole("listbox")).findByRole("option", { name: /São Paulo/ }));

    fireEvent.click(screen.getByRole("button", { name: /Salvar gabinete/ }));

    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/v1/admin/perfil-gabinete",
        expect.objectContaining({
          method: "PATCH",
          body: expect.any(String),
        }),
      );
    });

    const [, saveOptions] = apiRequest.mock.calls.find(([path, options]) => (
      path === "/api/v1/admin/perfil-gabinete" && options?.method === "PATCH"
    ));
    const payload = JSON.parse(saveOptions.body);
    expect(payload.dadosInstitucionais.estado).toBe("SP");
    expect(payload.dadosInstitucionais.municipio).toBe("São Paulo");
  });
});
