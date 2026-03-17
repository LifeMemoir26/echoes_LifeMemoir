import { apiGet, apiPost } from "@/lib/api/client";
import type { AuthSessionData, LoginData, LoginRequest, LogoutData, RegisterData, RegisterRequest } from "@/lib/api/types";

export async function login(username: string, password: string): Promise<LoginData> {
  return apiPost<LoginData, LoginRequest>("/auth/login", {
    username,
    password
  });
}

export async function getAuthSession(): Promise<AuthSessionData> {
  return apiGet<AuthSessionData>("/auth/me");
}

export async function logoutSession(): Promise<LogoutData> {
  return apiPost<LogoutData, Record<string, never>>("/auth/logout", {});
}

export async function register(username: string, password: string): Promise<RegisterData> {
  return apiPost<RegisterData, RegisterRequest>("/auth/register", {
    username,
    password
  });
}
