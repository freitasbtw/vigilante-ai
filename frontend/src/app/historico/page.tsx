"use client";

import { useEffect, useMemo, useState } from "react";
import { Filter, ShieldAlert } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import AlertDetailsModal from "@/components/AlertDetailsModal";
import { listCameraAlerts, listCameras, getMe } from "@/lib/api";
import type { Alert, Camera } from "@/types";

interface AlertWithCamera extends Alert {
  cameraId: string;
  cameraName: string;
}

const PERIODS = [
  { value: "today", label: "Hoje" },
  { value: "7d", label: "Últimos 7 dias" },
  { value: "30d", label: "Últimos 30 dias" },
  { value: "all", label: "Todos" },
] as const;

export default function HistoricoPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [allAlerts, setAllAlerts] = useState<AlertWithCamera[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<typeof PERIODS[number]["value"]>("7d");
  const [cameraFilter, setCameraFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selected, setSelected] = useState<Alert | null>(null);

  async function load() {
    try {
      await getMe();
      const list = await listCameras();
      setCameras(list);
      const results = await Promise.all(
        list.map((c) =>
          listCameraAlerts(c.id, 1, 200)
            .then((alerts) => alerts.map((a) => ({ ...a, cameraId: c.id, cameraName: c.name })))
            .catch(() => [] as AlertWithCamera[]),
        ),
      );
      setAllAlerts(results.flat());
    } catch {
      // noop
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  const filtered = useMemo(() => {
    const now = Date.now();
    const cutoff =
      period === "today"
        ? new Date(new Date().setHours(0, 0, 0, 0)).getTime()
        : period === "7d"
          ? now - 7 * 86400_000
          : period === "30d"
            ? now - 30 * 86400_000
            : 0;
    return allAlerts
      .filter((a) => new Date(a.timestamp).getTime() >= cutoff)
      .filter((a) => cameraFilter === "all" || a.cameraId === cameraFilter)
      .filter((a) => typeFilter === "all" || a.violation_type === typeFilter)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [allAlerts, period, cameraFilter, typeFilter]);

  const types = useMemo(
    () => Array.from(new Set(allAlerts.map((a) => a.violation_type))),
    [allAlerts],
  );

  return (
    <AppShell
      title="Histórico de alertas"
      subtitle={`${filtered.length} alertas no período · ${cameras.length} câmeras monitoradas`}
    >
      <div className="card mb-6 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <label className="label">Período</label>
            <select value={period} onChange={(e) => setPeriod(e.target.value as typeof PERIODS[number]["value"])} className="input">
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="label">Câmera</label>
            <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)} className="input">
              <option value="all">Todas</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="label">Tipo de violação</label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="input">
              <option value="all">Todos</option>
              {types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={load}
            className="btn-secondary ml-auto text-sm"
            aria-label="Atualizar lista"
          >
            <Filter size={14} strokeWidth={1.8} />
            Atualizar
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-text-muted">Carregando histórico…</p>
      ) : filtered.length === 0 ? (
        <div className="card flex flex-col items-center gap-2 px-6 py-16 text-center">
          <ShieldAlert size={28} className="text-text-muted" />
          <p className="text-sm font-medium text-text">Nenhum alerta no período selecionado.</p>
          <p className="text-xs text-text-muted">Ajuste o filtro ou aguarde novas detecções.</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="table">
            <thead>
              <tr>
                <th>Data/Hora</th>
                <th>Câmera</th>
                <th>Tipo</th>
                <th>Confiança</th>
                <th>Frame</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((alert) => {
                const date = new Date(alert.timestamp);
                return (
                  <tr key={alert.id} onClick={() => setSelected(alert)} className="cursor-pointer">
                    <td className="mono-num text-xs">
                      {date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" })}
                    </td>
                    <td className="font-medium">{alert.cameraName}</td>
                    <td>{alert.violation_type}</td>
                    <td className="mono-num">{Math.round(alert.confidence * 100)}%</td>
                    <td>
                      {alert.frame_thumbnail ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={`data:image/jpeg;base64,${alert.frame_thumbnail}`}
                          alt="thumb"
                          className="h-8 w-12 rounded object-cover"
                        />
                      ) : (
                        <span className="text-xs text-text-subtle">—</span>
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn-ghost text-xs">
                        Ver detalhes
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <AlertDetailsModal alert={selected} onClose={() => setSelected(null)} />
      )}
    </AppShell>
  );
}
