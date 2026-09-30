/** V2C-C12: text wordmark "Med"+"X" with aria-label MedX on login and start; no image logo. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Login } from "@/components/Login";
import { Start } from "@/components/Start";
import { Wordmark } from "@/components/Wordmark";

import { installApi } from "./helpers";

describe("wordmark", () => {
  it('is text "Med" + "X" with aria-label MedX and no image', () => {
    render(<Wordmark size={28} />);
    const w = screen.getByRole("img", { name: "MedX" });
    expect(w.tagName).toBe("SPAN");
    expect(w.textContent).toBe("MedX");
    expect(w.querySelector("span")?.textContent).toBe("X");
    expect(w.querySelector("img, svg")).toBeNull();
  });

  it("appears on login (28) and start (20)", async () => {
    installApi();
    const { unmount } = render(<Login onUser={vi.fn()} publicDemo={false} />);
    expect(screen.getByTestId("wordmark")).toHaveStyle({ fontSize: "28px" });
    unmount();
    render(<Start username="nurse1" accessCodeRequired={false} onSignOut={vi.fn()} onOpen={vi.fn()} />);
    await screen.findByRole("radiogroup");
    expect(screen.getByTestId("wordmark")).toHaveStyle({ fontSize: "20px" });
    expect(document.querySelectorAll("img")).toHaveLength(0);
  });
});
