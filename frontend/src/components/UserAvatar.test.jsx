import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { UserAvatar } from "./UserAvatar";

describe("UserAvatar", () => {
  test("exibe a foto disponível no lugar das iniciais", () => {
    const { container } = render(<UserAvatar user={{ name: "Paulo Parlamentar", fotoUrl: "https://example.test/paulo.jpg" }} />);

    expect(container.querySelector(".avatar img")).toHaveAttribute("src", "https://example.test/paulo.jpg");
    expect(screen.queryByText("PP")).not.toBeInTheDocument();
  });

  test("usa as iniciais quando a foto não carrega", () => {
    const { container } = render(<UserAvatar user={{ name: "Yuri Dias Fófano", fotografiaUrl: "https://example.test/indisponivel.jpg" }} />);

    fireEvent.error(container.querySelector(".avatar img"));

    expect(container.querySelector(".avatar img")).not.toBeInTheDocument();
    expect(screen.getByText("YF")).toBeInTheDocument();
  });
});
