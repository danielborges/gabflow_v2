import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AITriagePanel } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

it("exibe alerta e registra a revisão humana da triagem", async () => {
  const request = {
    id: "request-1",
    triagemIA: {
      id: "execution-1",
      status: "CONCLUIDA",
      statusRevisao: "PENDENTE",
      modelo: "gabflow-triage-rules-v1",
      versaoPrompt: "triage-v1",
      confianca: 0.91,
      resultado: {
        categoriaId: "category-1",
        categoria: "Saúde",
        subcategoria: "Emergência",
        prioridadeSugerida: "CRITICA",
        impacto: "ALTO",
        urgencia: "CRITICO",
        resumo: "Pessoa inconsciente.",
        justificativa: "O relato indica risco imediato.",
        emergencia: true,
        orientacaoEmergencia: "O gabinete não substitui o serviço de emergência.",
      },
    },
  };
  const updated = { ...request, triagemIA: { ...request.triagemIA, statusRevisao: "ACEITA" } };
  apiRequest
    .mockResolvedValueOnce({ statusRevisao: "ACEITA" })
    .mockResolvedValueOnce(updated);
  const onChanged = vi.fn();

  render(
    <AITriagePanel
      request={request}
      categories={[{ id: "category-1", nome: "Saúde", ativa: true }]}
      onChanged={onChanged}
      onError={vi.fn()}
    />,
  );

  expect(screen.getByText("Possível emergência")).toBeInTheDocument();
  expect(screen.getByText("Resumo do relato")).toBeInTheDocument();
  expect(screen.getByText("Classificação sugerida")).toBeInTheDocument();
  expect(screen.getByLabelText("Confiança da sugestão: 91%")).toBeInTheDocument();
  expect(screen.getByText("91%")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Aceitar sugestão" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/classificacoes-ia/execution-1/revisao",
      expect.objectContaining({ method: "POST" }),
    );
    expect(onChanged).toHaveBeenCalledWith(updated);
  });
});
