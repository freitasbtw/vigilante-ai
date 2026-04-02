"use client";

import { useCallback, useEffect, useState } from "react";
import { getEPIConfig, updateEPIConfig } from "@/lib/api";
import type { EPIItem } from "@/types";

export function useEpiConfig() {
  const [epis, setEpis] = useState<EPIItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEPIConfig()
      .then((config) => setEpis(config.epis))
      .catch((err) => setError(err.message));
  }, []);

  const toggleEpi = useCallback(
    async (key: string) => {
      const previous = epis;
      const updated = epis.map((epi) =>
        epi.key === key ? { ...epi, active: !epi.active } : epi
      );
      setEpis(updated);

      const activeKeys = updated.filter((epi) => epi.active).map((epi) => epi.key);

      try {
        const config = await updateEPIConfig(activeKeys);
        setEpis(config.epis);
        setError(null);
      } catch (err) {
        setEpis(previous);
        setError(err instanceof Error ? err.message : "Erro ao atualizar EPIs");
      }
    },
    [epis]
  );

  return { epis, error, toggleEpi };
}
