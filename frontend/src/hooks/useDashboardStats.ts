"use client";

import { useCallback, useState } from "react";
import { getStats } from "@/lib/api";
import type { SessionStats } from "@/types";
import { usePolling } from "@/hooks/usePolling";

export function useDashboardStats() {
  const [stats, setStats] = useState<SessionStats | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await getStats();
      setStats(data);
    } catch {
      // Backend may be offline
    }
  }, []);

  usePolling(fetchStats, 5000);

  return { stats };
}
