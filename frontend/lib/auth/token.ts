const USERNAME_KEY = "echoes_username";

export function saveSessionUsername(username: string): void {
  localStorage.setItem(USERNAME_KEY, username);
}

export function getSavedUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function clearSavedSession(): void {
  localStorage.removeItem(USERNAME_KEY);
}
