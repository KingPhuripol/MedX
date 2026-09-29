import { AlertTriangle } from "lucide-react";

import Notice from "@/components/ui/Notice";
import Section from "@/components/ui/Section";
import { BANNER_INCOMPLETE, BANNER_NOT_PERFORMED, type Screening } from "@/lib/triage";

import "./ScreeningBlock.css";

/**
 * The Case Graph red-flag screening block (slice i2, C1/C2). It states which rule set ran, its label and
 * scope, and counts out of the declared rules. It never reads as an all-clear: an evaluated screen with 0
 * alerts says "0 of N declared rules fired" with the scope; a partial or missing screen shows a text banner
 * (role="alert", warning tokens from the theme), so the state never depends on colour alone.
 */
export default function ScreeningBlock({
  screening,
  staleText = "STALE (not used)",
}: {
  screening: Screening | null | undefined;
  /** How a stale reading is described (care: an abnormal stale value still alerts, D-int2-1). */
  staleText?: string;
}) {
  const s = screening;
  if (!s || s.status === "unavailable" || s.status === "not_evaluated") {
    return (
      <Section
        title="Red-flag screening"
        titleId="screening-title"
        data-testid="screening-section"
        data-status={s?.status ?? "unavailable"}
      >
        <div data-part="stack">
          <Notice
            tone="warning"
            icon={<AlertTriangle size={20} />}
            role="alert"
            data-testid="screening-banner"
          >
            <strong>{BANNER_NOT_PERFORMED}.</strong> The red-flag rules did not run on this case. Do not regard it as
            screened: check red flags yourself and escalate if in doubt.
          </Notice>
          {s && <ScreeningDetails s={s} staleText={staleText} />}
        </div>
      </Section>
    );
  }
  return (
    <Section title="Red-flag screening" titleId="screening-title" data-testid="screening-section" data-status={s.status}>
      <div data-part="stack">
        {s.status === "partially_evaluated" ? (
          <Notice tone="warning" icon={<AlertTriangle size={20} />} role="alert" data-testid="screening-banner">
            <strong>{BANNER_INCOMPLETE}.</strong> {s.n_evaluated} of {s.n_declared} declared rules were evaluated;{" "}
            {s.n_not_evaluated} could not be checked (data missing or stale — not a negative result). {s.n_fired} of{" "}
            {s.n_declared} declared rules fired.
          </Notice>
        ) : (
          <p role="status" data-testid="screening-count" data-part="count">
            <strong>
              {s.n_fired} of {s.n_declared} declared rules fired
            </strong>{" "}
            ({s.n_evaluated} evaluated). Scope: {s.scope}
          </p>
        )}
        <ScreeningDetails s={s} staleText={staleText} />
      </div>
    </Section>
  );
}

function ScreeningDetails({ s, staleText }: { s: Screening; staleText: string }) {
  return (
    <>
      <p data-testid="screening-scope" data-part="detail">
        Rule set {s.rule_set_version} — {s.label}. Scope: {s.scope}
      </p>
      {s.rules_not_evaluated.length > 0 && (
        <p data-testid="screening-not-evaluated" data-part="not-evaluated">
          Not evaluated: {s.rules_not_evaluated.join(", ")}
          {s.missing_inputs.length > 0 ? `. Missing or stale inputs: ${s.missing_inputs.join("; ")}` : ""}
        </p>
      )}
      {s.readings.length > 0 && (
        <details data-part="readings">
          <summary>Vital readings used ({s.readings.length})</summary>
          <ul data-testid="screening-readings">
            {s.readings.map((r) => (
              <li key={r.vital}>
                {r.vital} = {String(r.value)}, read at {r.read_at}, age {r.age_min.toFixed(0)} min of a{" "}
                {r.window_min} min window — {r.fresh ? "fresh" : staleText}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
