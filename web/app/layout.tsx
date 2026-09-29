import type { Metadata } from "next";
import type { ReactNode } from "react";

import Disclaimer from "@/components/Disclaimer";
import Wordmark from "@/components/Wordmark";

import "./theme.css";
import "./globals.css";

const SITE_TITLE = "MedX — AI Clinical Front Door (research prototype)";

export const metadata: Metadata = {
  title: { template: `%s · ${SITE_TITLE}`, default: SITE_TITLE },
  description: "Research prototype — not for clinical use.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th">
      <body>
        <Disclaimer />
        <header className="site-header"><Wordmark /></header>
        <main>{children}</main>
      </body>
    </html>
  );
}
