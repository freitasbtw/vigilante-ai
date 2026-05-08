"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Plug, Plus, X } from "lucide-react";
import { useState } from "react";
import { createCamera, probeRtsp } from "@/lib/api";
import type { SourceKind } from "@/types";

interface AddCameraDialogProps {
  onCreated: () => void;
}

export function AddCameraDialog({ onCreated }: AddCameraDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [sourceKind, setSourceKind] = useState<SourceKind>("rtsp");
  const [rtspUrl, setRtspUrl] = useState("");
  const [localIndex, setLocalIndex] = useState(0);
  const [location, setLocation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeMsg, setProbeMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setName("");
    setSourceKind("rtsp");
    setRtspUrl("");
    setLocalIndex(0);
    setLocation("");
    setProbeMsg(null);
    setError(null);
  }

  async function onProbe() {
    if (!rtspUrl) return;
    setProbing(true);
    setProbeMsg(null);
    try {
      const res = await probeRtsp(rtspUrl);
      setProbeMsg({ ok: res.ok, text: res.message });
    } catch (err) {
      setProbeMsg({ ok: false, text: err instanceof Error ? err.message : "Erro" });
    } finally {
      setProbing(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await createCamera({
        name,
        source_kind: sourceKind,
        rtsp_url: sourceKind === "rtsp" ? rtspUrl : null,
        local_index: sourceKind === "local" ? localIndex : null,
        location: location || null,
      });
      onCreated();
      reset();
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="btn-primary text-sm">
          <Plus size={16} strokeWidth={2.2} />
          Adicionar câmera
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-bg-overlay backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-bg-elevated shadow-overlay outline-none data-[state=open]:animate-slide-up">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-base font-semibold text-text">Adicionar câmera</Dialog.Title>
            <Dialog.Close
              aria-label="Fechar"
              className="grid h-9 w-9 place-items-center rounded-md text-text-muted transition hover:bg-bg-sunken hover:text-text"
            >
              <X size={16} strokeWidth={1.8} />
            </Dialog.Close>
          </div>

          <form onSubmit={onSubmit} className="space-y-4 p-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="label">Nome</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input"
                  placeholder="Cam 01 — Portaria"
                />
              </div>
              <div className="space-y-1.5">
                <label className="label">Tipo</label>
                <select
                  value={sourceKind}
                  onChange={(e) => setSourceKind(e.target.value as SourceKind)}
                  className="input"
                >
                  <option value="rtsp">Câmera IP (RTSP)</option>
                  <option value="local">Webcam local</option>
                </select>
              </div>
            </div>

            {sourceKind === "rtsp" ? (
              <div className="space-y-1.5">
                <label className="label">URL RTSP</label>
                <div className="flex gap-2">
                  <input
                    required
                    value={rtspUrl}
                    onChange={(e) => setRtspUrl(e.target.value)}
                    className="input mono-num"
                    placeholder="rtsp://user:pass@192.168.1.50:554/stream"
                  />
                  <button
                    type="button"
                    onClick={onProbe}
                    disabled={probing || !rtspUrl}
                    className="btn-secondary shrink-0 text-xs"
                  >
                    <Plug size={13} strokeWidth={1.8} />
                    {probing ? "..." : "Testar"}
                  </button>
                </div>
                {probeMsg && (
                  <p className={`text-xs ${probeMsg.ok ? "text-success" : "text-danger"}`}>
                    {probeMsg.ok ? "✓" : "✗"} {probeMsg.text}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                <label className="label">Índice da webcam</label>
                <input
                  type="number"
                  min={0}
                  value={localIndex}
                  onChange={(e) => setLocalIndex(parseInt(e.target.value) || 0)}
                  className="input w-32"
                />
              </div>
            )}

            <div className="space-y-1.5">
              <label className="label">Localização (opcional)</label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="input"
                placeholder="Setor 3 / Portão A"
              />
            </div>

            {error && (
              <p className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close className="btn-ghost text-sm">Cancelar</Dialog.Close>
              <button type="submit" disabled={submitting} className="btn-primary text-sm">
                {submitting ? "..." : "Salvar"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
