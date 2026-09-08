"use client";

import dynamic from "next/dynamic";
import { Check, Copy, ExternalLink, MapPin, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { distanceClassificationLabel, distanceClassificationTone, formatDistanceMeters, googleMapsUrl } from "@/lib/geo-distance";
import { localizaApi, type LocationRequest, type LocationRequestCreateResult } from "@/lib/localiza-api";
import { LOCALIZA_STATUS_LABELS, LOCALIZA_STATUS_TONE, formatPortoVelho, localizaRequestLabel } from "./localiza-format";

const LocalizaDetailMapLeaflet = dynamic(
  () => import("./localiza-detail-map-leaflet").then((mod) => mod.LocalizaDetailMapLeaflet),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-slate-400">Carregando mapa…</div> },
);

// Aceita tanto uma solicitação já existente quanto o resultado de uma criação/regeneração
// recém-feita (que carrega o token em claro e o link público - só existem nesta resposta única).
type PanelItem = LocationRequest | LocationRequestCreateResult;

function hasFreshLink(value: PanelItem): value is LocationRequestCreateResult {
  return "public_link" in value;
}

// Intervalo curto o bastante pra o atendente ver a confirmação do cliente sem recarregar a
// página (pedido explícito), sem virar polling agressivo - a tela fica aberta por minutos, não
// por horas, e só enquanto a solicitação seguir pendente.
const POLL_INTERVAL_MS = 4000;

export function LocalizaDetailPanel({
  item,
  onClose,
  onChanged,
}: {
  item: PanelItem;
  onClose: () => void;
  onChanged: (next: LocationRequest) => void;
}) {
  const [current, setCurrent] = useState<LocationRequest>(item);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  // Nasce preenchido quando o painel abre logo após CRIAR ou REGENERAR (o `item` recebido já é o
  // resultado dessa chamada) - antes disso o link só aparecia no card do formulário, escondido
  // atrás deste painel (achado real, reportado pelo usuário ao ver a tela ao vivo).
  const [freshLink, setFreshLink] = useState<LocationRequestCreateResult | null>(hasFreshLink(item) ? item : null);
  const [orderCodeInput, setOrderCodeInput] = useState("");
  const [attaching, setAttaching] = useState(false);

  async function copy(text: string, field: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField((current) => (current === field ? null : current)), 2000);
    } catch {
      setError("Não foi possível copiar. Copie manualmente.");
    }
  }

  async function invalidate() {
    setBusy(true);
    setError(null);
    try {
      const updated = await localizaApi.invalidate(current.id);
      setCurrent(updated);
      onChanged(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao invalidar o link.");
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    setBusy(true);
    setError(null);
    try {
      const created = await localizaApi.regenerate(current.id);
      setCurrent(created);
      setFreshLink(created);
      onChanged(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao gerar nova solicitação.");
    } finally {
      setBusy(false);
    }
  }

  async function attachOrder() {
    if (!orderCodeInput.trim()) return;
    setAttaching(true);
    setError(null);
    try {
      const updated = await localizaApi.attachOrder(current.id, orderCodeInput.trim());
      setCurrent(updated);
      onChanged(updated);
      setOrderCodeInput("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao anexar o código da O.S.");
    } finally {
      setAttaching(false);
    }
  }

  // Atualização automática enquanto a solicitação segue pendente - o cliente pode confirmar a
  // qualquer momento, e o atendente não deveria precisar recarregar a página pra ver (pedido
  // explícito). Para sozinho assim que sair de "pending" (confirmado/invalidado/expirado) ou o
  // painel fechar.
  const currentIdRef = useRef(current.id);
  currentIdRef.current = current.id;
  useEffect(() => {
    if (current.status !== "pending") return;
    const interval = setInterval(async () => {
      try {
        const refreshed = await localizaApi.get(currentIdRef.current);
        setCurrent(refreshed);
        onChanged(refreshed);
      } catch {
        // Falha de rede pontual não deveria interromper o polling nem incomodar o atendente -
        // a próxima tentativa resolve sozinha.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.status, current.id]);

  const registeredPoint =
    current.registered_latitude !== null && current.registered_longitude !== null
      ? { latitude: current.registered_latitude, longitude: current.registered_longitude }
      : null;
  const confirmedPoint =
    current.confirmed_latitude !== null && current.confirmed_longitude !== null
      ? { latitude: current.confirmed_latitude, longitude: current.confirmed_longitude }
      : null;

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex flex-col gap-0 p-0">
        <SheetHeader className="border-b border-slate-200 px-6 py-4">
          <SheetTitle className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-blue-600" aria-hidden="true" />
            {localizaRequestLabel(current)} · {current.public_id}
          </SheetTitle>
          <SheetDescription>{current.customer_name || "Cliente não identificado"}</SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="grid gap-4 lg:grid-cols-[1.1fr_1.4fr]">
            <div className="grid gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <dl className="grid gap-1.5 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <dt className="text-slate-500">Protocolo OPA</dt>
                    <dd className="font-medium text-slate-950">{current.opa_protocol || "-"}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <dt className="text-slate-500">Código da O.S.</dt>
                    <dd className="font-medium text-slate-950">{current.order_code || "Ainda não informado"}</dd>
                  </div>
                </dl>
                {!current.order_code && current.status !== "invalidated" ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                    <Input
                      className="h-9 min-w-0 flex-1"
                      placeholder="Anexar código da O.S. quando existir"
                      value={orderCodeInput}
                      onChange={(event) => setOrderCodeInput(event.target.value)}
                    />
                    <Button size="sm" onClick={attachOrder} disabled={attaching || !orderCodeInput.trim()}>
                      Anexar O.S.
                    </Button>
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <StatusBadge tone={LOCALIZA_STATUS_TONE[current.status]}>{LOCALIZA_STATUS_LABELS[current.status]}</StatusBadge>
                  <span className="text-xs text-slate-500">Criado em {formatPortoVelho(current.created_at)}</span>
                </div>
                <dl className="mt-3 grid gap-2 text-sm">
                  {current.requested_by_name ? (
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-slate-500">Solicitado por</dt>
                      <dd className="font-medium text-slate-950">{current.requested_by_name}</dd>
                    </div>
                  ) : null}
                  <div className="flex items-center justify-between gap-2">
                    <dt className="text-slate-500">Expira em</dt>
                    <dd className="font-medium text-slate-950">{formatPortoVelho(current.expires_at)}</dd>
                  </div>
                  {current.opened_at ? (
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-slate-500">Aberto pelo cliente em</dt>
                      <dd className="font-medium text-slate-950">{formatPortoVelho(current.opened_at)}</dd>
                    </div>
                  ) : null}
                  {current.confirmed_at ? (
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-slate-500">Confirmado em</dt>
                      <dd className="font-medium text-slate-950">{formatPortoVelho(current.confirmed_at)}</dd>
                    </div>
                  ) : null}
                  {current.invalidated_at ? (
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-slate-500">Invalidado em</dt>
                      <dd className="font-medium text-slate-950">{formatPortoVelho(current.invalidated_at)}</dd>
                    </div>
                  ) : null}
                </dl>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-950">Coordenadas</h3>
                <dl className="mt-3 grid gap-3 text-sm">
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">Cadastrada</dt>
                    <dd className="font-mono text-slate-800">
                      {registeredPoint ? `${registeredPoint.latitude.toFixed(6)}, ${registeredPoint.longitude.toFixed(6)}` : "Não informada"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">Confirmada pelo cliente</dt>
                    <dd className="font-mono text-slate-800">
                      {confirmedPoint ? `${confirmedPoint.latitude.toFixed(6)}, ${confirmedPoint.longitude.toFixed(6)}` : "Aguardando confirmação"}
                    </dd>
                    {current.accuracy_meters !== null ? (
                      <p className="text-xs text-slate-500">Precisão do GPS: {formatDistanceMeters(current.accuracy_meters)}</p>
                    ) : null}
                    {current.adjusted_manually ? <p className="text-xs text-amber-700">Posição ajustada manualmente pelo cliente</p> : null}
                  </div>
                  {current.distance_from_registered_meters !== null && current.distance_classification ? (
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">Diferença da coordenada cadastrada</dt>
                      <dd className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-slate-950">{formatDistanceMeters(current.distance_from_registered_meters)}</span>
                        <StatusBadge tone={distanceClassificationTone(current.distance_classification)}>
                          {distanceClassificationLabel(current.distance_classification)}
                        </StatusBadge>
                      </dd>
                    </div>
                  ) : null}
                </dl>

                <div className="mt-4 flex flex-wrap gap-2">
                  {confirmedPoint ? (
                    <Button asChild variant="outline" size="sm">
                      <a href={googleMapsUrl(confirmedPoint.latitude, confirmedPoint.longitude)} target="_blank" rel="noreferrer">
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /> Abrir no Google Maps
                      </a>
                    </Button>
                  ) : null}
                  {confirmedPoint ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => copy(googleMapsUrl(confirmedPoint.latitude, confirmedPoint.longitude), "coordinates")}
                    >
                      {copiedField === "coordinates" ? (
                        <>
                          <Check className="h-3.5 w-3.5" aria-hidden="true" /> Copiado!
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copiar localização
                        </>
                      )}
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-950">Link enviado ao cliente</h3>
                {freshLink ? (
                  <div className="mt-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                    <p className="truncate font-mono text-xs text-emerald-800">{freshLink.public_link}</p>
                    <Button variant="outline" size="sm" className="mt-2" onClick={() => copy(freshLink.public_link, "fresh-link")}>
                      {copiedField === "fresh-link" ? (
                        <>
                          <Check className="h-3.5 w-3.5" aria-hidden="true" /> Copiado!
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copiar link
                        </>
                      )}
                    </Button>
                    <p className="mt-2 text-[11px] text-emerald-700">
                      Por segurança, o link só é exibido aqui nesta sessão. Para reenviar depois, gere uma nova solicitação.
                    </p>
                  </div>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">
                    Por segurança, o link só é exibido no momento em que é gerado. Para reenviar, gere uma nova solicitação -
                    o link atual é invalidado automaticamente.
                  </p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  {current.status === "pending" ? (
                    <Button variant="outline" size="sm" onClick={invalidate} disabled={busy}>
                      <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> Invalidar link
                    </Button>
                  ) : null}
                  <Button variant="outline" size="sm" onClick={regenerate} disabled={busy}>
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Gerar nova solicitação
                  </Button>
                </div>
                {error ? <p className="mt-2 text-xs text-rose-600">{error}</p> : null}
              </div>
            </div>

            <div className="isolate min-h-[380px] overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
              {registeredPoint || confirmedPoint ? (
                <LocalizaDetailMapLeaflet registered={registeredPoint} confirmed={confirmedPoint} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">Nenhuma coordenada disponível ainda.</div>
              )}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
