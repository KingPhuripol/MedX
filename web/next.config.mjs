/** Browser calls same-origin /api/*; Next proxies to the FastAPI backend (127.0.0.1 only). */
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Keep the dev overlay button out of keyboard focus order and screenshots.
  devIndicators: false,
  async rewrites() {
    // Slice d1: on Vercel, /api/* goes to the FastAPI Python function api/index.py, which sees the original
    // path (Vercel Next.js + FastAPI template pattern). Locally it stays the 127.0.0.1 backend.
    const destination = process.env.VERCEL === "1" ? "/api/" : `${API_ORIGIN}/api/:path*`;
    return [{ source: "/api/:path*", destination }];
  },
};

export default nextConfig;
