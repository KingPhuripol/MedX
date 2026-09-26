import Link from "next/link";

export default function NotFound() {
  return (
    <section aria-labelledby="not-found-title">
      <h1 id="not-found-title">404 — Page not found</h1>
      <p>
        <Link href="/login">Go to sign in</Link>
      </p>
    </section>
  );
}
