import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Wordmark from "@/components/Wordmark";

describe("MedX wordmark", () => {
  it("has accessible name MedX with the X in a .wordmark-x span", () => {
    render(<Wordmark />);
    const mark = screen.getByRole("img", { name: "MedX" });
    expect(mark).toHaveTextContent("MedX");
    const x = mark.querySelector(".wordmark-x");
    expect(x).not.toBeNull();
    expect(x).toHaveTextContent(/^X$/);
    expect(mark.querySelector("img")).toBeNull();
  });
});
