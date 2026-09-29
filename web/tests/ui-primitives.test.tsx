import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionBar } from "@/components/ui/ActionBar";
import { DataTable } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";

describe("U5 layout primitives (AUDIT section 6.2)", () => {
  it("PageHeader renders one h1 with subtitle, meta and actions", () => {
    render(<PageHeader title="Title" titleId="t" subtitle="Sub" meta={<span>meta</span>} actions={<button>Go</button>} testId="ph" />);
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toHaveAttribute("id", "t");
    expect(screen.getByTestId("ph")).toHaveClass("ui-page-header");
    expect(screen.getByText("Sub")).toHaveClass("muted");
    expect(screen.getByText("meta")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });

  it("Section labels itself with its h2 and passes through role and test id", () => {
    render(
      <Section title="Alerts" titleId="a" tone="critical" role="alert" data-testid="sec">
        body
      </Section>,
    );
    const sec = screen.getByTestId("sec");
    expect(sec).toHaveClass("ui-section--critical");
    expect(sec).toHaveAttribute("aria-labelledby", "a");
    expect(sec).toHaveAttribute("role", "alert");
    expect(within(sec).getByRole("heading", { level: 2, name: "Alerts" })).toHaveAttribute("id", "a");
  });

  it("StatusChip shows text with a tone class and never has role=status", () => {
    render(<StatusChip tone="warning" icon={<i />}>ต้องตรวจทาน</StatusChip>);
    const chip = screen.getByText("ต้องตรวจทาน");
    expect(chip).toHaveClass("ui-chip", "ui-chip--warning");
    expect(chip).not.toHaveAttribute("role");
  });

  it("Notice has no default role and passes role through", () => {
    const { rerender } = render(<Notice tone="info" title="T" data-testid="n">x</Notice>);
    expect(screen.getByTestId("n")).not.toHaveAttribute("role");
    rerender(<Notice tone="critical" role="alert" data-testid="n">x</Notice>);
    expect(screen.getByRole("alert")).toHaveClass("ui-notice--critical");
  });

  it("EmptyState uses h2 by default and h1 on request, with a next-step action", () => {
    const { rerender } = render(<EmptyState title="Empty" action={<a href="/x">Next</a>} />);
    expect(screen.getByRole("heading", { level: 2, name: "Empty" })).toBeInTheDocument();
    rerender(<EmptyState title="Gone" headingLevel={1} />);
    expect(screen.getByRole("heading", { level: 1, name: "Gone" })).toBeInTheDocument();
  });

  it("LoadingState shows a polite label and no status role", () => {
    const { container } = render(<LoadingState label="กำลังโหลด" rows={3} />);
    expect(container.querySelectorAll(".skeleton")).toHaveLength(3);
    expect(screen.getByText("กำลังโหลด")).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("DataTable renders columns, data-label cells, test id and the empty slot", () => {
    const cols = [
      { key: "a", header: "Case", render: (r: { id: string }) => r.id },
      { key: "b", header: <b>Act</b>, render: () => "go" },
    ];
    const { rerender } = render(<DataTable columns={cols} rows={[{ id: "C1" }]} rowKey={(r) => r.id} testId="tbl" />);
    const table = screen.getByTestId("tbl");
    expect(table).toHaveClass("ui-table");
    expect(within(table).getByRole("columnheader", { name: "Case" })).toBeInTheDocument();
    expect(within(table).getByText("C1")).toHaveAttribute("data-label", "Case");
    rerender(<DataTable columns={cols} rows={[]} rowKey={(r: { id: string }) => r.id} empty={<p>none</p>} />);
    expect(screen.getByText("none")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("ActionBar shows summary and actions", () => {
    render(
      <ActionBar summary="k/n">
        <button>Confirm</button>
      </ActionBar>,
    );
    expect(screen.getByText("k/n")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" }).closest(".ui-action-bar")).not.toBeNull();
  });

  it("Field wires label, hint and error to the control", () => {
    render(
      <Field label="Name" htmlFor="nm" hint="hint" error="bad">
        <input id="nm" />
      </Field>,
    );
    expect(screen.getByLabelText("Name")).toHaveAttribute("id", "nm");
    expect(screen.getByText("hint")).toHaveAttribute("id", "nm-hint");
    expect(screen.getByRole("alert")).toHaveTextContent("bad");
  });
});
