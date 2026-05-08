"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, BarChart3 } from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

import { AppShell } from "@/components/AppShell";
import { listCameras, listCameraAlerts, getCameraStats, getMe } from "@/lib/api";
import type { Camera, Alert, SessionStats } from "@/types";

interface CameraAggregate {
  camera: Camera;
  alerts: Alert[];
  stats: SessionStats | null;
}

const PERIODS = [
  { value: "7", label: "Últimos 7 dias" },
  { value: "30", label: "Últimos 30 dias" },
  { value: "all", label: "Todo o período" },
] as const;

export default function RelatoriosPage() {
  const [data, setData] = useState<CameraAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<typeof PERIODS[number]["value"]>("30");

  async function load() {
    try {
      await getMe();
      const cameras = await listCameras();
      const results = await Promise.all(
        cameras.map(async (camera) => {
          const [alerts, stats] = await Promise.all([
            listCameraAlerts(camera.id, 1, 500).catch(() => []),
            getCameraStats(camera.id).catch(() => null),
          ]);
          return { camera, alerts, stats };
        }),
      );
      setData(results);
    } catch {
      // noop
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const cutoff = useMemo(() => {
    if (period === "all") return 0;
    const days = parseInt(period, 10);
    return Date.now() - days * 86400_000;
  }, [period]);

  const filteredAlerts = useMemo(() => {
    return data.flatMap((d) =>
      d.alerts
        .filter((a) => new Date(a.timestamp).getTime() >= cutoff)
        .map((a) => ({ ...a, cameraName: d.camera.name })),
    );
  }, [data, cutoff]);

  // KPIs
  const totalAlerts = filteredAlerts.length;
  const activeCameras = data.filter((d) => d.camera.health.online && d.camera.is_running).length;
  const totalCameras = data.length;
  const averageCompliance = useMemo(() => {
    const valid = data.map((d) => d.stats?.compliance_rate ?? null).filter((v): v is number => v !== null);
    if (valid.length === 0) return null;
    return valid.reduce((a, b) => a + b, 0) / valid.length;
  }, [data]);
  const totalViolations = useMemo(
    () => data.reduce((acc, d) => acc + (d.stats?.total_violations ?? 0), 0),
    [data],
  );

  // Bar chart: alerts per day
  const alertsByDay = useMemo(() => {
    const map = new Map<string, number>();
    const days = period === "all" ? 30 : parseInt(period, 10);
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      map.set(key, 0);
    }
    for (const a of filteredAlerts) {
      const key = new Date(a.timestamp).toISOString().slice(0, 10);
      if (map.has(key)) map.set(key, (map.get(key) ?? 0) + 1);
    }
    return Array.from(map.entries()).map(([key, count]) => ({
      day: key.slice(8, 10) + "/" + key.slice(5, 7),
      count,
    }));
  }, [filteredAlerts, period]);

  // Distribution by violation type
  const distribution = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of filteredAlerts) {
      map.set(a.violation_type, (map.get(a.violation_type) ?? 0) + 1);
    }
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [filteredAlerts]);

  // Top cameras
  const topCameras = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of filteredAlerts) {
      map.set(a.cameraName, (map.get(a.cameraName) ?? 0) + 1);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [filteredAlerts]);

  return (
    <AppShell
      title="Relatórios e indicadores"
      subtitle={`Visão consolidada · ${PERIODS.find((p) => p.value === period)?.label.toLowerCase()}`}
      actions={
        <>
          <select value={period} onChange={(e) => setPeriod(e.target.value as typeof PERIODS[number]["value"])} className="input">
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <button type="button" className="btn-secondary text-sm" disabled>
            <Download size={14} strokeWidth={1.8} />
            Exportar PDF
          </button>
        </>
      }
    >
      {loading ? (
        <p className="text-sm text-text-muted">Carregando relatórios…</p>
      ) : (
        <div className="space-y-6">
          {/* KPI cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPI label="Total de alertas" value={totalAlerts.toString()} />
            <KPI
              label="Conformidade média"
              value={averageCompliance !== null ? `${formatRate(averageCompliance)}%` : "—"}
            />
            <KPI label="Violações registradas" value={totalViolations.toString()} />
            <KPI label="Câmeras ativas" value={`${activeCameras}/${totalCameras}`} />
          </div>

          {/* Bar chart */}
          <div className="card p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="eyebrow">Atividade</p>
                <h3 className="mt-1 text-base font-semibold text-text">Alertas por dia</h3>
              </div>
              <BarChart3 size={18} className="text-text-muted" />
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={alertsByDay} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e8e7e4" vertical={false} />
                <XAxis dataKey="day" stroke="#8a8a8a" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#8a8a8a" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(17,17,17,0.04)" }}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    border: "1px solid #e8e7e4",
                    borderRadius: 10,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="count" fill="#111111" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Distribution + ranking */}
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card p-5">
              <p className="eyebrow">Distribuição</p>
              <h3 className="mt-1 text-base font-semibold text-text">Por tipo de violação</h3>
              <ul className="mt-4 space-y-2">
                {distribution.length === 0 ? (
                  <li className="py-4 text-center text-sm text-text-muted">Sem dados.</li>
                ) : (
                  distribution.map(([type, count]) => {
                    const pct = totalAlerts > 0 ? Math.round((count / totalAlerts) * 100) : 0;
                    return (
                      <li key={type}>
                        <div className="mb-1 flex items-center justify-between text-sm">
                          <span className="text-text">{type}</span>
                          <span className="text-text-muted mono-num">
                            {count} ({pct}%)
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-bg-sunken">
                          <div className="h-full bg-text" style={{ width: `${pct}%` }} />
                        </div>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>

            <div className="card p-5">
              <p className="eyebrow">Ranking</p>
              <h3 className="mt-1 text-base font-semibold text-text">Câmeras com mais ocorrências</h3>
              <ul className="mt-4 space-y-2">
                {topCameras.length === 0 ? (
                  <li className="py-4 text-center text-sm text-text-muted">Sem dados.</li>
                ) : (
                  topCameras.map(([name, count]) => {
                    const max = topCameras[0][1];
                    const pct = max > 0 ? Math.round((count / max) * 100) : 0;
                    return (
                      <li key={name}>
                        <div className="mb-1 flex items-center justify-between text-sm">
                          <span className="truncate text-text">{name}</span>
                          <span className="text-text-muted mono-num">{count}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-bg-sunken">
                          <div className="h-full bg-text" style={{ width: `${pct}%` }} />
                        </div>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

function formatRate(v: number): string {
  const pct = v <= 1 ? v * 100 : v;
  return Math.max(0, Math.min(100, pct)).toFixed(0);
}

function KPI({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-5">
      <p className="eyebrow">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-text mono-num">{value}</p>
    </div>
  );
}
