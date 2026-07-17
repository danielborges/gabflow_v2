import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { DocumentOcrPanel } from "./RequestsPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

it("apresenta confiança e permite corrigir o texto preservando o documento", async () => {
  const attachment = {
    id: "attachment-1",
    nome: "comprovante.png",
    downloadUrl: "/api/v1/anexos/attachment-1/download?token=token",
    ocr: {
      id: "ocr-1",
      status: "CONCLUIDO",
      statusRevisao: "PENDENTE",
      modelo: "tesseract-5",
      idioma: "por",
      confianca: 0.91,
      paginas: 1,
      textoGerado: "Prefeitura Municipal",
      textoRevisado: null,
      detalhesPaginas: [{ pagina: 1, confianca: 0.91 }],
    },
  };
  apiRequest.mockResolvedValue({ statusRevisao: "EDITADO" });
  const onRefresh = vi.fn().mockResolvedValue(undefined);

  render(
    <DocumentOcrPanel
      attachment={attachment}
      onRefresh={onRefresh}
      onError={vi.fn()}
    />,
  );

  expect(screen.getByText("OCR local")).toBeInTheDocument();
  expect(screen.getByText("91% confiança")).toBeInTheDocument();
  expect(screen.getByText(/documento original é preservado/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Texto extraído"), {
    target: { value: "Prefeitura Municipal - comprovante." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar correções" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/ocr-documentos/ocr-1/revisao",
      expect.objectContaining({ method: "POST" }),
    );
    expect(onRefresh).toHaveBeenCalled();
  });
});

it("oferece reprocessamento quando o OCR falha", async () => {
  const attachment = {
    ocr: {
      id: "ocr-2",
      status: "FALHOU",
      statusRevisao: "PENDENTE",
      erro: "Nenhum texto reconhecível.",
    },
  };
  apiRequest.mockResolvedValue({ status: "PENDENTE" });

  render(
    <DocumentOcrPanel
      attachment={attachment}
      onRefresh={vi.fn().mockResolvedValue(undefined)}
      onError={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/ocr-documentos/ocr-2/reprocessar",
      { method: "POST" },
    );
  });
});
