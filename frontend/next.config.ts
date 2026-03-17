import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const appBasePath = normalizeBasePath(process.env.APP_BASE_PATH ?? "");
const publicApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? withBasePath(appBasePath, "/api/v1");
const isProd = process.env.NODE_ENV === "production";

function normalizeBasePath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/") return "";

  const withoutTrailingSlash = trimmed.replace(/\/+$/, "");
  return withoutTrailingSlash.startsWith("/") ? withoutTrailingSlash : `/${withoutTrailingSlash}`;
}

function withBasePath(basePath: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!basePath) {
    return normalizedPath;
  }
  if (normalizedPath === "/") {
    return `${basePath}/`;
  }
  return `${basePath}${normalizedPath}`;
}

function toOrigin(value: string): string | null {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

const connectSources = new Set<string>(["'self'"]);
for (const candidate of [
  backendUrl,
  publicApiBaseUrl,
  process.env.NEXT_PUBLIC_APP_URL ?? ""
]) {
  const origin = toOrigin(candidate);
  if (origin) {
    connectSources.add(origin);
  }
}

const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  `connect-src ${Array.from(connectSources).join(" ")}`,
  "font-src 'self' data:",
  "media-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(isProd ? ["upgrade-insecure-requests"] : [])
].join("; ");

const nextConfig: NextConfig = {
  basePath: appBasePath || undefined,
  output: process.env.STANDALONE === "true" ? "standalone" : undefined,
  typedRoutes: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`
      }
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" }
        ]
      }
    ];
  }
};

export default nextConfig;
