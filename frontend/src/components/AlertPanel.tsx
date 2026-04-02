"use client";

import { useState } from "react";
import { Bell, BellOff, Trash2 } from "lucide-react";
import type { Alert } from "@/types";
import { useAlerts } from "@/hooks/useAlerts";
import AlertCard from "./AlertCard";
import AlertDetailsModal from "./AlertDetailsModal";

export default function AlertPanel() {
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const { alerts, clearAllAlerts } = useAlerts(soundEnabled);

  async function handleClear() {
    await clearAllAlerts();
    setSelectedAlert(null);
  }

  return (
    <>
      <div className="surface-card flex h-full flex-col overflow-hidden p-0">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
          <div className="flex items-center gap-3">
            <div>
              <p className="eyebrow">Ocorrencias</p>
              <h3 className="mt-1 text-base font-semibold text-[var(--foreground)]">Alertas recentes</h3>
            </div>
          </div>
          {alerts.length > 0 && (
            <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700">
              {alerts.length}
            </span>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={() => setSoundEnabled((value) => !value)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border)] bg-white/80 text-[var(--muted-strong)] transition hover:border-[var(--border-strong)] hover:text-[var(--foreground)]"
              title={soundEnabled ? "Desativar som" : "Ativar som"}
            >
              {soundEnabled ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
            </button>
            <button
              onClick={handleClear}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white/80 px-4 py-2 text-xs font-semibold text-[var(--muted-strong)] transition hover:border-[var(--border-strong)] hover:text-[var(--foreground)]"
            >
              <Trash2 className="h-4 w-4" />
              Limpar
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {alerts.length === 0 ? (
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-[22px] border border-dashed border-[var(--border)] bg-[var(--panel)] px-6 text-center">
              <p className="text-sm font-medium text-[var(--foreground)]">Nenhum alerta registrado.</p>
              <p className="mt-2 max-w-xs text-sm text-[var(--muted)]">
                Quando houver ausencia de EPI, os eventos mais recentes aparecem aqui com atalho para inspecao detalhada.
              </p>
            </div>
          ) : (
            alerts.map((alert) => (
              <AlertCard key={alert.id} alert={alert} onSelect={setSelectedAlert} />
            ))
          )}
        </div>
      </div>

      <AlertDetailsModal
        alert={selectedAlert}
        open={selectedAlert !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedAlert(null);
          }
        }}
      />
    </>
  );
}
