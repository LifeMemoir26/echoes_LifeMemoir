import { apiPost } from "@/lib/api/client";
import type { LoginData, LoginRequest, RegisterData, RegisterRequest } from "@/lib/api/types";

export async function login(username: string, password: string): Promise<LoginData> {
  return apiPost<LoginData, LoginRequest>("/auth/login", {
    username,
    password
  });
}

export async function register(username: string, password: string): Promise<RegisterData> {
  return apiPost<RegisterData, RegisterRequest>("/auth/register", {
    username,
    password
  });
}
