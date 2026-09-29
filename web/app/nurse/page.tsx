import { redirect } from "next/navigation";

// Role homes land on the shared work queue (docs/UI-SPEC.md); role tools sit in the AppShell navigation.
export default function LegacyNurseHome() {
  redirect("/app/queue");
}
