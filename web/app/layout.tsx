import type { Metadata } from "next";
import type { ReactNode } from "react";

import Disclaimer from "@/components/Disclaimer";

import "./globals.css";

export const metadata: Metadata = {
  title: "Clinical Front Door (research prototype)",
  description: "Research prototype — not for clinical use.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Disclaimer />
        <main>{children}</main>
      </body>
    </html>
  );
}
