"use client";

import dynamic from "next/dynamic";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2, MapPin, MapPinned, RotateCcw, Settings } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { localizaApi, type PublicLocationStatus } from "@/lib/localiza-api";

const LocalizaPickerMapLeaflet = dynamic(
  () => import("./localiza-picker-map-leaflet").then((mod) => mod.LocalizaPickerMapLeaflet),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-slate-400">Carregando mapa…</div> },
);

// Mensagens amigáveis - nunca o código técnico do navegador/API cru na tela (exigência do escopo).
const STATUS_REASON_MESSAGES: Record<string, string> = {
  TOKEN_INVALID: "Este link de localização não é válido. Confira se copiou o endereço completo.",
  TOKEN_EXPIRED: "Este link de localização expirou. Solicite um novo link ao atendimento.",
  ALREADY_CONFIRMED: "Esta localização já foi enviada.",
  INVALIDATED: "Este link não está mais disponível.",
};

const GEOLOCATION_ERROR_MESSAGES: Record<number, string> = {
  1: "Não foi possível acessar sua localização. Verifique se a permissão de localização está habilitada.",
  2: "Não conseguimos identificar sua localização neste momento. Tente novamente em um local com melhor sinal de GPS.",
  3: "A localização demorou mais que o esperado. Tente novamente.",
};

type GpsFix = { latitude: number; longitude: number; accuracy: number };
type Step = "loading" | "invalid" | "intro" | "locating" | "review" | "confirming" | "success";

// Precisão boa o bastante pra parar de esperar - o GPS de celular costuma chegar nessa faixa
// poucos segundos depois do primeiro fix (grosseiro) da rede.
const GOOD_ACCURACY_METERS = 30;
// Acima disto a posição não serve pra despachar equipe (é praticamente "o bairro", não a casa) -
// a confirmação fica BLOQUEADA (exigência do usuário: "preciso da localização precisa pra
// retirar/enviar a equipe"). A única saída é ativar a localização precisa e tentar de novo, ou
// posicionar o marcador manualmente no ponto certo - aí a posição passa a ser escolha humana
// explícita, não um chute do aparelho.
const MAX_ACCEPTABLE_ACCURACY_METERS = 100;
// Teto de espera do refinamento: passando disso, usa a melhor leitura obtida até aqui em vez de
// deixar o cliente esperando indefinidamente.
const MAX_REFINE_MS = 20_000;

function formatAccuracy(accuracyMeters: number): string {
  if (accuracyMeters >= 1000) return `${(accuracyMeters / 1000).toFixed(1).replace(".", ",")} km`;
  return `${Math.round(accuracyMeters)} m`;
}

// Limiares de QUALIDADE DO GPS (raio de incerteza que o próprio navegador reporta) - diferente da
// classificação de divergência cadastral (calculada no backend contra a coordenada do IXC). Pedido
// do usuário: dar um aviso claro e "legal" quando a localização vier imprecisa, guiando o cliente a
// ajustar o marcador em vez de só confirmar um número que ele não entende.
function accuracyBanner(accuracyMeters: number): { className: string; text: string } {
  if (accuracyMeters <= 20) {
    return { className: "border-emerald-200 bg-emerald-50 text-emerald-800", text: `Boa precisão (${formatAccuracy(accuracyMeters)}).` };
  }
  if (accuracyMeters <= 100) {
    return {
      className: "border-amber-200 bg-amber-50 text-amber-800",
      text: `Precisão moderada (${formatAccuracy(accuracyMeters)}) - se possível, arraste o marcador para o ponto exato antes de confirmar.`,
    };
  }
  return {
    className: "border-rose-200 bg-rose-50 text-rose-800",
    text: `Localização imprecisa (~${formatAccuracy(accuracyMeters)}) - o aparelho respondeu com a posição aproximada da rede, não com o GPS. Ative a localização precisa do celular e tente novamente, ou arraste o marcador até o ponto certo no mapa antes de confirmar.`,
  };
}

// Navegador EMBUTIDO de app (WhatsApp, Instagram, Facebook...) - o link chega pelo WhatsApp, então
// é nele que o cliente abre por padrão, e esses navegadores internos costumam não acessar o GPS,
// caindo na posição de rede (quilômetros). Detecção conservadora: na dúvida NÃO acusa, porque um
// falso positivo mandaria o cliente pra um caminho que ele não precisa.
function isInAppBrowser(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  return /(WhatsApp|Instagram|FBAN|FBAV|FB_IAB|Line\/|MicroMessenger)/i.test(ua);
}

function InAppBrowserWarning() {
  return (
    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
      <p className="font-medium">Você abriu pelo navegador do aplicativo.</p>
      <p className="mt-1">
        Aqui o GPS costuma não funcionar, e a localização sai muito imprecisa. Toque nos três pontinhos no canto da
        tela e escolha <strong>&quot;Abrir no navegador&quot;</strong> (Chrome ou Safari) para conseguir a posição exata.
      </p>
    </div>
  );
}

function detectPlatform(): "android" | "iphone" {
  if (typeof navigator === "undefined") return "android";
  return /iPhone|iPad|iPod/i.test(navigator.userAgent || "") ? "iphone" : "android";
}

// Computador não tem GPS: mesmo com a permissão liberada, a posição vem de Wi-Fi/IP (centenas de
// metros a quilômetros). Não é problema de permissão e nenhuma configuração resolve - por isso o
// aviso é outro (usar o celular), não o guia de permissão.
function isDesktop(): boolean {
  if (typeof navigator === "undefined") return false;
  return !/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || "");
}

function DesktopWarning() {
  return (
    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
      <p className="font-medium">Você está num computador.</p>
      <p className="mt-1">
        Computadores não têm GPS - a posição sai por Wi-Fi/internet, com vários quilômetros de erro. Para a equipe
        achar o endereço certo, <strong>abra este mesmo link pelo celular</strong>.
      </p>
    </div>
  );
}

// Guia de "como ativar a localização" - aparece quando a permissão é negada ou quando a precisão
// vem ruim demais pra despachar equipe.
//
// Não existe API pra "elevar" permissão: nenhum site pode ligar o GPS, trocar a localização
// aproximada por precisa, nem forçar um novo pedido depois de negado (trava do sistema
// operacional). O que dá pra fazer é encurtar o caminho - por isso o guia (a) detecta o aparelho
// e mostra só os passos daquele sistema, (b) começa ABERTO quando já se sabe que é necessário, e
// (c) mostra primeiro o atalho DENTRO do navegador, que resolve sem abrir o app de Ajustes
// (pedido do usuário em 2026-09-08: "muitos têm que acessar as config").
function LocationHelpGuide({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [tab, setTab] = useState<"android" | "iphone">(detectPlatform);
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between text-xs font-medium text-slate-600"
      >
        <span className="flex items-center gap-1.5">
          <Settings className="h-3.5 w-3.5" aria-hidden="true" /> Como ativar a localização
        </span>
        {open ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
      </button>
      {open ? (
        <div className="mt-3">
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1">
            <button
              type="button"
              onClick={() => setTab("android")}
              className={`h-7 rounded-md px-2.5 text-xs font-medium ${tab === "android" ? "bg-slate-100 text-slate-950" : "text-slate-500"}`}
            >
              Android
            </button>
            <button
              type="button"
              onClick={() => setTab("iphone")}
              className={`h-7 rounded-md px-2.5 text-xs font-medium ${tab === "iphone" ? "bg-slate-100 text-slate-950" : "text-slate-500"}`}
            >
              iPhone
            </button>
          </div>
          {tab === "android" ? (
            <>
              <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Sem sair desta tela</p>
              <ol className="mt-1 list-decimal space-y-1 pl-4 text-xs text-slate-600">
                <li>Toque no <strong>cadeado</strong> (ou no ícone ao lado do endereço, no topo).</li>
                <li>Toque em <strong>Permissões</strong> {'>'} <strong>Localização</strong> e escolha Permitir.</li>
                <li>Volte aqui e toque em &quot;Tentar localizar novamente&quot;.</li>
              </ol>
              <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Se continuar impreciso (quilômetros)
              </p>
              <ol className="mt-1 list-decimal space-y-1 pl-4 text-xs text-slate-600">
                <li>Configurações do celular {'>'} <strong>Localização</strong> - ative.</li>
                <li>
                  Ainda em Localização: <strong>Permissões</strong> {'>'} seu navegador {'>'} ative
                  <strong> &quot;Usar localização precisa&quot;</strong>. Sem ela o Android manda só a posição
                  aproximada, por mais que se espere.
                </li>
              </ol>
            </>
          ) : (
            <>
              <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Sem sair desta tela</p>
              <ol className="mt-1 list-decimal space-y-1 pl-4 text-xs text-slate-600">
                <li>
                  Toque em <strong>&quot;aA&quot;</strong> (à esquerda do endereço, no topo da tela).
                </li>
                <li>
                  Toque em <strong>Ajustes do Site</strong> {'>'} <strong>Localização</strong> e escolha
                  <strong> Permitir</strong> (ou Perguntar).
                </li>
                <li>Volte aqui e toque em &quot;Tentar localizar novamente&quot;.</li>
              </ol>
              <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Se continuar impreciso (quilômetros)
              </p>
              <ol className="mt-1 list-decimal space-y-1 pl-4 text-xs text-slate-600">
                <li>Ajustes {'>'} Privacidade e Segurança {'>'} <strong>Serviços de Localização</strong> - ative.</li>
                <li>
                  Na mesma tela, role até o <strong>Safari</strong>, escolha &quot;Ao Usar o App&quot; e ative
                  <strong> &quot;Localização Precisa&quot;</strong>.
                </li>
              </ol>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function LocalizaPublicFlow({ token }: { token: string }) {
  const [step, setStep] = useState<Step>("loading");
  const [status, setStatus] = useState<PublicLocationStatus | null>(null);
  const [gpsFix, setGpsFix] = useState<GpsFix | null>(null);
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);
  const [adjustedManually, setAdjustedManually] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  // Melhor precisão obtida até agora enquanto o GPS ainda está refinando (só para mostrar
  // progresso ao cliente - o valor definitivo vai para `gpsFix` quando a captura encerra).
  const [refiningAccuracy, setRefiningAccuracy] = useState<number | null>(null);
  const watchIdRef = useRef<number | null>(null);
  const refineTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bestFixRef = useRef<GpsFix | null>(null);
  // Estado da permissão informado pelo próprio navegador (Chrome no Android e no PC; o Safari não
  // expõe geolocalização aqui, e aí fica "unknown" e o fluxo segue normal). Serve pra dois ganhos
  // reais: avisar que está BLOQUEADO antes de a pessoa tentar e falhar, e perceber sozinho quando
  // ela ajustou nas configurações e voltou - sem depender de ela adivinhar que precisa tentar de
  // novo. Não existe forma de ELEVAR a permissão por código: só de saber em que pé ela está.
  const [permissionState, setPermissionState] = useState<"granted" | "denied" | "prompt" | "unknown">("unknown");

  useEffect(() => {
    let cancelled = false;
    let status: PermissionStatus | null = null;
    async function checkPermission() {
      try {
        if (typeof navigator === "undefined" || !navigator.permissions?.query) return;
        status = await navigator.permissions.query({ name: "geolocation" as PermissionName });
        if (cancelled || !status) return;
        setPermissionState(status.state);
        status.onchange = () => {
          if (!cancelled && status) setPermissionState(status.state);
        };
      } catch {
        // Navegador sem suporte (Safari) - segue sem antecipar o estado, nada quebra.
      }
    }
    void checkPermission();
    return () => {
      cancelled = true;
      if (status) status.onchange = null;
    };
  }, []);

  useEffect(() => {
    let active = true;
    localizaApi
      .publicStatus(token)
      .then((result) => {
        if (!active) return;
        setStatus(result);
        setStep(result.valid ? "intro" : "invalid");
      })
      .catch(() => {
        if (!active) return;
        setStatus({ valid: false, reason: "TOKEN_INVALID", order_code: null, opa_protocol: null, customer_name: null, status: null, expires_at: null });
        setStep("invalid");
      });
    return () => {
      active = false;
    };
  }, [token]);

  function stopWatching() {
    if (watchIdRef.current !== null && typeof navigator !== "undefined" && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }
    watchIdRef.current = null;
    if (refineTimerRef.current) {
      clearTimeout(refineTimerRef.current);
      refineTimerRef.current = null;
    }
  }

  // Encerra a captura ficando com a melhor leitura obtida e leva o cliente para a confirmação.
  function acceptFix(fix: GpsFix) {
    stopWatching();
    setGpsFix(fix);
    setPosition({ latitude: fix.latitude, longitude: fix.longitude });
    setAdjustedManually(false);
    setAttempt((value) => value + 1);
    setRefiningAccuracy(null);
    setStep("review");
  }

  useEffect(() => stopWatching, []);

  // A chamada à API de geolocalização acontece só em resposta direta a este clique - nunca
  // automaticamente ao carregar a página (exigência explícita do escopo).
  function shareLocation() {
    setError(null);
    setPermissionDenied(false);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError("Seu navegador não é compatível com o compartilhamento de localização.");
      return;
    }
    stopWatching();
    bestFixRef.current = null;
    setRefiningAccuracy(null);
    setStep("locating");

    // `watchPosition` em vez de `getCurrentPosition`: o sistema entrega o PRIMEIRO fix disponível,
    // que quase sempre é o da rede (Wi-Fi/torre de celular, na casa dos quilômetros) - o GPS só
    // alcança precisão de metros alguns segundos depois. Com uma leitura única, essa leitura boa
    // nunca chegava, e `enableHighAccuracy` sozinho não resolve: ele pede o GPS, mas não faz o
    // navegador ESPERAR por ele (causa real da "localização imprecisa em todos os dispositivos"
    // reportada pelo usuário em 2026-09-08). Aqui as leituras vão chegando e ficamos com a melhor.
    watchIdRef.current = navigator.geolocation.watchPosition(
      (result) => {
        const fix: GpsFix = {
          latitude: result.coords.latitude,
          longitude: result.coords.longitude,
          accuracy: result.coords.accuracy,
        };
        if (!bestFixRef.current || fix.accuracy < bestFixRef.current.accuracy) {
          bestFixRef.current = fix;
          setRefiningAccuracy(fix.accuracy);
        }
        // Boa o bastante: não faz o cliente esperar mais do que o necessário.
        if (bestFixRef.current.accuracy <= GOOD_ACCURACY_METERS) acceptFix(bestFixRef.current);
      },
      (geoError) => {
        // Erro tardio (ex.: perda de sinal) depois de já ter alguma leitura não deve descartar o
        // que já foi obtido - segue com a melhor leitura em vez de mandar o cliente recomeçar.
        if (bestFixRef.current) {
          acceptFix(bestFixRef.current);
          return;
        }
        stopWatching();
        setError(GEOLOCATION_ERROR_MESSAGES[geoError.code] || "Não foi possível obter sua localização. Tente novamente.");
        setPermissionDenied(geoError.code === 1);
        setRefiningAccuracy(null);
        setStep("intro");
      },
      { enableHighAccuracy: true, timeout: MAX_REFINE_MS, maximumAge: 0 },
    );

    refineTimerRef.current = setTimeout(() => {
      if (bestFixRef.current) {
        acceptFix(bestFixRef.current);
        return;
      }
      stopWatching();
      setError(GEOLOCATION_ERROR_MESSAGES[3]);
      setRefiningAccuracy(null);
      setStep("intro");
    }, MAX_REFINE_MS);
  }

  function handleMarkerMoved(latitude: number, longitude: number) {
    setPosition({ latitude, longitude });
    setAdjustedManually(true);
  }

  async function confirmLocation() {
    if (!position || !gpsFix) return;
    setStep("confirming");
    setError(null);
    try {
      await localizaApi.publicConfirm(token, {
        latitude: position.latitude,
        longitude: position.longitude,
        accuracy_meters: gpsFix.accuracy,
        gps_latitude: gpsFix.latitude,
        gps_longitude: gpsFix.longitude,
        adjusted_manually: adjustedManually,
      });
      setStep("success");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "TOKEN_INVALID";
      setError(STATUS_REASON_MESSAGES[message] || "Não foi possível enviar sua localização agora. Tente novamente em instantes.");
      setStep("review");
    }
  }

  const banner = gpsFix ? accuracyBanner(gpsFix.accuracy) : null;
  // Ajuste manual do marcador libera a confirmação mesmo com GPS ruim: aí a posição é escolha
  // explícita da pessoa (que sabe onde mora), não mais o chute do aparelho.
  const blockedByAccuracy = Boolean(gpsFix && gpsFix.accuracy > MAX_ACCEPTABLE_ACCURACY_METERS && !adjustedManually);

  return (
    <main className="flex min-h-screen flex-col bg-slate-50">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-5 py-4">
        <img src="/brand/uni-logo.png" alt="" className="h-7 w-auto object-contain" onError={(event) => (event.currentTarget.style.display = "none")} />
        <span className="text-sm font-semibold text-slate-950">UNI Localiza</span>
      </header>

      <div className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-6">
        {step === "loading" ? (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> Verificando link...
          </div>
        ) : null}

        {step === "invalid" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
            <AlertTriangle className="h-8 w-8 text-rose-500" aria-hidden="true" />
            <p className="text-sm font-medium text-rose-800">
              {STATUS_REASON_MESSAGES[status?.reason || "TOKEN_INVALID"] || "Este link de localização não está disponível."}
            </p>
          </div>
        ) : null}

        {step === "intro" || step === "locating" ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            {status?.order_code || status?.opa_protocol ? (
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                {status.order_code ? `O.S. ${status.order_code}` : `Protocolo ${status.opa_protocol}`}
              </p>
            ) : null}
            <div className="mt-2 flex items-center gap-2">
              <MapPin className="h-5 w-5 text-blue-600" aria-hidden="true" />
              <h1 className="text-lg font-semibold text-slate-950">Compartilhar sua localização</h1>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              Para localizarmos corretamente o endereço do atendimento, permita o acesso à sua localização. Sua
              localização será enviada somente após sua confirmação.
            </p>
            {/* Avisa ANTES de tentar: no navegador embutido do app a tentativa quase sempre volta
                imprecisa, e a pessoa perde a viagem duas vezes (tentar, falhar, trocar, repetir). */}
            {isInAppBrowser() ? <InAppBrowserWarning /> : null}
            {!isInAppBrowser() && isDesktop() ? <DesktopWarning /> : null}

            {/* O navegador já disse que está bloqueado: não faz sentido a pessoa tocar no botão e
                receber um erro - mostra o caminho direto. */}
            {permissionState === "denied" && !permissionDenied ? (
              <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                A localização está <strong>bloqueada</strong> para este site no seu navegador. Libere pelo caminho
                abaixo e o botão volta a funcionar.
              </div>
            ) : null}
            {permissionState === "denied" ? <LocationHelpGuide defaultOpen /> : null}

            {/* Reagiu sozinho: a pessoa liberou nas configurações e voltou - confirma que já pode
                seguir, em vez de deixar ela na dúvida se precisa fazer mais alguma coisa. */}
            {permissionState === "granted" && (permissionDenied || error) ? (
              <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                Permissão liberada. Toque em <strong>&quot;Compartilhar minha localização&quot;</strong> para continuar.
              </div>
            ) : null}
            <Button className="mt-4 w-full" onClick={shareLocation} disabled={step === "locating"}>
              {step === "locating" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Obtendo localização...
                </>
              ) : (
                <>
                  <MapPinned className="h-4 w-4" aria-hidden="true" /> Compartilhar minha localização
                </>
              )}
            </Button>

            {/* O GPS leva alguns segundos pra sair da posição aproximada da rede e chegar na
                precisa - sem mostrar esse progresso, a espera parece travamento e o cliente
                desiste (ou confirma um ponto ruim). */}
            {step === "locating" ? (
              <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                {refiningAccuracy !== null ? (
                  <p>
                    Melhorando a precisão... no momento: <strong>{formatAccuracy(refiningAccuracy)}</strong>
                  </p>
                ) : (
                  <p>Procurando sinal de GPS... mantenha a tela aberta por alguns segundos.</p>
                )}
              </div>
            ) : null}

            {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}
            {permissionDenied ? <LocationHelpGuide defaultOpen /> : null}
          </div>
        ) : null}

        {(step === "review" || step === "confirming") && position && gpsFix ? (
          <div className="flex flex-1 flex-col gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-slate-950">Localização encontrada</p>
              <p className="text-xs text-slate-500">Arraste o marcador ou toque no mapa para ajustar.</p>
              {adjustedManually ? <p className="mt-1 text-xs font-medium text-amber-700">Posição ajustada manualmente.</p> : null}
            </div>

            {banner ? <div className={`rounded-xl border px-3 py-2 text-xs ${banner.className}`}>{banner.text}</div> : null}
            {/* Com precisão ruim o guia é tão útil quanto na negação de permissão - normalmente é
                a "localização precisa" do aparelho que está desligada, ou o navegador embutido do
                app de mensagem, que não acessa o GPS. */}
            {blockedByAccuracy ? (
              <>
                {isInAppBrowser() ? <InAppBrowserWarning /> : null}
                <LocationHelpGuide defaultOpen />
              </>
            ) : null}

            <div className="isolate h-72 overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
              <LocalizaPickerMapLeaflet
                key={attempt}
                latitude={position.latitude}
                longitude={position.longitude}
                accuracyMeters={gpsFix.accuracy}
                onChange={handleMarkerMoved}
              />
            </div>

            {error ? <p className="text-sm text-rose-600">{error}</p> : null}

            <div className="grid gap-2">
              {blockedByAccuracy ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                  Não dá para confirmar com esta precisão - a equipe não conseguiria achar o endereço. Ative a
                  localização precisa e toque em &quot;Tentar localizar novamente&quot;, <strong>ou</strong> arraste o
                  marcador no mapa até o ponto exato.
                </p>
              ) : null}
              <Button onClick={confirmLocation} disabled={step === "confirming" || blockedByAccuracy}>
                {step === "confirming" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Enviando...
                  </>
                ) : (
                  "Confirmar localização"
                )}
              </Button>
              <Button variant="outline" onClick={shareLocation} disabled={step === "confirming"}>
                <RotateCcw className="h-4 w-4" aria-hidden="true" /> Tentar localizar novamente
              </Button>
            </div>
          </div>
        ) : null}

        {step === "success" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
            <CheckCircle2 className="h-8 w-8 text-emerald-600" aria-hidden="true" />
            <p className="text-base font-semibold text-emerald-900">Localização enviada com sucesso.</p>
            <p className="text-sm text-emerald-700">Obrigado! O atendimento já pode seguir com a posição confirmada.</p>
          </div>
        ) : null}
      </div>
    </main>
  );
}
