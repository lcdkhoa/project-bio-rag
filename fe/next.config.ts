import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const apiHost = process.env.NEXT_PUBLIC_API_HOST || "http://localhost:5000";
    return [
      {
        source: "/images/:path*",
        destination: `${apiHost}/images/:path*`,
      },
    ];
  },
};

export default nextConfig;
