import type { Metadata } from "next";
import Link from "next/link";

import PageFrame from "@/components/PageFrame";

export const metadata: Metadata = { title: "404" };

export default function NotFound() {
  return (
    <PageFrame
      eyebrow="Not found"
      titleId="not-found-title"
      title="404 — Page not found"
      claim="The page you asked for does not exist."
      next={
        <>
          <em>Return to sign in</em> to start again.
        </>
      }
    >
      <p>
        <Link href="/login">Go to sign in</Link>
      </p>
    </PageFrame>
  );
}
