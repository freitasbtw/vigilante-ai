import type { ReactNode } from "react";
import Link from "next/link";

interface MarketingShellProps {
  children: ReactNode;
}

export function MarketingShell({ children }: MarketingShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-30 border-b border-border bg-bg-elevated/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-[18px] font-semibold tracking-tight text-text"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo-black.webp" alt="Vigilante.AI" width={28} height={29} className="block" />
            <span>Vigilante<span style={{ color: "#f5a623" }}>.AI</span></span>
          </Link>
          <nav className="hidden items-center gap-1 text-[15px] font-medium md:flex">
            <Link href="/" className="rounded-md px-3 py-1.5 text-text-muted transition hover:bg-bg-sunken hover:text-text">
              Início
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="btn-ghost text-[15px]">
              Entrar
            </Link>
            <Link href="/login?mode=register" className="btn-primary text-[15px]">
              Criar conta
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-border bg-bg-elevated">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-2 text-[16px] font-semibold tracking-tight text-text">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo-black.webp" alt="Vigilante.AI" width={24} height={25} className="block" />
              <span>Vigilante<span style={{ color: "#f5a623" }}>.AI</span></span>
            </span>
            <span className="text-sm text-text-muted">© 2026</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-text-muted">
            <a
              href="https://github.com/badmuriss/vigilante-ai"
              target="_blank"
              rel="noreferrer"
              className="transition hover:text-text"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
