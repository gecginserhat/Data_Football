import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  transpilePackages: ["@kurgu/ui", "@kurgu/pitch", "@kurgu/api-client"],
  poweredByHeader: false,
  // İçe aktarım dosyaları sunucu eylemiyle API'ye iletilir (API sınırı 20 MB).
  experimental: { serverActions: { bodySizeLimit: "21mb" } },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default withNextIntl(config);
