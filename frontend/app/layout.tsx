import type { Metadata } from "next";
import { Cinzel, Cormorant_Garamond, Crimson_Pro } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const heading = Cormorant_Garamond({ subsets: ["latin"], variable: "--font-heading" });
const body = Crimson_Pro({ subsets: ["latin"], variable: "--font-body" });
const display = Cinzel({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Echoes LifeMemoir",
  description: "Memoir reader powered by API v1"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={`${heading.variable} ${body.variable} ${display.variable}`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
