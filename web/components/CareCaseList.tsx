"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/ui/DataTable";
import Field from "@/components/ui/Field";
import LoadingState from "@/components/ui/LoadingState";
import Notice from "@/components/ui/Notice";
import PageHeader from "@/components/ui/PageHeader";
import Section from "@/components/ui/Section";
import { formatThaiTime } from "@/lib/demo";
import { OUTPUT_LABEL, postJson, type CaseItem } from "@/lib/care";

import styles from "./CareCaseList.module.css";

const DECISION_POINTS = ["T1", "T2"] as const;

export default function CareCaseList() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/care/cases", { credentials: "same-origin" })
      .then(async (resp) => {
        if (!active) return;
        if (resp.status === 503)
          throw new Error("The synthetic dataset is missing. Run make data.");
        if (!resp.ok) throw new Error("Could not load the case list.");
        setCases((await resp.json()).cases);
      })
      .catch(
        (e: Error) =>
          active && setError(e.message || "Could not load the case list."),
      );
    return () => {
      active = false;
    };
  }, []);

  async function assess(caseId: string, dp: string) {
    setBusy(`${caseId}:${dp}`);
    setError(null);
    const resp = await postJson(
      `/api/care/cases/${encodeURIComponent(caseId)}/assess`,
      { decision_point: dp },
    ).catch(() => null);
    if (resp && resp.ok) {
      const data = await resp.json();
      router.push(`/physician/care/${data.assessment_id}`);
      return;
    }
    setBusy(null);
    setError("The assessment could not be created. Please try again.");
  }

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (cases ?? []).filter(
      (c) => !q || c.case_id.toLowerCase().includes(q),
    );
  }, [cases, query]);

  const dpColumns = DECISION_POINTS.map((dp) => ({
    key: dp,
    header: dp,
    className: styles.dp,
    render: (c: CaseItem) => {
      const d = c.decision_points.find((x) => x.decision_point === dp);
      if (!d) return <span className="muted">—</span>;
      const key = `${c.case_id}:${dp}`;
      return (
        <Button
          type="button"
          variant="secondary"
          onClick={() => assess(c.case_id, dp)}
          disabled={busy !== null}
          aria-label={`Assess ${c.case_id} at ${dp}`}
        >
          {busy === key
            ? "กำลังประเมิน…"
            : `${dp} · ${formatThaiTime(d.as_of)}`}
        </Button>
      );
    },
  }));

  return (
    <section aria-labelledby="care-cases-title" className="page-stack">
      <PageHeader
        titleId="care-cases-title"
        title="Care suggestion cases"
        subtitle={
          <>
            <strong>{OUTPUT_LABEL}.</strong> Synthetic development-split cases
            only. Each assessment shows red-flag alerts and screening status
            first, then a case summary, information to collect next and
            care-pathway options to consider. Nothing affects care until a
            physician confirms it.
          </>
        }
        meta={cases ? <span>{cases.length} cases</span> : undefined}
      />
      {error && (
        <Notice tone="critical" role="alert">
          {error}
        </Notice>
      )}
      {!cases && !error && <LoadingState label="Loading cases…" />}
      {cases && (
        <Section title="Cases" titleId="cases-title">
          <div className={styles.stack}>
            <div className={styles.filter}>
              <Field
                label="Filter by case id · ค้นหารหัสเคส"
                htmlFor="case-filter"
              >
                <input
                  id="case-filter"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoComplete="off"
                />
              </Field>
            </div>
            <DataTable
              testId="care-case-list"
              rows={shown}
              rowKey={(c) => c.case_id}
              empty="No case matches this filter."
              columns={[
                {
                  key: "case",
                  header: "Case",
                  render: (c) => <strong>{c.case_id}</strong>,
                },
                ...dpColumns,
              ]}
            />
          </div>
        </Section>
      )}
    </section>
  );
}
