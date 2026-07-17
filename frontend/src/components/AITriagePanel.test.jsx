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
        orgaoId: "agency-1",
        orgao: "Secretaria de Saúde",
        prioridadeSugerida: "CRITICA",
        impacto: "ALTO",
        urgencia: "CRITICO",
        resumo: "Pessoa inconsciente.",
        resumoEstruturado: {
          situacao: "Pessoa inconsciente.",
          local: "Avenida Central",
          afetados: "Uma pessoa",
          informacoesAusentes: ["Idade"],
        },
        justificativa: "O relato indica risco imediato.",
        emergencia: true,
        orientacaoEmergencia: "O gabinete não substitui o serviço de emergência.",
        conteudoOfensivo: true,
        marcadoresConteudo: ["ameaça"],
        entidades: { endereco: "Avenida Central", pessoas: ["Uma pessoa"] },
        analiseDuplicidade: {
          modelo: "nomic-embed-text",
          candidatos: [{
            id: "request-2",
            protocolo: "GF-2026-000002",
            titulo: "Pessoa desacordada na Avenida Central",
            pontuacao: 0.89,
            justificativas: ["Similaridade semântica de 91%", "Localização a menos de 500 m"],
          }],
        },
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
      agencies={[{ id: "agency-1", nome: "Secretaria de Saúde", ativa: true }]}
      onChanged={onChanged}
      onError={vi.fn()}
    />,
  );

  expect(screen.getByText("Possível emergência")).toBeInTheDocument();
  expect(screen.getByText("Resumo do relato")).toBeInTheDocument();
  expect(screen.getByText("Classificação sugerida")).toBeInTheDocument();
  expect(screen.getByText("Linguagem sensível identificada")).toBeInTheDocument();
  expect(screen.getByText("Entidades identificadas")).toBeInTheDocument();
  expect(screen.getByText("Informações ausentes:")).toBeInTheDocument();
  expect(screen.getByText("Possíveis duplicidades")).toBeInTheDocument();
  expect(screen.getByText("89% compatível")).toBeInTheDocument();
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

it("agrupa uma duplicidade sem excluir após confirmação humana", async () => {
  const request = {
    id: "request-1",
    duplicidades: [],
    triagemIA: {
      id: "execution-1",
      status: "CONCLUIDA",
      statusRevisao: "PENDENTE",
      modelo: "qwen2.5:3b",
      versaoPrompt: "triage-v3",
      confianca: 0.82,
      resultado: {
        resumo: "Poste apagado.",
        justificativa: "Iluminação pública.",
        analiseDuplicidade: {
          modelo: "nomic-embed-text",
          candidatos: [{
            id: "request-2",
            protocolo: "GF-2026-000002",
            titulo: "Lâmpada apagada na mesma rua",
            pontuacao: 0.87,
            justificativas: ["Similaridade semântica de 90%"],
          }],
        },
      },
    },
  };
  apiRequest
    .mockResolvedValueOnce({ id: "group-1" })
    .mockResolvedValueOnce({ ...request, duplicidades: [{ id: "request-2" }] });
  const onChanged = vi.fn();

  render(
    <AITriagePanel
      request={request}
      categories={[]}
      agencies={[]}
      onChanged={onChanged}
      onError={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Confirmar duplicidade" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/solicitacoes/agrupar-duplicadas",
      expect.objectContaining({ method: "POST" }),
    );
    expect(onChanged).toHaveBeenCalled();
  });
});
