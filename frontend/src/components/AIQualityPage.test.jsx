import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { apiRequest } from "../api";
import { AIQualityPage } from "./AIQualityPage";

vi.mock("../api", () => ({ apiRequest: vi.fn() }));

it("apresenta métricas de qualidade e revisão humana", async () => {
  apiRequest.mockResolvedValue({
    amostraMinimaAtingida: false,
    indicadores: {
      execucoes: 10,
      falhas: 1,
      revisadas: 8,
      taxaConclusao: 0.9,
      taxaAceitacao: 0.75,
      taxaIntervencaoHumana: 0.25,
      taxaFallback: 0.1,
      concordanciaCategoria: 0.875,
      confiancaMedia: 0.82,
      latenciaMediaMs: 1850,
    },
    revisoes: { pendentes: 1, aceitas: 6, editadas: 1, rejeitadas: 1 },
    cobertura: {
      entidadesExtraidas: 8,
      orgaosSugeridos: 7,
      conteudoOfensivoSinalizado: 1,
      emergenciasSinalizadas: 1,
      analisesDuplicidade: 10,
      candidatosDuplicidade: 3,
      audiosTranscritos: 4,
      transcricoesRevisadas: 3,
      falhasTranscricao: 1,
    },
    porModelo: [{ provedor: "OLLAMA", modelo: "qwen2.5:3b", execucoes: 10, confiancaMedia: 0.82, latenciaMediaMs: 1850 }],
  });

  render(<AIQualityPage />);

  expect(await screen.findByText("Qualidade da triagem")).toBeInTheDocument();
  expect(screen.getByText("75%")).toBeInTheDocument();
  expect(screen.getByText("qwen2.5:3b")).toBeInTheDocument();
  expect(screen.getByText("Candidatos similares")).toBeInTheDocument();
  expect(screen.getByText("Áudios transcritos")).toBeInTheDocument();
  expect(screen.getByText(/maior estabilidade após 30 revisões/)).toBeInTheDocument();
});
