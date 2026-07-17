import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AIAssistancePanel } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

const request = {
  id: "request-1",
  assistenciaIA: {
    id: "assistance-1",
    status: "CONCLUIDA",
    statusRevisao: "PENDENTE",
    modelo: "gabflow-assistance-rules-v1",
    confianca: 0.84,
    resultado: {
      resumoHistorico: "Solicitação sobre falta de vacinas aguardando atendimento.",
      perguntasFaltantes: ["Qual unidade precisa do atendimento?"],
      documentosNecessarios: [{ nome: "Comprovante", motivo: "Ajuda a localizar o atendimento.", obrigatorio: false }],
      proximosPassos: [{ ordem: 1, acao: "Confirmar a unidade.", responsavel: "GABINETE", justificativa: "Completa o relato." }],
      respostaSugerida: { canal: "WHATSAPP", tom: "ACOLHEDOR", assunto: null, conteudo: "Olá. Estamos acompanhando sua solicitação." },
      envioAutomatico: false,
    },
  },
};

it("transfere o rascunho revisado sem enviar automaticamente", async () => {
  const updated = { ...request, assistenciaIA: { ...request.assistenciaIA, statusRevisao: "EDITADA" } };
  let finishReview;
  const pendingReview = new Promise((resolve) => { finishReview = resolve; });
  apiRequest.mockReturnValueOnce(pendingReview).mockResolvedValueOnce(updated);
  const onUse = vi.fn();

  render(<AIAssistancePanel request={request} onChanged={vi.fn()} onUse={onUse} onError={vi.fn()} />);

  expect(screen.getByText(/não será enviada automaticamente/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Resposta sugerida"), { target: { value: "Resposta revisada." } });
  fireEvent.click(screen.getByRole("button", { name: "Usar na resposta" }));

  expect(onUse).toHaveBeenCalledWith(expect.objectContaining({ conteudo: "Resposta revisada." }));
  finishReview({ statusRevisao: "EDITADA" });

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/assistencias-ia/assistance-1/revisao",
      expect.objectContaining({ method: "POST" }),
    );
  });
  expect(apiRequest).not.toHaveBeenCalledWith(expect.stringContaining("/respostas"), expect.anything());
});

it("solicita uma nova versão com tom e canal configuráveis", async () => {
  apiRequest.mockResolvedValueOnce({ status: "PENDENTE" }).mockResolvedValueOnce({ ...request, assistenciaIA: { status: "PENDENTE" } });
  render(<AIAssistancePanel request={{ id: "request-1" }} onChanged={vi.fn()} onUse={vi.fn()} onError={vi.fn()} />);

  fireEvent.change(screen.getByLabelText("Tom"), { target: { value: "FORMAL" } });
  fireEvent.change(screen.getByLabelText("Canal"), { target: { value: "EMAIL" } });
  fireEvent.click(screen.getByRole("button", { name: "Gerar sugestões" }));

  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
    "/api/v1/solicitacoes/request-1/assistencia-ia",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ canal: "EMAIL", tom: "FORMAL" }) }),
  ));
});
