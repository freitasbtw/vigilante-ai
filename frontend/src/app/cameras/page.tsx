"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Camera as CameraIcon, ShieldAlert, Check, ThumbsDown, X } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { CameraPreviewCard } from "@/components/CameraPreviewCard";
import { CameraDetailDrawer } from "@/components/CameraDetailDrawer";
import { AddCameraDialog } from "@/components/AddCameraDialog";
import {
  deleteCamera,
  getMe,
  listCameras,
  startCamera,
  stopCamera,
  listCameraAlerts,
  setAlertFeedback,
} from "@/lib/api";
import type { Camera, Alert, User } from "@/types";

interface ToastItem {
  alert: Alert;
  cameraName: string;
}

const TOAST_TTL_MS = 20_000;
const REVIEWER_ROLES: User["role"][] = ["admin", "supervisor"];

export default function CamerasHubPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  // Confirmed alerts that surface in KPIs / sidebar feed.
  const [alertsByCamera, setAlertsByCamera] = useState<Record<string, Alert[]>>({});
  // Pending alerts awaiting review — only fetched for admin/supervisor.
  const [pendingByCamera, setPendingByCamera] = useState<Record<string, Alert[]>>({});
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Camera | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seenAlertIdsRef = useRef<Set<string>>(new Set());
  const firstLoadRef = useRef(true);
  const isReviewer = !!me && REVIEWER_ROLES.includes(me.role);

  async function load() {
    setError(null);
    try {
      const user = await getMe();
      setMe(user);
      const reviewer = REVIEWER_ROLES.includes(user.role);
      const list = await listCameras();
      setCameras(list);
      const fetches = list.map(async (c) => {
        const confirmed = await listCameraAlerts(c.id, 1, 10, "confirmed").catch(
          () => [] as Alert[],
        );
        const pending = reviewer
          ? await listCameraAlerts(c.id, 1, 10, "pending").catch(() => [] as Alert[])
          : [];
        return [c.id, confirmed, pending] as const;
      });
      const results = await Promise.all(fetches);
      setAlertsByCamera(
        Object.fromEntries(results.map(([id, conf]) => [id, conf])),
      );
      setPendingByCamera(
        Object.fromEntries(results.map(([id, , pend]) => [id, pend])),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  // Keep selected camera object in sync with refreshed list
  useEffect(() => {
    if (!selected) return;
    const fresh = cameras.find((c) => c.id === selected.id);
    if (fresh) setSelected(fresh);
  }, [cameras, selected]);

  // Detect new pending alerts and surface them as soft-alert review
  // toasts. Toasts only render for reviewers. The first poll hydrates
  // the seen-set without spawning toasts so we don't dump the existing
  // pending backlog on screen at startup.
  useEffect(() => {
    if (!isReviewer) return;
    const seen = seenAlertIdsRef.current;
    const fresh: ToastItem[] = [];
    for (const cam of cameras) {
      const list = pendingByCamera[cam.id] ?? [];
      for (const a of list) {
        if (!seen.has(a.id)) {
          seen.add(a.id);
          if (!firstLoadRef.current) fresh.push({ alert: a, cameraName: cam.name });
        }
      }
    }
    if (firstLoadRef.current && Object.keys(pendingByCamera).length > 0) {
      firstLoadRef.current = false;
    }
    if (fresh.length === 0) return;
    setToasts((prev) => [...fresh, ...prev].slice(0, 5));
    fresh.forEach((t) => {
      setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.alert.id !== t.alert.id));
      }, TOAST_TTL_MS);
    });
  }, [pendingByCamera, cameras, isReviewer]);

  function dismissToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.alert.id !== id));
  }

  async function feedbackToast(id: string, value: "correct" | "false_positive") {
    try {
      const updated = await setAlertFeedback(id, value);
      // Pending list always loses this entry; confirmed list gains it
      // when the admin marks the alert as "correct". Avoids waiting for
      // the next 5s poll to reflect the decision in the UI.
      setPendingByCamera((prev) => {
        const next: Record<string, Alert[]> = {};
        for (const [cid, list] of Object.entries(prev)) {
          next[cid] = list.filter((a) => a.id !== id);
        }
        return next;
      });
      if (value === "correct") {
        setAlertsByCamera((prev) => {
          const camId = Object.entries(prev).find(([, list]) =>
            list.some((a) => a.id === id),
          )?.[0];
          // The alert isn't in the confirmed list yet; insert by camera_id
          // we recover from the pending list. If we can't determine the
          // camera, skip — next poll will reconcile.
          if (camId) return prev;
          return prev;
        });
        // Trigger an immediate refresh so the new confirmed alert shows
        // up in the sidebar without waiting for the next interval.
        void load();
      }
      // Update selected camera drawer's local state if it currently shows this alert.
      if (selected) {
        // Drawer fetches alerts itself on its own interval — no shared state to patch here.
      }
      void updated;
    } catch {
      /* ignore */
    } finally {
      dismissToast(id);
    }
  }

  async function action(id: string, kind: "start" | "stop" | "delete") {
    try {
      if (kind === "start") await startCamera(id);
      if (kind === "stop") await stopCamera(id);
      if (kind === "delete") await deleteCamera(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    }
  }

  const recentAcrossAll: { camera: Camera; alert: Alert }[] = useMemo(() => {
    const flat: { camera: Camera; alert: Alert }[] = [];
    for (const cam of cameras) {
      const list = alertsByCamera[cam.id] ?? [];
      for (const a of list) flat.push({ camera: cam, alert: a });
    }
    return flat
      .sort((a, b) => new Date(b.alert.timestamp).getTime() - new Date(a.alert.timestamp).getTime())
      .slice(0, 12);
  }, [cameras, alertsByCamera]);

  const onlineCount = cameras.filter((c) => c.health.online && c.is_running).length;

  return (
    <AppShell
      title="Câmeras ao vivo"
      subtitle={loading ? "Carregando…" : `${onlineCount} de ${cameras.length} câmeras online`}
      actions={<AddCameraDialog onCreated={load} />}
    >
      {error && (
        <div className="mb-6 rounded-md border border-danger/30 bg-danger-bg px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-text-muted">Carregando câmeras…</p>
      ) : cameras.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          {/* Camera grid */}
          <div className="grid content-start gap-4 sm:grid-cols-2">
            {cameras.map((cam) => (
              <CameraPreviewCard
                key={cam.id}
                camera={cam}
                onOpen={setSelected}
                onStart={(id) => void action(id, "start")}
                onStop={(id) => void action(id, "stop")}
                onDelete={(id) => void action(id, "delete")}
                recentAlertCount={(alertsByCamera[cam.id] ?? []).length}
                pollingPaused={selected !== null}
              />
            ))}
          </div>

          {/* Live alerts panel */}
          <aside className="card flex max-h-[calc(100vh-160px)] flex-col overflow-hidden xl:sticky xl:top-6">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-text">
                <ShieldAlert size={14} strokeWidth={1.8} />
                Alertas em tempo real
              </h2>
              <span className="text-xs text-text-muted">{recentAcrossAll.length}</span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              {recentAcrossAll.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-text-muted">
                  Nenhum alerta recente. Tudo dentro da norma.
                </p>
              ) : (
                recentAcrossAll.map(({ camera, alert }) => (
                  <button
                    key={alert.id}
                    type="button"
                    onClick={() => setSelected(camera)}
                    className="block w-full rounded-md border border-border bg-bg-elevated p-2.5 text-left transition hover:border-border-strong hover:bg-bg-sunken"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-medium text-text">{camera.name}</span>
                      <span className="shrink-0 text-[10px] text-text-muted mono-num">
                        {new Date(alert.timestamp).toLocaleTimeString("pt-BR", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-text-muted">{alert.violation_type}</p>
                  </button>
                ))
              )}
            </div>
          </aside>
        </div>
      )}

      <CameraDetailDrawer camera={selected} onClose={() => setSelected(null)} />

      {/* Soft-alert review toasts. Only rendered for reviewers (admin/supervisor)
          since pending alerts are gated server-side too. */}
      {isReviewer && (
        <div
          className="pointer-events-none fixed bottom-4 left-4 z-[70] flex w-96 flex-col gap-2"
          onPointerDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {toasts.map((t) => {
            const imageSrc =
              t.alert.frame_image || t.alert.frame_thumbnail || "";
            return (
              <article
                key={t.alert.id}
                className="pointer-events-auto overflow-hidden rounded-lg border border-amber-500/40 bg-bg-elevated shadow-overlay"
              >
                {imageSrc ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`data:image/jpeg;base64,${imageSrc}`}
                    alt="Frame da violação"
                    className="h-44 w-full object-cover"
                  />
                ) : (
                  <div className="grid h-44 w-full place-items-center bg-bg-sunken text-text-muted">
                    <ShieldAlert size={24} />
                  </div>
                )}
                <div className="p-3">
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="inline-flex items-center rounded-full bg-amber-500/15 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-600">
                          Pendente
                        </span>
                        <p className="truncate text-xs font-semibold text-text">
                          {t.cameraName}
                        </p>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-danger">
                        {t.alert.violation_type}
                      </p>
                      <p className="mt-0.5 text-[10px] text-text-muted mono-num">
                        {new Date(t.alert.timestamp).toLocaleTimeString("pt-BR", {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => dismissToast(t.alert.id)}
                      className="text-text-muted hover:text-text"
                      aria-label="Fechar"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <p className="mt-2 text-[10px] uppercase tracking-wider text-text-muted">
                    Confirmar incidente?
                  </p>
                  <div className="mt-1.5 flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => feedbackToast(t.alert.id, "correct")}
                      className="inline-flex flex-1 items-center justify-center gap-1 rounded-md bg-success px-2 py-1.5 text-[11px] font-medium text-white hover:opacity-90"
                    >
                      <Check size={12} strokeWidth={2.4} /> Confirmar
                    </button>
                    <button
                      type="button"
                      onClick={() => feedbackToast(t.alert.id, "false_positive")}
                      className="inline-flex flex-1 items-center justify-center gap-1 rounded-md bg-danger px-2 py-1.5 text-[11px] font-medium text-white hover:opacity-90"
                    >
                      <ThumbsDown size={12} strokeWidth={2.4} /> Falso positivo
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-full bg-bg-sunken text-text-muted">
        <CameraIcon size={24} strokeWidth={1.6} />
      </div>
      <h3 className="text-lg font-semibold text-text">Nenhuma câmera cadastrada</h3>
      <p className="max-w-md text-sm text-text-muted">
        Adicione sua primeira câmera RTSP para começar o monitoramento. Você pode usar o botão no topo da página.
      </p>
    </div>
  );
}
