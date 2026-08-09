import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Migration Platform",
  description: "Batch 20 executable migration-platform scaffold",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
