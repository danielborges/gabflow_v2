import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useState } from "react";
import { AttachmentDropzone } from "./RequestsPage";

function DropzoneHarness({ onError = vi.fn(), onSubmit = vi.fn() }) {
  const [file, setFile] = useState(null);
  return (
    <AttachmentDropzone
      file={file}
      uploading={false}
      onFile={setFile}
      onError={onError}
      onSubmit={onSubmit}
    />
  );
}

it("seleciona arquivo por drag and drop e permite removê-lo", () => {
  render(<DropzoneHarness />);
  const dropzone = screen.getByRole("button", {
    name: "Selecionar ou arrastar arquivo para anexar",
  });
  const file = new File(["conteúdo"], "relato.txt", { type: "text/plain" });

  fireEvent.dragEnter(dropzone, { dataTransfer: { files: [file] } });
  expect(dropzone).toHaveClass("is-dragging");
  fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });

  expect(screen.getByText("relato.txt")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Enviar anexo" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Remover arquivo selecionado" }));
  expect(screen.queryByText("relato.txt")).not.toBeInTheDocument();
});

it("bloqueia no cliente arquivos acima de 15 MB", () => {
  const onError = vi.fn();
  render(<DropzoneHarness onError={onError} />);
  const file = new File(["vídeo"], "grande.mp4", { type: "video/mp4" });
  Object.defineProperty(file, "size", { value: 15 * 1024 * 1024 + 1 });

  fireEvent.drop(
    screen.getByRole("button", { name: "Selecionar ou arrastar arquivo para anexar" }),
    { dataTransfer: { files: [file] } },
  );

  expect(onError).toHaveBeenCalledWith("O arquivo excede o limite de 15 MB.");
  expect(screen.getByRole("button", { name: "Enviar anexo" })).toBeDisabled();
});
