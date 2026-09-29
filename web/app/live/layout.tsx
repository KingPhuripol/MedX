import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "@/components/live/live.css";

// The manifest carries the theme colour: hex literals are only allowed in theme.css (and the manifest is data).
export const metadata: Metadata = {
  title: "MedX Live",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "MedX Live", statusBarStyle: "black-translucent" },
  icons: { apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function LiveLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
