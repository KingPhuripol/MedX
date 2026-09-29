import DemoLauncher from "@/components/clinical/DemoLauncher";
export const metadata = { title: "รอบเดโม" };
export default function DemoPage() {
  return <DemoLauncher enabled={process.env.DEMO_MODE === "1"} />;
}
