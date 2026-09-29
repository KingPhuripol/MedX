import Link from "next/link";

import PageFrame from "@/components/PageFrame";

export default function Forbidden() {
  return (
    <PageFrame
      testId="forbidden"
      eyebrow="Access control"
      titleId="forbidden-title"
      title={<>403 — Not your role&apos;s page</>}
      claim="Each role can open only its own home page."
      next={
        <>
          <em>Sign in with your own role</em> to continue.
        </>
      }
    >
      <p>This page belongs to another role. You can only open your own home page.</p>
      <p>
        <Link href="/login">Go to sign in</Link>
      </p>
    </PageFrame>
  );
}
