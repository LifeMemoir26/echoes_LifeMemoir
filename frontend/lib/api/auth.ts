import { apiPost } from "@/lib/api/client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export interface RegisterResponse {
  username: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse, { username: string; password: string }>("/auth/login", {
    username,
    password
  });
}

export async function register(username: string, password: string): Promise<RegisterResponse> {
  return apiPost<RegisterResponse, { username: string; password: string }>("/auth/register", {
    username,
    password
  });
}
