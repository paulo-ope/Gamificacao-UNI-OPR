"use client";

import { useParams } from "next/navigation";

import { LocalizaPublicFlow } from "@/components/localiza/public/localiza-public-flow";

export default function PublicLocationPage() {
  const params = useParams<{ token: string }>();
  return <LocalizaPublicFlow token={params.token} />;
}
