import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "8000" },
      { protocol: "https", hostname: "**" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://api:8000/api/:path*`,
      },
      {
        source: "/dashboard/:path+",
        destination: "/:path+",
      },
    ];
  },
};

export default nextConfig;
