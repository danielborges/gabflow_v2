import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { Workspace } from "./Workspace";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const electoralAvailability = {
  disponivel: true,
  mandato: {
    id: "mandate-1",
    cargo: "Vereadora",
    jurisdicao: "Juiz de Fora/MG",
    status: "active",
  },
  capacidades: ["consultar_dados_publicos"],
  limiarPrivacidade: 10,
  funcionalidades: { catalogo: true },
};

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path === "/api/v1/electoral/disponibilidade") return electoralAvailability;
    if (path === "/api/v1/electoral/elections") return {
      items: [{ id: "e-1", year: 2024, nome: "Eleições Municipais", uf: "MG" }],
      total: 1,
    };
    if (path === "/api/v1/electoral/coverage") return {
      content: [{ datasetVersionId: "d-1", ano: 2022, uf: "MG", cargoCodigo: "6", votos: 1234, qualidade: 1 }],
      total: 1,
    };
    if (path === "/api/v1/electoral/quality") return { qualidadeMedia: 1 };
    if (path === "/api/v1/electoral/favorites" && options.method === "POST") return { id: "favorite-1", target_id: "candidate-1", label: "MAURÍCIO DELGADO" };
    if (path === "/api/v1/electoral/favorites") return { content: [] };
    if (path === "/api/v1/electoral/saved-comparisons" && options.method === "POST") return { id: "saved-1", name: "Meu comparativo", election_id: "e-1", candidate_ids: ["candidate-1", "candidate-2"], level: "municipality" };
    if (path === "/api/v1/electoral/saved-comparisons") return { content: [] };
    if (path.startsWith("/api/v1/electoral/candidates?")) return {
      items: [{
        id: "candidate-1",
        candidacy_id: "candidacy-1",
        external_id: "130001937518",
        full_name: "MAURÍCIO HENRIQUE PINTO DE OLIVEIRA DELGADO",
        ballot_name: "MAURÍCIO DELGADO",
        number: "18010",
        party: { acronym: "REDE", number: 18 },
        office: { name: "VEREADOR" },
      }, {
        id: "candidate-2",
        candidacy_id: "candidacy-2",
        external_id: "candidate-2-external",
        full_name: "CANDIDATA COMPARÁVEL",
        ballot_name: "CANDIDATA TESTE",
        number: "18123",
        party: { acronym: "REDE", number: 18 },
        office: { name: "VEREADOR" },
      }],
      total: 2,
      page: 1,
      perPage: 20,
    };
    if (path.startsWith("/api/v1/electoral/candidates/candidate-1/results?")) return {
      candidate: {
        ballot_name: "MAURÍCIO DELGADO",
        number: "18010",
        party: { acronym: "REDE" },
        office: { name: "VEREADOR" },
      },
      candidate_total_votes: 5453,
      dataset_version: "ccfd70f9-4962-4d50-b56c-ee26b6062782",
      quality_score: 1,
      denominator: {
        label: "Votos nominais válidos do mesmo cargo e território",
        formula: "votos_do_candidato / votos_nominais_validos_do_cargo_no_territorio",
      },
      source: "https://cdn.tse.jus.br/recurso.zip",
      page: 1,
      perPage: 50,
      total: 1,
      items: [{
        territory_id: "territory-1",
        territory_name: "JUIZ DE FORA",
        votes: 5453,
        share: 0.0197,
        rank: 10,
        denominator_value: 275026,
        quality_warning: null,
      }],
    };
    if (path === "/api/v1/electoral/candidates/candidate-1/history") return {
      identity: { reviewed: false, warning: "Vínculo automático por nome completo." },
      warnings: [{ code: "PARTY_CHANGED", message: "O partido mudou entre as eleições." }],
      items: [{
        candidate: {
          candidacy_id: "history-2020",
          election: { year: 2020 },
          party: { acronym: "DEM" },
          number: "25010",
        },
        candidate_total_votes: 4106,
        territory: { share: 0.01695251, rank: 6 },
      }],
    };
    if (path.startsWith("/api/v1/electoral/candidates/candidate-1/map?")) return {
      geometry_available: true,
      geometry_version: "geometry-version-1",
      reference_year: 2024,
      source: "https://servicodados.ibge.gov.br/api/v3/malhas/estados/31",
      warnings: [],
      features: [{
        id: "geometry-1",
        geometry: { type: "Polygon", coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] },
        properties: { territory_code: "47333", territory_name: "JUIZ DE FORA", votes: 5453, share: 0.0197, rank: 10, variation: 1347 },
      }],
    };
    if (path.endsWith("/identity-review")) return { content: [{ decision: "CONFIRMED" }] };
    if (path === "/api/v1/electoral/comparisons") return {
      candidates: [
        { id: "candidate-1", ballot_name: "MAURÍCIO DELGADO" },
        { id: "candidate-2", ballot_name: "CANDIDATA TESTE" },
      ],
      denominator: { label: "Votos nominais válidos do mesmo cargo e território" },
      items: [{
        territory_code: "47333",
        territory_name: "JUIZ DE FORA",
        denominator_value: 275026,
        series: [
          { candidate_id: "candidate-1", votes: 5453, share: 0.0197, rank: 10 },
          { candidate_id: "candidate-2", votes: 3200, share: 0.0116, rank: 15 },
        ],
      }],
    };
    if (path === "/api/v1/notificacoes") return { content: [], naoLidas: 0 };
    return { content: [] };
  });
});

it("pesquisa candidatura e exibe resultado territorial com filtros na URL", async () => {
  render(
    <Workspace
      user={{
        name: "Maurício Delgado",
        role: "representative",
        tenant: {
          name: "Gabinete Demonstração",
          modulosHabilitados: ["solicitacoes", "inteligencia_eleitoral"],
        },
      }}
      onLogout={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Inteligência Eleitoral" }));
  const query = await screen.findByLabelText("Nome ou número");
  fireEvent.change(query, { target: { value: "Mauricio Delgado" } });
  fireEvent.click(screen.getByRole("button", { name: "Pesquisar" }));

  expect(await screen.findByText("MAURÍCIO HENRIQUE PINTO DE OLIVEIRA DELGADO")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Adicionar aos favoritos: MAURÍCIO DELGADO" }));
  expect(await screen.findByRole("button", { name: "Remover dos favoritos: MAURÍCIO DELGADO" })).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "Ver resultado" })[0]);

  expect(await screen.findByRole("heading", { name: "MAURÍCIO DELGADO" })).toBeInTheDocument();
  expect(screen.getAllByText("5.453").length).toBeGreaterThan(0);
  expect(screen.getByText("10º")).toBeInTheDocument();
  expect(window.location.search).toContain("busca=Mauricio+Delgado");
  expect(window.location.search).toContain("candidato=candidate-1");
});

it("exibe o catalogo eleitoral somente ao Parlamentar habilitado", async () => {
  render(
    <Workspace
      user={{
        name: "Vereadora Teste",
        role: "representative",
        tenant: {
          name: "Gabinete Teste",
          modulosHabilitados: ["solicitacoes", "inteligencia_eleitoral"],
        },
      }}
      onLogout={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Inteligência Eleitoral" }));

  expect(await screen.findByRole("heading", { name: "Catálogo consultável" })).toBeInTheDocument();
  expect(screen.getByText("Juiz de Fora/MG")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Pesquisar candidatura" })).toBeInTheDocument();
  expect(apiRequest).toHaveBeenCalledWith("/api/v1/electoral/disponibilidade");
});

it("exibe histórico e compara duas candidaturas com o mesmo denominador", async () => {
  render(
    <Workspace
      user={{ name: "Maurício Delgado", role: "representative", tenant: { name: "Gabinete Demonstração", modulosHabilitados: ["inteligencia_eleitoral"] } }}
      onLogout={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Inteligência Eleitoral" }));
  fireEvent.change(await screen.findByLabelText("Nome ou número"), { target: { value: "Mauricio" } });
  fireEvent.click(screen.getByRole("button", { name: "Pesquisar" }));
  fireEvent.click((await screen.findAllByRole("button", { name: "Ver resultado" }))[0]);
  expect(await screen.findByRole("heading", { name: "Histórico da candidatura" })).toBeInTheDocument();
  expect(screen.getByText("O partido mudou entre as eleições.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Mapa territorial" })).toBeInTheDocument();

  const include = screen.getAllByRole("checkbox", { name: "Incluir" });
  fireEvent.click(include[0]);
  fireEvent.click(include[1]);
  fireEvent.click(screen.getByRole("button", { name: "Comparar 2 candidaturas" }));
  expect(await screen.findByText("275.026")).toBeInTheDocument();
  expect(screen.getAllByText("5.453").length).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText("Nome do comparativo"), { target: { value: "Meu comparativo" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar comparativo" }));
  expect(await screen.findByRole("button", { name: "Meu comparativo" })).toBeInTheDocument();
});

it("nao mostra o modulo eleitoral a outro perfil mesmo quando a chave esta presente", () => {
  render(
    <Workspace
      user={{
        name: "Admin Teste",
        role: "admin",
        tenant: {
          name: "Gabinete Teste",
          modulosHabilitados: ["solicitacoes", "inteligencia_eleitoral"],
        },
      }}
      onLogout={vi.fn()}
    />,
  );

  expect(screen.queryByRole("button", { name: "Inteligência Eleitoral" })).not.toBeInTheDocument();
});
