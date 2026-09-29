import s from "./primitives.module.css";

export function LoadingState({ label = "กำลังโหลดข้อมูล…", rows = 2 }: { label?: string; rows?: number }) {
  return (
    <div className={s.loading}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={s.bar} aria-hidden="true" />
      ))}
      <p aria-live="polite">{label}</p>
    </div>
  );
}
export default LoadingState;
