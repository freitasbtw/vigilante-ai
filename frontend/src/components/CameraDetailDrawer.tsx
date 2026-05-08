"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X, MapPin, ShieldAlert, Loader2, CameraOff, Activity, Pipette, Plus, Check, ThumbsDown } from "lucide-react";
import { useEffect, useState } from "react";
import type { Camera, Alert, SessionStats, EPIConfig, User } from "@/types";
import {
  listCameraAlerts,
  getCameraStats,
  getCameraEPIConfig,
  updateCameraEPIConfig,
  getCameraColorConfig,
  updateCameraColorConfig,
  setAlertFeedback,
  getMe,
  type CameraColorConfig,
} from "@/lib/api";
import { useLiveFrame } from "@/lib/useLiveFrame";

interface CameraDetailDrawerProps {
  camera: Camera | null;
  onClose: () => void;
}

const REVIEWER_ROLES: User["role"][] = ["admin", "supervisor"];

export function CameraDetailDrawer({ camera, onClose }: CameraDetailDrawerProps) {
  const open = camera !== null;
  const isOnline = camera?.health.online && camera.is_running;
  const frame = useLiveFrame(camera?.id ?? null, 250, !!isOnline);

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [pendingAlerts, setPendingAlerts] = useState<Alert[]>([]);
  const [tab, setTab] = useState<"confirmed" | "pending">("confirmed");
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [epiConfig, setEpiConfig] = useState<EPIConfig | null>(null);
  const [colorConfig, setColorConfig] = useState<CameraColorConfig | null>(null);
  const [savingColors, setSavingColors] = useState(false);
  const [zoomedAlert, setZoomedAlert] = useState<Alert | null>(null);
  const [role, setRole] = useState<User["role"] | null>(null);
  const isReviewer = role !== null && REVIEWER_ROLES.includes(role);

  useEffect(() => {
    if (!camera) return;
    let cancelled = false;
    async function load() {
      if (!camera) return;
      try {
        const meRes = role ? null : await getMe().catch(() => null);
        if (meRes && !cancelled) setRole(meRes.role);
        const reviewer =
          (meRes?.role ?? role) !== null &&
          REVIEWER_ROLES.includes((meRes?.role ?? role) as User["role"]);
        const [a, p, s, e, c] = await Promise.all([
          listCameraAlerts(camera.id, 1, 20, "confirmed").catch(() => []),
          reviewer
            ? listCameraAlerts(camera.id, 1, 20, "pending").catch(() => [])
            : Promise.resolve([]),
          getCameraStats(camera.id).catch(() => null),
          getCameraEPIConfig(camera.id).catch(() => null),
          getCameraColorConfig(camera.id).catch(() => null),
        ]);
        if (!cancelled) {
          setAlerts(a);
          setPendingAlerts(p);
          setStats(s);
          setEpiConfig(e);
          if (c) setColorConfig(c);
        }
      } catch {
        /* noop */
      }
    }
    void load();
    const id = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [camera, role]);

  async function reviewAlert(
    alertId: string,
    decision: "correct" | "false_positive",
  ) {
    try {
      const updated = await setAlertFeedback(alertId, decision);
      setPendingAlerts((prev) => prev.filter((a) => a.id !== alertId));
      if (decision === "correct") {
        setAlerts((prev) => [updated, ...prev]);
      }
      if (zoomedAlert?.id === alertId) setZoomedAlert(updated);
    } catch {
      /* noop */
    }
  }

  async function toggleEpi(key: string) {
    if (!epiConfig || !camera) return;
    const active = new Set(epiConfig.epis.filter((e) => e.active).map((e) => e.key));
    if (active.has(key)) active.delete(key);
    else active.add(key);
    const updated = await updateCameraEPIConfig(camera.id, Array.from(active));
    setEpiConfig(updated);
  }

  async function toggleColor(slot: "capacete" | "colete", value: string) {
    if (!colorConfig || !camera) return;
    const cap = new Set(colorConfig.capacete);
    const vest = new Set(colorConfig.colete);
    const target = slot === "capacete" ? cap : vest;
    if (target.has(value)) target.delete(value);
    else target.add(value);
    setSavingColors(true);
    try {
      const updated = await updateCameraColorConfig(
        camera.id,
        Array.from(cap),
        Array.from(vest),
      );
      setColorConfig(updated);
    } finally {
      setSavingColors(false);
    }
  }

  async function addCustomColor(slot: "capacete" | "colete", hex: string) {
    if (!colorConfig || !camera) return;
    const normalized = hex.toLowerCase();
    const cap = new Set(colorConfig.capacete);
    const vest = new Set(colorConfig.colete);
    const target = slot === "capacete" ? cap : vest;
    if (target.has(normalized)) return;
    target.add(normalized);
    setSavingColors(true);
    try {
      const updated = await updateCameraColorConfig(
        camera.id,
        Array.from(cap),
        Array.from(vest),
      );
      setColorConfig(updated);
    } finally {
      setSavingColors(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-bg-sidebar/95 data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className="fixed inset-0 z-50 flex flex-col bg-bg-sidebar text-text-on-dark outline-none data-[state=open]:animate-fade-in"
          onInteractOutside={(e) => {
            // Toasts and EyeDropper popups live outside the dialog tree.
            // Prevent Radix from auto-closing the drawer when the user
            // clicks them.
            e.preventDefault();
          }}
        >
          {/* Top bar */}
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-on-dark bg-bg-sidebar px-6">
            <div className="flex items-center gap-4">
              <Dialog.Close
                aria-label="Voltar"
                className="grid h-9 w-9 place-items-center rounded-md text-text-on-dark-muted transition hover:bg-bg-sidebar-elevated hover:text-text-on-dark"
              >
                <X size={18} strokeWidth={1.8} />
              </Dialog.Close>
              <div className="min-w-0">
                <Dialog.Title className="truncate text-sm font-semibold text-text-on-dark">
                  {camera?.name ?? "Câmera"}
                </Dialog.Title>
                {camera?.location && (
                  <Dialog.Description className="inline-flex items-center gap-1 text-xs text-text-on-dark-muted">
                    <MapPin size={11} strokeWidth={1.8} />
                    {camera.location}
                  </Dialog.Description>
                )}
              </div>
            </div>

            {isOnline && (
              <div className="inline-flex items-center gap-1.5 rounded-full bg-bg-sidebar-elevated px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-text-on-dark">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
                Ao vivo
              </div>
            )}
          </header>

          {/* Body: feed center + side panel */}
          <div className="flex min-h-0 flex-1 overflow-hidden">
            {/* Feed area — centered with max-width, KPIs below */}
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex flex-1 items-center justify-center bg-black p-3">
                {!camera?.is_running ? (
                  <div className="flex flex-col items-center gap-3 text-text-on-dark-muted">
                    <CameraOff size={48} strokeWidth={1.4} />
                    <span className="text-sm">Câmera parada</span>
                  </div>
                ) : !frame.src ? (
                  <div className="flex items-center gap-2 text-text-on-dark-muted">
                    <Loader2 size={20} className="animate-spin" />
                    <span className="text-sm">Carregando feed…</span>
                  </div>
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={frame.src}
                    alt="Feed ao vivo"
                    className="h-full w-full rounded-md border border-border-on-dark object-contain shadow-overlay"
                  />
                )}
              </div>

              {/* KPI strip below the feed */}
              {stats && (
                <div className="flex shrink-0 items-stretch border-t border-border-on-dark bg-bg-sidebar-elevated">
                  <KPI label="Compliance" value={`${formatRate(stats.compliance_rate)}%`} />
                  <KPI label="Violações" value={stats.total_violations.toString()} />
                  <KPI label="Sessão" value={formatDuration(stats.session_duration_seconds)} />
                  <KPI label="Reconexões" value={camera?.health.reconnect_count.toString() ?? "0"} />
                </div>
              )}
            </div>

            {/* Side panel */}
            <aside className="flex w-80 shrink-0 flex-col border-l border-border-on-dark bg-bg-sidebar">
              {epiConfig && (
                <section className="border-b border-border-on-dark px-5 py-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-text-on-dark-muted">
                    EPIs fiscalizados
                  </p>
                  <div className="mt-3 space-y-1.5">
                    {epiConfig.epis.map((epi) => (
                      <label
                        key={epi.key}
                        className="flex cursor-pointer items-center justify-between rounded-md px-2.5 py-2 text-sm text-text-on-dark transition hover:bg-bg-sidebar-elevated"
                      >
                        <span>{epi.label}</span>
                        <input
                          type="checkbox"
                          checked={epi.active}
                          onChange={() => toggleEpi(epi.key)}
                          className="h-4 w-4 cursor-pointer accent-white"
                        />
                      </label>
                    ))}
                  </div>
                </section>
              )}

              {colorConfig && (
                <ColorPaletteSection
                  config={colorConfig}
                  saving={savingColors}
                  onToggle={toggleColor}
                  onAddCustom={addCustomColor}
                />
              )}

              <section className="flex min-h-0 flex-1 flex-col">
                <div className="flex items-center border-b border-border-on-dark">
                  <button
                    type="button"
                    onClick={() => setTab("confirmed")}
                    className={
                      "flex flex-1 items-center justify-center gap-2 px-4 py-3 text-[11px] font-semibold uppercase tracking-wider transition " +
                      (tab === "confirmed"
                        ? "border-b-2 border-text-on-dark text-text-on-dark"
                        : "text-text-on-dark-muted hover:text-text-on-dark")
                    }
                  >
                    <ShieldAlert size={12} strokeWidth={2} />
                    Confirmados
                    <span className="text-text-on-dark-subtle mono-num">
                      {alerts.length}
                    </span>
                  </button>
                  {isReviewer && (
                    <button
                      type="button"
                      onClick={() => setTab("pending")}
                      className={
                        "flex flex-1 items-center justify-center gap-2 px-4 py-3 text-[11px] font-semibold uppercase tracking-wider transition " +
                        (tab === "pending"
                          ? "border-b-2 border-amber-400 text-text-on-dark"
                          : "text-text-on-dark-muted hover:text-text-on-dark")
                      }
                    >
                      Pendentes
                      <span
                        className={
                          "rounded-full px-1.5 py-0.5 text-[10px] mono-num " +
                          (pendingAlerts.length > 0
                            ? "bg-amber-500/20 text-amber-300"
                            : "text-text-on-dark-subtle")
                        }
                      >
                        {pendingAlerts.length}
                      </span>
                    </button>
                  )}
                </div>
                <div className="flex-1 space-y-1.5 overflow-y-auto p-3">
                  {tab === "confirmed" ? (
                    alerts.length === 0 ? (
                      <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-text-on-dark-muted">
                        <Activity size={20} />
                        <p className="text-xs">
                          Nenhum incidente confirmado ainda.
                        </p>
                      </div>
                    ) : (
                      alerts.map((alert) => (
                        <SideAlertRow
                          key={alert.id}
                          alert={alert}
                          onClick={() => setZoomedAlert(alert)}
                        />
                      ))
                    )
                  ) : pendingAlerts.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-text-on-dark-muted">
                      <Activity size={20} />
                      <p className="text-xs">
                        Nada pra revisar agora.
                      </p>
                    </div>
                  ) : (
                    pendingAlerts.map((alert) => (
                      <PendingAlertRow
                        key={alert.id}
                        alert={alert}
                        onZoom={() => setZoomedAlert(alert)}
                        onConfirm={() => reviewAlert(alert.id, "correct")}
                        onReject={() => reviewAlert(alert.id, "false_positive")}
                      />
                    ))
                  )}
                </div>
              </section>
            </aside>
          </div>

          {/* Alert lightbox — full-frame zoom of any past violation */}
          {zoomedAlert && (
            <div
              className="fixed inset-0 z-[60] flex flex-col bg-black/95"
              onClick={() => setZoomedAlert(null)}
            >
              <div
                className="flex items-center justify-between gap-4 border-b border-border-on-dark px-6 py-3 text-text-on-dark"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{zoomedAlert.violation_type}</p>
                  <p className="mt-0.5 text-xs text-text-on-dark-subtle mono-num">
                    {new Date(zoomedAlert.timestamp).toLocaleString("pt-BR")} ·{" "}
                    {Math.round(zoomedAlert.confidence * 100)}% confiança
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {isReviewer && (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          void reviewAlert(zoomedAlert.id, "correct");
                        }}
                        className={
                          "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition " +
                          (zoomedAlert.feedback === "correct"
                            ? "bg-success text-white"
                            : "border border-border-on-dark text-text-on-dark-muted hover:text-text-on-dark")
                        }
                      >
                        <Check size={14} strokeWidth={2.2} /> Correto
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void reviewAlert(zoomedAlert.id, "false_positive");
                        }}
                    className={
                      "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition " +
                      (zoomedAlert.feedback === "false_positive"
                        ? "bg-danger text-white"
                        : "border border-border-on-dark text-text-on-dark-muted hover:text-text-on-dark")
                    }
                  >
                    <ThumbsDown size={14} strokeWidth={2.2} /> Falso positivo
                  </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => setZoomedAlert(null)}
                    className="grid h-9 w-9 place-items-center rounded-md text-text-on-dark-muted transition hover:bg-bg-sidebar-elevated hover:text-text-on-dark"
                    aria-label="Fechar"
                  >
                    <X size={18} strokeWidth={1.8} />
                  </button>
                </div>
              </div>
              <div className="flex flex-1 items-center justify-center p-4">
                {(() => {
                  // Reviewers get the raw (un-annotated) frame so they can
                  // see what the model actually saw without the bbox bias.
                  // Everyone else gets the annotated full-res image; the
                  // tiny thumbnail is the last resort.
                  const src =
                    (isReviewer && zoomedAlert.frame_raw_image) ||
                    zoomedAlert.frame_image ||
                    zoomedAlert.frame_thumbnail;
                  if (!src) {
                    return <p className="text-text-on-dark-muted">Sem frame disponível</p>;
                  }
                  return (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={`data:image/jpeg;base64,${src}`}
                      alt="Frame da violação"
                      onClick={(e) => e.stopPropagation()}
                      className="max-h-full max-w-full rounded-md border border-border-on-dark object-contain shadow-overlay"
                    />
                  );
                })()}
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function KPI({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center border-r border-border-on-dark px-6 py-4 last:border-r-0">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-on-dark-muted">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-text-on-dark mono-num leading-none">
        {value}
      </p>
    </div>
  );
}

type Slot = "capacete" | "colete";

function ColorPaletteSection({
  config,
  saving,
  onToggle,
  onAddCustom,
}: {
  config: CameraColorConfig;
  saving: boolean;
  onToggle: (slot: Slot, value: string) => void;
  onAddCustom: (slot: Slot, hex: string) => void;
}) {
  return (
    <section className="border-b border-border-on-dark px-5 py-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-text-on-dark-muted">
        Cores aceitas {saving && <span className="ml-1 text-text-on-dark-subtle">salvando…</span>}
      </p>
      <p className="mt-1 text-[11px] text-text-on-dark-subtle">
        Vazio = aceita qualquer cor. Adicione cores pra restringir.
      </p>
      {(["capacete", "colete"] as const).map((slot) => (
        <ColorSlot
          key={slot}
          slot={slot}
          values={config[slot]}
          presets={config.available_presets}
          onToggle={(v) => onToggle(slot, v)}
          onAddCustom={(hex) => onAddCustom(slot, hex)}
        />
      ))}
    </section>
  );
}

function ColorSlot({
  slot,
  values,
  onToggle,
  onAddCustom,
}: {
  slot: Slot;
  values: string[];
  presets: string[];
  onToggle: (v: string) => void;
  onAddCustom: (hex: string) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftHex, setDraftHex] = useState("#ffffff");
  const eyedropperSupported =
    typeof window !== "undefined" && "EyeDropper" in window;

  async function pickFromScreen() {
    try {
      const ed = new (window as unknown as { EyeDropper: new () => { open: () => Promise<{ sRGBHex: string }> } }).EyeDropper();
      const r = await ed.open();
      setDraftHex(r.sRGBHex);
    } catch {
      /* cancelled */
    }
  }

  function commit() {
    onAddCustom(draftHex);
    setPickerOpen(false);
    setDraftHex("#ffffff");
  }

  return (
    <div className="mt-3">
      <p className="text-[11px] font-medium text-text-on-dark-muted capitalize">{slot}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {values.map((v) => {
          const isHex = v.startsWith("#") && v.length === 7;
          return (
            <button
              key={v}
              type="button"
              onClick={() => onToggle(v)}
              className="inline-flex items-center gap-1 rounded-full border border-border-on-dark px-2 py-1 text-[11px] text-text-on-dark hover:opacity-80"
              title="Remover"
            >
              {isHex && (
                <span
                  className="h-3 w-3 rounded-full ring-1 ring-white/30"
                  style={{ background: v }}
                />
              )}
              {v.replace("_", " ")}
              <X size={10} strokeWidth={2.4} />
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setPickerOpen((v) => !v)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-border-on-dark px-2.5 py-1 text-[11px] text-text-on-dark-muted hover:text-text-on-dark"
        >
          <Plus size={10} strokeWidth={2.4} />
          Nova
        </button>
      </div>

      {pickerOpen && (
        <div className="mt-2 rounded-md border border-border-on-dark bg-bg-sidebar-elevated p-3">
          <div className="flex items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <span
                className="h-6 w-6 rounded ring-1 ring-white/30"
                style={{ background: draftHex }}
              />
              <input
                type="color"
                value={draftHex}
                onChange={(e) => setDraftHex(e.target.value)}
                className="sr-only"
              />
              <span className="text-[11px] text-text-on-dark-muted">
                {draftHex.toUpperCase()}
              </span>
            </label>
            {eyedropperSupported && (
              <button
                type="button"
                onClick={pickFromScreen}
                className="inline-flex items-center gap-1 rounded-md border border-border-on-dark px-2 py-1 text-[11px] text-text-on-dark-muted hover:text-text-on-dark"
                title="Pegar cor da tela (eyedropper)"
              >
                <Pipette size={11} strokeWidth={2.4} />
              </button>
            )}
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPickerOpen(false)}
                className="text-[11px] text-text-on-dark-muted hover:text-text-on-dark"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={commit}
                className="rounded-md bg-text-on-dark px-2.5 py-1 text-[11px] font-medium text-bg-sidebar"
              >
                Adicionar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SideAlertRow({ alert, onClick }: { alert: Alert; onClick?: () => void }) {
  const time = new Date(alert.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-md bg-bg-sidebar-elevated p-2 text-left transition hover:bg-bg-sidebar-elevated/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-text-on-dark"
    >
      {alert.frame_thumbnail ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`data:image/jpeg;base64,${alert.frame_thumbnail}`}
          alt="Thumbnail"
          className="h-10 w-14 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="grid h-10 w-14 shrink-0 place-items-center rounded bg-bg-sidebar text-text-on-dark-muted">
          <ShieldAlert size={14} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-text-on-dark">{alert.violation_type}</p>
        <p className="text-[11px] text-text-on-dark-subtle mono-num">
          {time} · {Math.round(alert.confidence * 100)}%
        </p>
      </div>
    </button>
  );
}

function PendingAlertRow({
  alert,
  onZoom,
  onConfirm,
  onReject,
}: {
  alert: Alert;
  onZoom: () => void;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const time = new Date(alert.timestamp).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return (
    <article className="rounded-md border border-amber-500/40 bg-bg-sidebar-elevated p-2">
      <button
        type="button"
        onClick={onZoom}
        className="flex w-full items-center gap-2.5 text-left transition hover:opacity-90"
      >
        {alert.frame_thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`data:image/jpeg;base64,${alert.frame_thumbnail}`}
            alt="Thumbnail"
            className="h-10 w-14 shrink-0 rounded object-cover"
          />
        ) : (
          <div className="grid h-10 w-14 shrink-0 place-items-center rounded bg-bg-sidebar text-text-on-dark-muted">
            <ShieldAlert size={14} />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-text-on-dark">
            {alert.violation_type}
          </p>
          <p className="text-[11px] text-text-on-dark-subtle mono-num">
            {time} · {Math.round(alert.confidence * 100)}%
          </p>
        </div>
      </button>
      <div className="mt-2 flex gap-1.5">
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex flex-1 items-center justify-center gap-1 rounded-md bg-success px-2 py-1 text-[11px] font-medium text-white hover:opacity-90"
        >
          <Check size={11} strokeWidth={2.4} /> Confirmar
        </button>
        <button
          type="button"
          onClick={onReject}
          className="inline-flex flex-1 items-center justify-center gap-1 rounded-md bg-danger px-2 py-1 text-[11px] font-medium text-white hover:opacity-90"
        >
          <ThumbsDown size={11} strokeWidth={2.4} /> Falso
        </button>
      </div>
    </article>
  );
}

function formatRate(v: number): string {
  const pct = v <= 1 ? v * 100 : v;
  return Math.max(0, Math.min(100, pct)).toFixed(0);
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h${m.toString().padStart(2, "0")}`;
  return `${m}min`;
}
