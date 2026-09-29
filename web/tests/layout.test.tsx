import { render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import RootLayout from "@/app/layout";
import Disclaimer from "@/components/Disclaimer";
import { DISCLAIMER_EN, DISCLAIMER_TH } from "@/lib/copy";

describe("research-prototype disclaimer", () => {
  it("has the exact English and Thai text as a note", () => {
    render(<Disclaimer />);
    const note = screen.getByTestId("research-disclaimer");
    expect(note).toHaveAttribute("role", "note");
    expect(screen.getByRole("note")).toBe(note);
    expect(note).toHaveTextContent(DISCLAIMER_EN);
    expect(note).toHaveTextContent(DISCLAIMER_TH);
    expect(DISCLAIMER_EN).toBe(
      "Research prototype — not for clinical use. Outputs are suggestions for review and require confirmation by a clinician.",
    );
    expect(DISCLAIMER_TH).toBe("ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง ผลลัพธ์เป็นข้อเสนอที่ต้องให้บุคลากรยืนยัน");
  });

  it("is rendered by the root layout before page content on every page", () => {
    const html = renderToStaticMarkup(
      <RootLayout>
        <p>page-body</p>
      </RootLayout>,
    );
    expect(html).toContain('data-testid="research-disclaimer"');
    expect(html).toContain('role="note"');
    expect(html).toContain(DISCLAIMER_EN);
    expect(html).toContain(DISCLAIMER_TH);
    expect(html.indexOf("research-disclaimer")).toBeLessThan(html.indexOf("page-body"));
    expect(html).toContain('<html lang="th">');
  });

  it("renders the MedX wordmark after the disclaimer and before page content", () => {
    const html = renderToStaticMarkup(
      <RootLayout>
        <p>page-body</p>
      </RootLayout>,
    );
    expect(html).toMatch(/<body><div class="disclaimer"/);
    const wordmark = html.indexOf('data-testid="wordmark"');
    expect(wordmark).toBeGreaterThan(html.indexOf("research-disclaimer"));
    expect(wordmark).toBeLessThan(html.indexOf("page-body"));
    expect(html).toContain('aria-label="MedX"');
  });
});
