function normalizeBasePath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/") return "";

  const withoutTrailingSlash = trimmed.replace(/\/+$/, "");
  return withoutTrailingSlash.startsWith("/") ? withoutTrailingSlash : `/${withoutTrailingSlash}`;
}

export const APP_BASE_PATH = normalizeBasePath(process.env.NEXT_PUBLIC_BASE_PATH ?? "");

export function withBasePath(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!APP_BASE_PATH) {
    return normalizedPath;
  }
  if (normalizedPath === "/") {
    return `${APP_BASE_PATH}/`;
  }
  return `${APP_BASE_PATH}${normalizedPath}`;
}

export function stripBasePath(pathname: string): string {
  if (!APP_BASE_PATH || !pathname.startsWith(APP_BASE_PATH)) {
    return pathname || "/";
  }

  const stripped = pathname.slice(APP_BASE_PATH.length);
  if (!stripped) {
    return "/";
  }
  return stripped.startsWith("/") ? stripped : `/${stripped}`;
}
