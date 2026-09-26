/** Browser calls same-origin /api/*; Next proxies to the FastAPI backend (127.0.0.1 only). */
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
