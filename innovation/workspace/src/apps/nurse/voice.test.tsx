// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { VoicePage } from "./VoicePage";

afterEach(cleanup);

it("keeps a transcript editable and never submits it without an explicit staff action", () => {
  Element.prototype.scrollIntoView = vi.fn();
  const startRun = vi.fn();
  const setMessage = vi.fn();
  render(<VoicePage
    cases={[{ encounter_id: "synthetic-1", age: 40, case_revision: 0 }]}
    current={{ encounter_id: "synthetic-1", age: 40, case_revision: 0 }}
    facts={[]}
    runs={[]}
    session={{ subject: "nurse-1", role: "intake", workspace: "pilot", csrf: "token" }}
    caps={{ profile: "synthetic_intake_v1", role: "intake", provider: "mock-v2", model: "mock", differential: false, speech: true, synthesis: false, conversation: true, validation: "MOCK_ONLY" }}
    voiceState="idle"
    busy={false}
    job={null}
    message="ข้อความถอดเสียงที่ยังไม่ยืนยัน"
    setMessage={setMessage}
    record={vi.fn()}
    speak={vi.fn()}
    stopAudio={vi.fn()}
    startRun={startRun}
    changeCase={vi.fn()}
    newCaseOpen={false}
    setNewCaseOpen={vi.fn()}
    onNavigateToCockpit={vi.fn()}
  />);

  expect((screen.getByLabelText("Transcript รอตรวจ") as HTMLTextAreaElement).value)
    .toBe("ข้อความถอดเสียงที่ยังไม่ยืนยัน");
  expect(startRun).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "ตรวจแล้ว ส่งให้ผู้ช่วย" }));
  expect(startRun).toHaveBeenCalledWith("conversation");
});
