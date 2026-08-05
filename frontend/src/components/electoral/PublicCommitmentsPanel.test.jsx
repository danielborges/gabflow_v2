import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "../../api";
import { PublicCommitmentsPanel } from "./PublicCommitmentsPanel";

vi.mock("../../api", () => ({ apiRequest: vi.fn() }));

const commitment = {
  id: "commitment-1", title: "Requalificar praça", description: "Entrega pública",
  territory: { id: "territory-1", name: "Centro" },
  responsible: { id: "user-1", name: "Parlamentar" }, due_on: "2026-12-20",
  status: "IN_PROGRESS", effective_status: "IN_PROGRESS", progress: 45,
  evidence: [], history: [{ id: "history-1", action: "CREATED", created_at: "2026-08-04T12:00:00Z" }],
};

const list = {
  can_manage: true, content: [commitment],
  territories: [{ id: "territory-1", name: "Centro" }],
  responsible_users: [{ id: "user-1", name: "Parlamentar", role: "representative" }],
};

const map = {
  boundary: { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [[[-43.4, -21.8], [-43.3, -21.8], [-43.3, -21.7], [-43.4, -21.8]]] } }] },
  source: { name: "IBGE", url: "https://servicodados.ibge.gov.br", official: true },
  features: [{ id: "commitment-1", geometry: { type: "Point", coordinates: [-43.35, -21.76] }, properties: { commitment_id: "commitment-1", title: "Requalificar praça", progress: 45 } }],
  unmapped_commitments: 0,
  warnings: ["Territórios sem geometria oficial; nenhum polígono foi criado artificialmente."],
};

beforeEach(() => {
  vi.clearAllMocks();
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path.endsWith("operational-map")) return map;
    if (path.endsWith("public-commitments") && !options.method) return list;
    if (path.endsWith("public-commitments") && options.method === "POST") return commitment;
    if (path.includes("public-commitments/commitment-1")) return commitment;
    return list;
  });
});

it("sincroniza compromisso entre tabela e mapa oficial", async () => {
  render(<PublicCommitmentsPanel onError={vi.fn()} />);
  expect(await screen.findByText("Requalificar praça")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Mapa operacional de compromissos públicos" })).toBeInTheDocument();
  expect(screen.getByText(/nenhum polígono foi criado artificialmente/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Requalificar praça: 45%" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/electoral/public-commitments/commitment-1"));
  expect(await screen.findByText("Histórico imutável (1)")).toBeInTheDocument();
});

it("cadastra responsável, prazo e local público confirmado", async () => {
  render(<PublicCommitmentsPanel onError={vi.fn()} />);
  await screen.findByText("Requalificar praça");
  fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Nova entrega" } });
  fireEvent.change(screen.getByLabelText("Território"), { target: { value: "territory-1" } });
  fireEvent.change(screen.getByLabelText("Responsável"), { target: { value: "user-1" } });
  fireEvent.change(screen.getByLabelText("Descrição"), { target: { value: "Descrição pública" } });
  fireEvent.change(screen.getByLabelText("Nome do local"), { target: { value: "Praça Central" } });
  fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "-21.76" } });
  fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "-43.35" } });
  fireEvent.click(screen.getByLabelText(/Confirmo que não é endereço residencial/));
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar compromisso" }));
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/electoral/public-commitments",
    expect.objectContaining({ method: "POST" }),
  ));
  const call = apiRequest.mock.calls.find(([path, options]) => path.endsWith("public-commitments") && options?.method === "POST");
  expect(JSON.parse(call[1].body)).toMatchObject({ responsible_user_id: "user-1", location_is_public: true });
});
