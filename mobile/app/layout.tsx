import type { Metadata, Viewport } from "next";

import { SwRegister } from "@/components/SwRegister";

import "./theme.css";
import "./mobile.css";

export const metadata: Metadata = {
  title: "MedX Scribe",
  description: "บันทึกซักประวัติข้างเตียง · ข้อมูลสังเคราะห์ · ต้นแบบเพื่อการวิจัย",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "MedX Scribe", statusBarStyle: "default" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <body>
        {children}
        <SwRegister />
      </body>
    </html>
  );
}
