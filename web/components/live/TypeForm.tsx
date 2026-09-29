"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/Field";
import type { Speaker } from "@/lib/voice";

/** Text fallback: posts the same turn as speech, with the speaker chosen here. */
export function TypeForm({
  busy,
  onSpeaker,
  onSubmit,
  onFinish,
}: {
  busy: boolean;
  onSpeaker: (s: Speaker) => void;
  onSubmit: (speaker: Speaker, text: string) => Promise<boolean>;
  /** Present only when a typed-only session can be finished from here (no call in progress). */
  onFinish?: () => void;
}) {
  const [speaker, setSpeaker] = useState<Speaker>("patient");
  const [text, setText] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (await onSubmit(speaker, text)) setText("");
  }

  return (
    <form className="live-panel live-type-form" data-testid="live-type-form" aria-label="พิมพ์แทนการพูด" onSubmit={submit}>
      <Field label="ผู้พูด" htmlFor="live-speaker">
        <select
          id="live-speaker"
          value={speaker}
          onChange={(e) => {
            const s = e.target.value as Speaker;
            setSpeaker(s);
            onSpeaker(s);
          }}
        >
          <option value="patient">ผู้ป่วย</option>
          <option value="relative">ญาติ</option>
          <option value="nurse">พยาบาล</option>
        </select>
      </Field>
      <Field label="ข้อความ" htmlFor="live-text">
        <input id="live-text" lang="th" value={text} autoComplete="off" onChange={(e) => setText(e.target.value)} required />
      </Field>
      <div className="live-type-actions">
        <Button type="submit" disabled={busy}>
          ส่ง
        </Button>
        {onFinish && (
          <Button type="button" variant="secondary" data-testid="live-end-text" onClick={onFinish}>
            จบการสนทนา
          </Button>
        )}
      </div>
    </form>
  );
}
