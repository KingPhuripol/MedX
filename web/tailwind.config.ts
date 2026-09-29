import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { background:"var(--background)", foreground:"var(--foreground)", card:"var(--card)", border:"var(--border)", muted:"var(--muted)", "muted-foreground":"var(--muted-foreground)", primary:"var(--primary)", critical:"var(--critical)", warning:"var(--warning)", success:"var(--success)" },
    fontFamily: { sans:["SCBXBeta2","system-ui","sans-serif"] }, borderRadius:{lg:"12px",md:"8px"}, boxShadow:{panel:"var(--shadow-panel)"}
  } },
  plugins: [require("tailwindcss-animate")],
};
export default config;
