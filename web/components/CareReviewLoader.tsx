"use client";

import { useCallback, useEffect, useState } from "react";

import CareReview from "@/components/CareReview";
import { ERROR_TEXT, postJson, type Assessment, type ReviewAction, type ReviewBody, type Vocabulary } from "@/lib/care";

export default function CareReviewLoader({ assessmentId }: { assessmentId: string }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [vocab, setVocab] = useState<Vocabulary>({ next_information: [], pathway_options: [] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`/api/care/assessments/${encodeURIComponent(assessmentId)}`, { credentials: "same-origin" }),
      fetch("/api/care/vocabulary", { credentials: "same-origin" }),
    ])
      .then(async ([a, v]) => {
        if (!active) return;
        if (!a.ok || !v.ok) {
          setError(a.status === 404 ? "Assessment not found." : "Could not load the assessment.");
          return;
        }
        setAssessment(await a.json());
        setVocab(await v.json());
      })
      .catch(() => active && setError("The service is unavailable. Please try again."));
    return () => {
      active = false;
    };
  }, [assessmentId]);

  const onReview = useCallback(
    async (action: ReviewAction, body: ReviewBody) => {
      const resp = await postJson(`/api/care/assessments/${encodeURIComponent(assessmentId)}/${action}`, body).catch(
        () => null,
      );
      if (!resp) return "The service is unavailable. Please try again.";
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) return ERROR_TEXT[data.detail] ?? "The review could not be saved.";
      setAssessment(data);
      return null;
    },
    [assessmentId],
  );

  if (error) return <p role="alert">{error}</p>;
  if (!assessment) return <p aria-live="polite">Loading assessment…</p>;
  return <CareReview assessment={assessment} vocabulary={vocab} onReview={onReview} />;
}
