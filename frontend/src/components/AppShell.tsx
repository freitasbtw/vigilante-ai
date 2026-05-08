import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

interface AppShellProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function AppShell({ title, subtitle, actions, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-6 border-b border-border bg-bg-elevated px-8">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight text-text">{title}</h1>
            {subtitle && (
              <p className="truncate text-xs text-text-muted">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
        <main className="min-w-0 flex-1 overflow-x-hidden p-8">{children}</main>
      </div>
    </div>
  );
}
