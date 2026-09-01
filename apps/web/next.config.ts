import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@linerfy/domain", "@linerfy/ui"],
};

export default nextConfig;
