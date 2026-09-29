import type { Metadata } from "next";

import RoleGuard from "@/components/RoleGuard";
import VoiceIntake from "@/components/voice/VoiceIntake";

export const metadata: Metadata = { title: "Voice intake" };

export default function NurseIntakePage() {
  return (
    <RoleGuard role="nurse">
      <VoiceIntake />
    </RoleGuard>
  );
}
