import type { Metadata } from "next";

import RoleGuard from "@/components/RoleGuard";
import VoiceIntake from "@/components/voice/VoiceIntake";

export const metadata: Metadata = { title: "Voice intake — Clinical Front Door (research prototype)" };

export default function NurseIntakePage() {
  return (
    <RoleGuard role="nurse">
      <VoiceIntake />
    </RoleGuard>
  );
}
