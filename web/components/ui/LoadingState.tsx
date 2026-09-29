/** Skeleton bars plus a polite live label. Not role="status" (tests query that role in strict mode). */
export function LoadingState({ label = "กำลังโหลดข้อมูล…", rows = 2 }: { label?: string; rows?: number }) {
  return (
    <div className="ui-loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton" key={i} aria-hidden="true" />
      ))}
      <p aria-live="polite" className="muted">
        {label}
      </p>
    </div>
  );
}
export default LoadingState;
