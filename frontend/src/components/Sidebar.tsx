"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Camera, History, BarChart3, Settings, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getMe } from "@/lib/api";
import type { User } from "@/types";

const NAV = [
  { href: "/cameras", label: "Câmeras ao vivo", icon: Camera },
  { href: "/historico", label: "Histórico", icon: History },
  { href: "/relatorios", label: "Relatórios", icon: BarChart3 },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push("/login"));
  }, [router]);

  function logout() {
    clearTokens();
    router.push("/login");
  }

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col bg-bg-sidebar text-text-on-dark">
      {/* Brand */}
      <div className="flex h-16 items-center border-b border-border-on-dark px-6">
        <span className="inline-flex items-center gap-2 text-[17px] font-semibold tracking-tight text-text-on-dark">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-white.webp" alt="Vigilante.AI" width={26} height={27} className="block" />
          <span>Vigilante<span style={{ color: "#f5a623" }}>.AI</span></span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link key={href} href={href} className="sidebar-link" data-active={active}>
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-border-on-dark p-3">
        <div className="flex items-center gap-3 rounded-md px-3 py-2">
          <div className="grid h-8 w-8 place-items-center rounded-full bg-bg-sidebar-elevated text-xs font-semibold uppercase">
            {user?.email?.[0] ?? "?"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-text-on-dark">{user?.email ?? "—"}</div>
            <div className="truncate text-xs text-text-on-dark-subtle">{user?.role ?? ""}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sair"
            className="grid h-8 w-8 place-items-center rounded-md text-text-on-dark-muted transition hover:bg-bg-sidebar-elevated hover:text-text-on-dark"
          >
            <LogOut size={16} strokeWidth={1.8} />
          </button>
        </div>
      </div>
    </aside>
  );
}
