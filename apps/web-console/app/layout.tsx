import type { Metadata, Viewport } from "next";
import "./styles.css";
import { AppShell } from "./components/AppShell";
import { AccountSessionProvider } from "./components/AccountSessionProvider";
import { UserActivityCollector } from "./components/UserActivityCollector";
import { UiPreferencesProvider } from "./components/UiPreferencesProvider";

export const metadata: Metadata = {
  title: { default: "ELMOS 控制中心", template: "%s · ELMOS" },
  description: "企业遗留系统现代化与证据控制中心",
  applicationName: "ELMOS",
  robots: { index: false, follow: false, noarchive: true },
};

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1719" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <UiPreferencesProvider>
          <AccountSessionProvider>
            <UserActivityCollector />
            <AppShell>{children}</AppShell>
          </AccountSessionProvider>
        </UiPreferencesProvider>
      </body>
    </html>
  );
}
