"use client";

import { useEffect, useRef } from "react";

import { PROPOSED_V2C } from "@/lib/copy";

import { Icon } from "./Icon";

/**
 * Bottom sheet on the native <dialog> (focus trap, Escape and focus restore come from the platform).
 * Content is rendered only while open, so a closed sheet adds no text to the screen.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [open]);
  return (
    <dialog ref={ref} className="sheet" aria-labelledby={open ? "sheet-title" : undefined} onClose={onClose} onCancel={onClose}>
      {open && (
        <div className="sheet-body">
          <div className="sheet-head">
            <h2 id="sheet-title" className="t-title">
              {title}
            </h2>
            <button type="button" className="btn btn--ghost" aria-label={PROPOSED_V2C.closeSheet} onClick={onClose}>
              <Icon name="x" />
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}
