import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). Not role="status". */
export function LoadingState({ label = "กำลังโหลดข้อมูล…", rows = 2 }: { label?: string; rows?: number }) {
  return (
    <div className="ui-loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={s.skeleton} aria-hidden="true" />
      ))}
      <p aria-live="polite">{label}</p>
    </div>
  );
}
export default LoadingState;
