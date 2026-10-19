"use client";

import { TvScreen } from "@/components/support-tv/tv-screen";
import { fetchSchedulingTvPresence, fetchSchedulingTvSnapshot } from "@/lib/support-tv-api";

export default function SchedulingTvPage() {
  return (
    <TvScreen
      title="Agendamento"
      moduleLabel="o Agendamento"
      readPermission="scheduling:read"
      fetchSnapshot={fetchSchedulingTvSnapshot}
      fetchPresence={fetchSchedulingTvPresence}
      storagePrefix="uni-scheduling-tv"
      showN1={false}
      showQueue
    />
  );
}
