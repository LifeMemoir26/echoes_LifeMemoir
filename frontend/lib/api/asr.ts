import { apiGet } from "@/lib/api/client";

export type AsrSignData = {
  url: string;
  appid: string;
  expires_at: number;
};

export async function getAsrSignedUrl(): Promise<AsrSignData> {
  return apiGet<AsrSignData>("/asr/sign");
}
