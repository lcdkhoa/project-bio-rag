import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow Colab proxy hosts for HMR
  allowedDevOrigins: [
    "*.colab.dev",
    "*.googleusercontent.com",
    "localhost:3000",
  ],
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
