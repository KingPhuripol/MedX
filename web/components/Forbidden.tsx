import Link from "next/link";

export default function Forbidden() {
  return (
    <section aria-labelledby="forbidden-title" data-testid="forbidden">
      <h1 id="forbidden-title">403 — Not your role&apos;s page</h1>
      <p>This page belongs to another role. You can only open your own home page.</p>
      <p>
        <Link href="/login">Go to sign in</Link>
      </p>
    </section>
  );
}
