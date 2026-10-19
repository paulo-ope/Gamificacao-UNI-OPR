"use client";

import { TvScreen } from "@/components/support-tv/tv-screen";
import { fetchSupportTvPresence, fetchSupportTvSnapshot } from "@/lib/support-tv-api";

export default function SupportTvPage() {
  return (
    <TvScreen
      title="Suporte Interno"
      moduleLabel="o Suporte Interno"
      readPermission="support:read"
      fetchSnapshot={fetchSupportTvSnapshot}
      fetchPresence={fetchSupportTvPresence}
      storagePrefix="uni-support-tv"
      configurable
    />
  );
}
