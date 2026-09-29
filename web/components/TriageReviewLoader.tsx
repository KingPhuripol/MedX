"use client";

import { useCallback, useEffect, useState } from "react";

import TriageReview from "@/components/TriageReview";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import { ERROR_TEXT, postJson, type Assessment, type Department, type ReviewAction, type ReviewBody } from "@/lib/triage";

export default function TriageReviewLoader({ assessmentId }: { assessmentId: string }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`/api/triage/assessments/${encodeURIComponent(assessmentId)}`, { credentials: "same-origin" }),
      fetch("/api/triage/departments", { credentials: "same-origin" }),
    ])
      .then(async ([a, d]) => {
        if (!active) return;
        if (!a.ok || !d.ok) {
          setError(a.status === 404 ? "Assessment not found." : "Could not load the assessment.");
          return;
        }
        setAssessment(await a.json());
        setDepartments((await d.json()).departments);
      })
      .catch(() => active && setError("The service is unavailable. Please try again."));
    return () => {
      active = false;
    };
  }, [assessmentId]);

  const onReview = useCallback(
    async (action: ReviewAction, body: ReviewBody) => {
      const resp = await postJson(`/api/triage/assessments/${encodeURIComponent(assessmentId)}/${action}`, body).catch(
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

  if (error)
    return (
      <div className="page-stack">
        <Notice tone="critical" role="alert" title="โหลดผลประเมินไม่สำเร็จ">
          <p>{error}</p>
        </Notice>
      </div>
    );
  if (!assessment)
    return (
      <div className="page-stack">
        <LoadingState label="กำลังโหลดผลประเมิน… (Loading assessment)" rows={3} />
      </div>
    );
  return <TriageReview assessment={assessment} departments={departments} onReview={onReview} />;
}
