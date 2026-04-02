"use client";

import VideoFeed from "@/components/VideoFeed";
import StatusBar from "@/components/StatusBar";
import Controls from "@/components/Controls";
import AlertPanel from "@/components/AlertPanel";
import EPIPanel from "@/components/EPIPanel";
import { useMonitorStatus } from "@/hooks/useMonitorStatus";

export default function Home() {
  const {
    monitorState,
    status,
    actionError,
    onStartPending,
    onStartSuccess,
    onStartError,
    onStop,
  } = useMonitorStatus();

  return (
    <div className="space-y-6">
      <section className="surface-card relative overflow-hidden p-6 sm:p-7">
        <div className="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-4">
            <div>
              <p className="eyebrow">Centro de monitoramento</p>
              <h2 className="mt-2 max-w-3xl text-3xl font-semibold tracking-tight text-[var(--foreground)] sm:text-4xl">
                Operacao em tempo real com feedback visual claro desde o primeiro segundo.
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted)] sm:text-base">
                Acompanhe o feed, o desempenho do processamento e os incidentes recentes sem perder contexto quando a camera ainda estiver inicializando.
              </p>
            </div>

            <StatusBar status={status} monitorState={monitorState} />

            {actionError && (
              <div className="inline-flex rounded-full border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700">
                {actionError}
              </div>
            )}
          </div>

          <Controls
            monitorState={monitorState}
            onStartPending={onStartPending}
            onStartSuccess={onStartSuccess}
            onStartError={onStartError}
            onStop={onStop}
          />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_360px]">
        <div className="min-w-0 space-y-6">
          <VideoFeed monitorState={monitorState} fps={status?.fps ?? 0} />
          <EPIPanel />
        </div>
        <div className="min-w-0 xl:sticky xl:top-6 xl:h-[calc(100vh-8.5rem)]">
          <AlertPanel />
        </div>
      </div>
    </div>
  );
}
