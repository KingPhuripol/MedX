"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Field } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatThaiTime } from "@/lib/demo";
import { postJson, type CaseItem } from "@/lib/triage";

import css from "./TriageCaseList.module.css";

export default function TriageCaseList() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/triage/cases", { credentials: "same-origin" })
      .then(async (resp) => {
        if (!active) return;
        if (!resp.ok) throw new Error(String(resp.status));
        setCases((await resp.json()).cases);
      })
      .catch(() => active && setError("Could not load the case list."));
    return () => {
      active = false;
    };
  }, []);

  async function assess(item: CaseItem) {
    setBusy(item.case_ref);
    setError(null);
    const resp = await postJson(`/api/triage/cases/${encodeURIComponent(item.case_ref)}/assess`, {
      as_of: item.suggested_as_of,
    }).catch(() => null);
    if (resp && resp.ok) {
      const data = await resp.json();
      router.push(`/nurse/triage/${data.assessment_id}`);
      return;
    }
    setBusy(null);
    setError("The assessment could not be created. Please try again.");
  }

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!cases) return [];
    if (!q) return cases;
    return cases.filter((c) => c.case_ref.toLowerCase().includes(q) || (c.chief_complaint ?? "").toLowerCase().includes(q));
  }, [cases, query]);

  const columns: Column<CaseItem>[] = [
    { key: "ref", header: "Case", render: (c) => <strong>{c.case_ref}</strong> },
    {
      key: "complaint",
      header: "Chief complaint",
      className: css.complaint,
      render: (c) =>
        c.chief_complaint ? <span lang="th">{c.chief_complaint}</span> : <span className={css.muted}>chief complaint not recorded</span>,
    },
    {
      key: "asof",
      header: "Evidence as of",
      render: (c) => <time dateTime={c.suggested_as_of}>{formatThaiTime(c.suggested_as_of)}</time>,
    },
    {
      key: "action",
      header: "Action",
      render: (c) => (
        <Button
          type="button"
          variant="secondary"
          onClick={() => assess(c)}
          disabled={busy !== null}
          aria-label={`Assess ${c.case_ref}`}
        >
          {busy === c.case_ref ? "กำลังประเมิน…" : "Assess"}
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        titleId="cases-title"
        title="Triage cases"
        subtitle="Synthetic fixture cases only. Each assessment gives red-flag alerts and a department suggestion for nurse review. Nothing is sent to a department until a nurse confirms it."
        meta={cases ? <StatusChip tone="info">{cases.length} cases</StatusChip> : undefined}
      />
      {error && (
        <Notice tone="critical" role="alert">
          <p>{error}</p>
        </Notice>
      )}
      <Section aria-label="Case list">
        {!cases && !error && <LoadingState label="กำลังโหลดรายการเคส… (Loading cases)" rows={4} />}
        {cases && (
          <>
            <div className={css.filter}>
              <Field label="ค้นหาเคส / Filter by case or complaint" htmlFor="case-filter">
                <input
                  id="case-filter"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoComplete="off"
                />
              </Field>
              <StatusChip tone="neutral">
                {rows.length}/{cases.length}
              </StatusChip>
            </div>
            <DataTable
              testId="case-list"
              caption="Triage cases"
              columns={columns}
              rows={rows}
              rowKey={(c) => c.case_ref}
              empty={<p className={css.muted}>ไม่พบเคสที่ตรงกับคำค้น</p>}
            />
          </>
        )}
      </Section>
    </div>
  );
}
