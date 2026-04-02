"use client";

import StatsCards from "@/components/StatsCards";
import ViolationsChart from "@/components/ViolationsChart";
import { useDashboardStats } from "@/hooks/useDashboardStats";

export default function DashboardPage() {
  const { stats } = useDashboardStats();

  return (
    <div className="space-y-6">
      <section className="surface-card p-6 sm:p-7">
        <p className="eyebrow">Resumo</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--foreground)]">
          Dashboard operacional
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted)] sm:text-base">
          Consolide o historico da sessao atual e acompanhe o volume de violacoes ao longo do tempo.
        </p>
      </section>

      <StatsCards stats={stats} />
      <ViolationsChart timeline={stats?.violations_timeline ?? []} />
    </div>
  );
}
