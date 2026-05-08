"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Clock3, ShieldAlert, X } from "lucide-react";
import type { Alert } from "@/types";

interface AlertDetailsModalProps {
  alert: Alert | null;
  onClose: () => void;
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function AlertDetailsModal({ alert, onClose }: AlertDetailsModalProps) {
  const open = alert !== null;
  if (!alert) return null;

  const imageData = alert.frame_image || alert.frame_thumbnail;
  const missingItems = alert.missing_epis.length > 0 ? alert.missing_epis : [alert.violation_type];
  const confidence = Math.round(alert.confidence * 100);

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-bg-overlay backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(94vw,960px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg bg-bg-elevated shadow-overlay outline-none data-[state=open]:animate-slide-up">
          <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
            <div>
              <p className="eyebrow">Detalhes do alerta</p>
              <Dialog.Title className="mt-1 text-lg font-semibold text-text">
                {alert.violation_type}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-text-muted">
                Inspecione a imagem capturada, os EPIs ausentes e o horário exato do registro.
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Fechar"
              className="grid h-9 w-9 place-items-center rounded-md text-text-muted transition hover:bg-bg-sunken hover:text-text"
            >
              <X size={16} strokeWidth={1.8} />
            </Dialog.Close>
          </div>

          <div className="grid gap-6 p-6 sm:grid-cols-[1.5fr_1fr]">
            <div className="overflow-hidden rounded-lg border border-border bg-bg-sidebar">
              {imageData ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:image/jpeg;base64,${imageData}`}
                  alt="Registro do alerta"
                  className="h-full max-h-[64vh] w-full object-contain"
                />
              ) : (
                <div className="flex h-80 items-center justify-center text-sm text-text-on-dark-muted">
                  Imagem indisponível para este alerta.
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="card p-4">
                <p className="eyebrow">EPIs faltantes</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {missingItems.map((item) => (
                    <span key={item} className="badge badge-danger">
                      <ShieldAlert size={12} strokeWidth={1.8} />
                      {item}
                    </span>
                  ))}
                </div>
              </div>

              <div className="card p-4">
                <p className="eyebrow">Momento do registro</p>
                <div className="mt-2 inline-flex items-center gap-2 text-sm text-text mono-num">
                  <Clock3 size={14} strokeWidth={1.8} className="text-text-muted" />
                  {formatDateTime(alert.timestamp)}
                </div>
              </div>

              <div className="card p-4">
                <p className="eyebrow">Confiança da detecção</p>
                <p className="mt-2 text-3xl font-semibold text-text mono-num">
                  {confidence > 0 ? `${confidence}%` : "—"}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  Valor representativo da inferência no momento em que a violação foi registrada.
                </p>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
