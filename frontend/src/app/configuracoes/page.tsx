"use client";

import { useEffect, useState } from "react";
import { Mail, Shield, Building, Cpu, type LucideIcon } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { getMe } from "@/lib/api";
import type { User } from "@/types";

export default function ConfiguracoesPage() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => null)
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="Configurações" subtitle="Conta, tenant e integrações da plataforma">
      {loading ? (
        <p className="text-sm text-text-muted">Carregando…</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card p-6">
            <p className="eyebrow">Conta</p>
            <h2 className="mt-1 text-base font-semibold text-text">Dados do usuário</h2>
            <dl className="mt-5 space-y-4">
              <Field icon={Mail} label="Email" value={user?.email ?? "—"} />
              <Field icon={Shield} label="Papel" value={translateRole(user?.role)} />
              <Field icon={Building} label="Tenant" value={user?.tenant_id ?? "—"} mono />
            </dl>
          </section>

          <section className="card p-6">
            <p className="eyebrow">Plataforma</p>
            <h2 className="mt-1 text-base font-semibold text-text">Modelo e processamento</h2>
            <dl className="mt-5 space-y-4">
              <Field icon={Cpu} label="Modelo" value="YOLOv8s · helmet + vest" />
              <Field icon={Cpu} label="Inferência" value="GPU local · ~700 fps" />
            </dl>
            <p className="mt-6 text-xs text-text-muted">
              Configurações avançadas (notificação WhatsApp, regras por câmera, exportação automática) virão na Fase 5
              do projeto.
            </p>
          </section>
        </div>
      )}
    </AppShell>
  );
}

function Field({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-md bg-bg-sunken text-text-muted">
        <Icon size={14} strokeWidth={1.8} />
      </span>
      <div className="min-w-0">
        <dt className="text-xs text-text-muted">{label}</dt>
        <dd className={`text-sm text-text ${mono ? "mono-num" : ""}`}>{value}</dd>
      </div>
    </div>
  );
}

function translateRole(role: string | undefined): string {
  if (!role) return "—";
  const map: Record<string, string> = {
    admin: "Administrador",
    supervisor: "Supervisor",
    viewer: "Visualizador",
  };
  return map[role] ?? role;
}
