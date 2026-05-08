"use client";

import { CameraOff, MapPin, Pause, Play, Trash2, Loader2, AlertTriangle } from "lucide-react";
import type { Camera } from "@/types";
import { useLiveFrame } from "@/lib/useLiveFrame";

interface CameraPreviewCardProps {
  camera: Camera;
  onOpen: (camera: Camera) => void;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
  onDelete: (id: string) => void;
  recentAlertCount?: number;
  pollingPaused?: boolean;
}

export function CameraPreviewCard({
  camera,
  onOpen,
  onStart,
  onStop,
  onDelete,
  recentAlertCount = 0,
  pollingPaused = false,
}: CameraPreviewCardProps) {
  const isOnline = camera.health.online && camera.is_running;
  const frame = useLiveFrame(camera.id, 500, isOnline && !pollingPaused);

  return (
    <article className="card card-hover overflow-hidden">
      <button
        type="button"
        onClick={() => onOpen(camera)}
        className="block w-full text-left"
        aria-label={`Abrir detalhes de ${camera.name}`}
      >
        {/* Preview */}
        <div className="relative aspect-video bg-bg-sidebar">
          {!camera.is_running ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-text-on-dark-muted">
              <CameraOff size={28} strokeWidth={1.6} />
              <span className="text-xs">Câmera parada</span>
            </div>
          ) : frame.error ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-text-on-dark-muted">
              <AlertTriangle size={24} strokeWidth={1.6} className="text-warning" />
              <span className="text-xs">Sem sinal</span>
            </div>
          ) : !frame.src ? (
            <div className="flex h-full items-center justify-center text-text-on-dark-muted">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={frame.src}
              alt={`Preview ${camera.name}`}
              className="h-full w-full object-cover"
            />
          )}

          {/* Overlay header */}
          <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-black/60 to-transparent p-3">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                isOnline
                  ? "bg-success/15 text-success"
                  : camera.is_running
                    ? "bg-warning/15 text-warning"
                    : "bg-white/10 text-text-on-dark-muted"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isOnline ? "bg-success animate-pulse" : camera.is_running ? "bg-warning" : "bg-text-on-dark-muted"
                }`}
              />
              {isOnline ? "Ao vivo" : camera.is_running ? "Reconectando" : "Parada"}
            </span>
            {recentAlertCount > 0 && (
              <span className="badge badge-danger">{recentAlertCount} alertas</span>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="space-y-2 p-4">
          <div>
            <h3 className="truncate text-sm font-semibold text-text">{camera.name}</h3>
            {camera.location && (
              <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-text-muted">
                <MapPin size={11} strokeWidth={1.8} />
                {camera.location}
              </p>
            )}
          </div>
          {camera.health.last_error && !camera.health.online && (
            <p className="truncate text-xs text-danger" title={camera.health.last_error}>
              ⚠ {camera.health.last_error}
            </p>
          )}
        </div>
      </button>

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-border bg-bg-sunken px-4 py-2">
        <div className="flex items-center gap-1">
          {camera.is_running ? (
            <button
              type="button"
              onClick={() => onStop(camera.id)}
              className="btn-ghost px-2 py-1 text-xs"
              aria-label="Parar"
            >
              <Pause size={13} strokeWidth={1.8} />
              Parar
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onStart(camera.id)}
              className="btn-ghost px-2 py-1 text-xs"
              aria-label="Iniciar"
            >
              <Play size={13} strokeWidth={1.8} />
              Iniciar
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            if (confirm(`Excluir câmera "${camera.name}"?`)) onDelete(camera.id);
          }}
          className="btn-ghost px-2 py-1 text-xs text-text-muted hover:text-danger"
          aria-label="Excluir"
        >
          <Trash2 size={13} strokeWidth={1.8} />
        </button>
      </div>
    </article>
  );
}
