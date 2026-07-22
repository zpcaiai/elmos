import type { Metadata } from "next";
import "./styles.css";
import { AppShell } from "./components/AppShell";

export const metadata: Metadata = {
  title: { default: "ELMOS 控制中心", template: "%s · ELMOS" },
  description: "企业遗留系统现代化与证据控制中心",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
