/** LocalStorage keys */
const TOKEN_KEY = "echoes_access_token";
const USERNAME_KEY = "echoes_username";

export function saveToken(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getSavedUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

/**
 * Decode the JWT payload (middle segment) and check the `exp` claim.
 * Does NOT verify the signature — server is the authority.
 */
export function isTokenExpired(token: string): boolean {
  try {
    const segment = token.split(".")[1];
    if (!segment) return true;
    // base64url → base64
    const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64)) as Record<string, unknown>;
    const exp = payload.exp;
    if (typeof exp !== "number") return false;
    return Date.now() / 1000 > exp;
  } catch {
    return true;
  }
}
