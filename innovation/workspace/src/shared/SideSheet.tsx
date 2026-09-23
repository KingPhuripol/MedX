import React, { useEffect, useRef } from "react";
import { Icon } from "./ui/Icon";

export function SideSheet({ title, description, onClose, children }: {
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = panel.current;
    const focusable = () => Array.from(root?.querySelectorAll<HTMLElement>('button:not(.sheet-backdrop):not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || []);
    focusable()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); returnFocus.current?.focus(); };
  }, []);

  return <div className="sheet-layer"><button className="sheet-backdrop" aria-label="ปิดแผงแก้ไข" onClick={onClose} /><div ref={panel} className="side-sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"><header><div><span className="eyebrow">ตรวจและบันทึก</span><h2 id="sheet-title">{title}</h2>{description ? <p>{description}</p> : null}</div><button className="button button--icon" aria-label="ปิด" onClick={onClose}><Icon name="close" /></button></header><div className="side-sheet__body">{children}</div></div></div>;
}
