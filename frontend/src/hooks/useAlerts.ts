"use client";

import { useCallback, useRef, useState } from "react";
import { clearAlerts, getAlerts } from "@/lib/api";
import type { Alert } from "@/types";
import { usePolling } from "@/hooks/usePolling";

export function useAlerts(soundEnabled: boolean) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const prevCountRef = useRef(0);
  const audioContextRef = useRef<AudioContext | null>(null);

  const playNotification = useCallback(() => {
    const AudioContextCtor =
      window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;

    if (!AudioContextCtor) return;

    const ctx = audioContextRef.current ?? new AudioContextCtor();
    audioContextRef.current = ctx;

    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.frequency.value = 880;
    gain.gain.value = 0.15;
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.12);
  }, []);

  const pollAlerts = useCallback(async () => {
    try {
      const data = await getAlerts();
      setAlerts(data);
      if (soundEnabled && data.length > prevCountRef.current) {
        playNotification();
      }
      prevCountRef.current = data.length;
    } catch {
      // ignore fetch errors
    }
  }, [playNotification, soundEnabled]);

  usePolling(pollAlerts, 2000);

  const clearAllAlerts = useCallback(async () => {
    await clearAlerts();
    setAlerts([]);
    prevCountRef.current = 0;
  }, []);

  return { alerts, clearAllAlerts };
}
