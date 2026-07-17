import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AudioTranscriptionPanel } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

it("permite revisar a transcrição mantendo acesso ao áudio original", async () => {
  const attachment = {
    id: "attachment-1",
    nome: "relato.mp3",
    downloadUrl: "/api/v1/anexos/attachment-1/download?token=token",
    transcricao: {
      id: "transcription-1",
      status: "CONCLUIDA",
      statusRevisao: "PENDENTE",
      modelo: "base",
      idioma: "pt",
      duracaoSegundos: 4.2,
      textoGerado: "A rua está sem iluminação.",
      textoRevisado: null,
    },
  };
  apiRequest.mockResolvedValue({ statusRevisao: "EDITADA" });
  const onRefresh = vi.fn().mockResolvedValue(undefined);

  render(
    <AudioTranscriptionPanel
      attachment={attachment}
      onRefresh={onRefresh}
      onError={vi.fn()}
    />,
  );

  expect(screen.getByText("Transcrição local")).toBeInTheDocument();
  expect(screen.getByText(/arquivo de áudio original é preservado/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Texto transcrito"), {
    target: { value: "A rua está totalmente sem iluminação." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar correções" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/transcricoes-audio/transcription-1/revisao",
      expect.objectContaining({ method: "POST" }),
    );
    expect(onRefresh).toHaveBeenCalled();
  });
});

it("oferece reprocessamento quando a transcrição falha", async () => {
  const attachment = {
    downloadUrl: "/audio",
    transcricao: {
      id: "transcription-2",
      status: "FALHOU",
      statusRevisao: "PENDENTE",
      erro: "Áudio inválido.",
    },
  };
  apiRequest.mockResolvedValue({ status: "PENDENTE" });
  const onRefresh = vi.fn().mockResolvedValue(undefined);

  render(
    <AudioTranscriptionPanel
      attachment={attachment}
      onRefresh={onRefresh}
      onError={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/transcricoes-audio/transcription-2/reprocessar",
      { method: "POST" },
    );
  });
});
