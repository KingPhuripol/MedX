// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { AgentTrace } from "./clinical";
import type { Run } from "../../shared/types";
afterEach(cleanup);

const run = (trace: Run["trace"]): Run => ({ run_id: "r", case_revision: 1, status: "FAILED_SAFE", response: "", user_text: "", proposals: [], trace, provenance: { model: "m-1", design: { design_id: "fixed" } } });

it("shows each executed step, marks the failed one, and names design and model", () => {
  render(<AgentTrace run={run([
    { sequence: 1, tool: "read_snapshot", status: "COMPLETED", elapsed_ms: 2, evidence_ids: ["a", "b"] },
    { sequence: 2, tool: "create_draft", status: "FAILED", elapsed_ms: 4100, evidence_ids: [] },
  ])} />);
  expect(screen.getByText(/2 ขั้น · 4.1 วินาที/)).toBeTruthy();
  expect(screen.getByText("อ่านข้อมูลเคสล่าสุด")).toBeTruthy();
  expect(screen.getByText(/อ้างหลักฐาน 2/)).toBeTruthy();
  expect(screen.getByText("เขียนร่างส่งต่อ").closest("li")?.className).toContain("--failed");
  expect(screen.getByText("design: fixed · model: m-1")).toBeTruthy();
});

it("renders nothing for a run recorded before traces existed", () => {
  const { container } = render(<AgentTrace run={run(undefined)} />);
  expect(container.innerHTML).toBe("");
});
