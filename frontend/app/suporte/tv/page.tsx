"use client";

import { Minus, Moon, Plus, Settings, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { TvConfigDialog } from "@/components/support-tv/tv-config-dialog";
import { TvHourlyChart } from "@/components/support-tv/tv-hourly-chart";
import { TvKpiStrip } from "@/components/support-tv/tv-kpi-strip";
import { TvAttendantsPanel, TvReasonsPanel } from "@/components/support-tv/tv-panels";
import { TvPresencePanel } from "@/components/support-tv/tv-presence";
import { TvNextUpdate } from "@/components/support-tv/tv-next-update";
import { TvN1Chip, TvRadarPanel } from "@/components/support-tv/tv-radar";
import { TV_CLASSES, type TvStatus, type TvTheme } from "@/components/support-tv/tv-theme";
import { RedirectToWorkspaceHome } from "@/components/workspace/redirect-to-home";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { fetchSupportTvPresence, fetchSupportTvSnapshot, type SupportTvPresence, type SupportTvSnapshot } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";

const REFRESH_SECONDS = 30;
// Presença muda em segundos (entrou numa ligação, saiu para pausa): ciclo próprio, mais curto.
const PRESENCE_REFRESH_SECONDS = 10;
const SUPPORT_TIMEZONE = "America/Porto_Velho";
// Sincronização do OPA: acima disso o dado da TV já pode estar atrasado em relação ao painel oficial.
const SYNC_ATTENTION_MINUTES = 30;
const SYNC_CRITICAL_MINUTES = 60;
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 1.4;
const ZOOM_STEP = 0.1;
const THEME_KEY = "uni-support-tv-theme";
const ZOOM_KEY = "uni-support-tv-zoom";

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Armazenamento bloqueado: a preferência só não persiste, a TV segue funcionando.
  }
}

function formatClock(date: Date | null): string {
  if (!date) return "--:--";
  return date.toLocaleTimeString("pt-BR", { timeZone: SUPPORT_TIMEZONE, hour: "2-digit", minute: "2-digit" });
}

function formatClockWithSeconds(date: Date | null): string {
  if (!date) return "--:--:--";
  return date.toLocaleTimeString("pt-BR", { timeZone: SUPPORT_TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatLongDate(date: Date): string {
  const text = date.toLocaleDateString("pt-BR", { timeZone: SUPPORT_TIMEZONE, weekday: "long", day: "numeric", month: "long" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function syncChip(snapshot: SupportTvSnapshot | null, now: Date): { text: string; status: TvStatus } {
  if (!snapshot) return { text: "Sincronização do OPA: aguardando dados", status: "neutral" };
  const { last_success_at: lastSuccess, consecutive_failures: failures } = snapshot.sync;
  if (!lastSuccess) return { text: "Sincronização do OPA: sem registro", status: "attention" };
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(lastSuccess).getTime()) / 60_000));
  const age = minutes < 1 ? "agora" : minutes < 60 ? `há ${minutes} min` : `há ${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
  const status: TvStatus = minutes >= SYNC_CRITICAL_MINUTES ? "critical" : minutes >= SYNC_ATTENTION_MINUTES || failures > 0 ? "attention" : "ok";
  return { text: `Dados do OPA atualizados ${age}${failures > 0 ? ` · ${failures} falha(s) seguidas` : ""}`, status };
}

// Item da grade: no celular/tablet cada bloco tem sua ordem de leitura (o que a gestão precisa ver
// primeiro vem antes); na TV (xl) vale a ordem do DOM e a grade fixa de 4 colunas.
function Slot({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("flex min-h-0 flex-col [&>section]:min-h-0 [&>section]:flex-1", className)}>{children}</div>;
}

export default function SupportTvPage() {
  const { user, checking } = useWorkspaceAuth();
  const [snapshot, setSnapshot] = useState<SupportTvSnapshot | null>(null);
  const [presence, setPresence] = useState<SupportTvPresence | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  // Quando o próximo ciclo vai buscar dados (mostrado no cabeçalho, com contagem regressiva).
  const [nextRefreshAt, setNextRefreshAt] = useState<Date | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [theme, setTheme] = useState<TvTheme>("dark");
  const [zoom, setZoom] = useState(1);
  const [configOpen, setConfigOpen] = useState(false);
  // Muda quando a configuração é salva: reinicia o ciclo de atualização já com o novo recorte.
  const [reloadToken, setReloadToken] = useState(0);
  const requestRef = useRef(0);

  const canRead = Boolean(user?.permissions.includes("support:read"));
  // A conta da TV só lê; configurar o recorte é da gestão (mesma permissão da configuração do módulo).
  const canConfigure = Boolean(user?.permissions.includes("support:sync_opa"));

  useEffect(() => {
    if (!user || !canRead) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      const requestId = ++requestRef.current;
      try {
        const data = await fetchSupportTvSnapshot();
        if (cancelled || requestId !== requestRef.current) return;
        setSnapshot(data);
        setFetchError(null);
        setLastUpdatedAt(new Date());
      } catch (reason) {
        if (cancelled || requestId !== requestRef.current) return;
        // Mantém o último dado válido na tela - nunca zera fingindo que a operação está parada.
        setFetchError(reason instanceof Error ? reason.message : "Não foi possível atualizar os dados agora.");
      }
      if (!cancelled) {
        setNextRefreshAt(new Date(Date.now() + REFRESH_SECONDS * 1000));
        timer = setTimeout(tick, REFRESH_SECONDS * 1000);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [user, canRead, reloadToken]);

  // Presença dos atendentes: ciclo independente do snapshot. Falha aqui não derruba o resto - o
  // painel só mostra o último dado (ou "Indisponível" se nunca carregou).
  useEffect(() => {
    if (!user || !canRead) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const data = await fetchSupportTvPresence();
        if (!cancelled) setPresence(data);
      } catch {
        // mantém o último valor válido
      }
      if (!cancelled) timer = setTimeout(tick, PRESENCE_REFRESH_SECONDS * 1000);
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [user, canRead, reloadToken]);

  // Relógio e idade da sincronização andam mesmo entre duas atualizações de dado.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const storedTheme = readStorage(THEME_KEY);
    if (storedTheme === "light" || storedTheme === "dark") setTheme(storedTheme);
    const storedZoom = Number(readStorage(ZOOM_KEY));
    if (storedZoom >= ZOOM_MIN && storedZoom <= ZOOM_MAX) setZoom(storedZoom);
  }, []);

  function changeTheme(next: TvTheme) {
    setTheme(next);
    writeStorage(THEME_KEY, next);
  }

  function changeZoom(next: number) {
    const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(next * 100) / 100));
    setZoom(clamped);
    writeStorage(ZOOM_KEY, String(clamped));
  }

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">Carregando UNI Workspace...</main>;
  }
  if (!user) return <RedirectToWorkspaceHome />;
  if (!canRead) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-8 text-center text-slate-600">
        Acesso não autorizado — esta conta não tem permissão para o Suporte Interno.
      </main>
    );
  }

  const t = TV_CLASSES[theme];
  const sync = syncChip(snapshot, now);
  const buttonClass = t.control;

  return (
    <main style={{ zoom }} className={cn("flex min-h-screen w-full flex-col gap-4 p-4 md:p-6 xl:h-screen xl:w-screen xl:overflow-hidden xl:p-6", t.page)}>
      <header className="flex flex-shrink-0 flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className={cn("flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em]", t.label)}>
            <span className="h-2 w-2 rounded-sm bg-uni-turquoise" aria-hidden="true" />
            UNI Internet
          </p>
          <h1 className={cn("text-3xl font-bold tracking-tight", t.title)}>Suporte Interno</h1>
          <p className={cn("mt-1 text-base", t.muted)}>{formatLongDate(now)}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 xl:flex-nowrap xl:gap-4">
          <TvN1Chip data={snapshot?.n1 ?? null} theme={theme} />
          <span className={cn("inline-flex items-center gap-2.5 rounded-full px-4 py-1.5 text-base font-medium", t.chip)}>
            <span className={cn("h-2.5 w-2.5 rounded-full", t.status[sync.status].dot, sync.status === "ok" && "tv-live")} aria-hidden="true" />
            {sync.text}
          </span>
          <div className="xl:text-right">
            <p className={cn("text-4xl font-bold leading-none tracking-tight tabular-nums", t.value)} aria-label="Hora atual">
              {formatClock(now)}
            </p>
            {/* Hora (com segundos) da última carga bem-sucedida: permite conferir a olho que a TV
                está mesmo atualizando. O destaque rápido a cada carga confirma a troca sem chamar atenção. */}
            <p key={lastUpdatedAt?.getTime() ?? 0} className={cn("tv-flash mt-1.5 inline-block text-sm tabular-nums", t.muted)} data-testid="tv-last-update">
              Atualizado às {formatClockWithSeconds(lastUpdatedAt)}
            </p>
            <TvNextUpdate at={nextRefreshAt} theme={theme} />
          </div>
          <div className="flex items-center gap-1.5">
            {/* Zoom só faz sentido na TV; no celular a página já se ajusta sozinha. */}
            <div className="hidden items-center gap-1.5 xl:flex">
              <button type="button" className={buttonClass} onClick={() => changeZoom(zoom - ZOOM_STEP)} disabled={zoom <= ZOOM_MIN} aria-label="Diminuir zoom">
                <Minus className="h-4 w-4" aria-hidden="true" />
              </button>
              <button type="button" className={buttonClass} onClick={() => changeZoom(1)} aria-label="Redefinir zoom para 100%">
                {Math.round(zoom * 100)}%
              </button>
              <button type="button" className={buttonClass} onClick={() => changeZoom(zoom + ZOOM_STEP)} disabled={zoom >= ZOOM_MAX} aria-label="Aumentar zoom">
                <Plus className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <button type="button" className={buttonClass} onClick={() => changeTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}>
              {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
            </button>
            {canConfigure && (
              <button type="button" className={buttonClass} onClick={() => setConfigOpen(true)} aria-label="Configurar a TV">
                <Settings className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </header>

      {fetchError && (
        <div className="flex-shrink-0 rounded-lg bg-amber-500/15 px-4 py-2.5 text-base font-medium text-amber-300 ring-1 ring-inset ring-amber-400/60" role="status">
          Atualização falhou — {snapshot ? `mostrando o último dado válido (${formatClock(lastUpdatedAt)}).` : "aguardando a primeira carga."} {fetchError}
        </div>
      )}

      {!snapshot ? (
        <div className={cn("flex flex-1 items-center justify-center py-20 text-2xl", t.muted)}>{fetchError ? "Não foi possível carregar o painel." : "Carregando painel..."}</div>
      ) : (
        <>
          <div className="flex-shrink-0">
            <TvKpiStrip kpis={snapshot.kpis} theme={theme} />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:min-h-0 xl:flex-1 xl:grid-cols-4 xl:grid-rows-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            {/* Sem o bloco Bot e humano, o ritmo por hora ocupa as 3 colunas que sobraram ao lado do radar. */}
            <Slot className="max-xl:order-3 md:col-span-2 xl:col-span-3">
              <TvHourlyChart hourly={snapshot.hourly} theme={theme} />
            </Slot>
            <Slot className="max-xl:order-2">
              <TvRadarPanel radar={snapshot.radar} theme={theme} />
            </Slot>

            <Slot className="max-xl:order-6 md:col-span-2">
              <TvAttendantsPanel items={snapshot.attendants} theme={theme} />
            </Slot>
            <Slot className="max-xl:order-5">
              <TvReasonsPanel reasons={snapshot.top_reasons} channels={snapshot.channels} theme={theme} />
            </Slot>
            <Slot className="max-xl:order-1">
              <TvPresencePanel presence={presence} theme={theme} />
            </Slot>
          </div>
        </>
      )}
      {canConfigure && <TvConfigDialog open={configOpen} onOpenChange={setConfigOpen} onSaved={() => setReloadToken((value) => value + 1)} />}

      {/* Microinteração: tudo sutil e desligado para quem pede menos movimento (WCAG 2.3.3). */}
      <style jsx global>{`
        @keyframes tv-reveal {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: none; }
        }
        @keyframes tv-live {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.45; transform: scale(1.3); }
        }
        @keyframes tv-flash {
          from { background-color: rgba(39, 217, 191, 0.4); }
          to { background-color: rgba(39, 217, 191, 0); }
        }
        .tv-reveal { animation: tv-reveal 0.55s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
        .tv-live { animation: tv-live 2.4s ease-in-out infinite; }
        .tv-flash { animation: tv-flash 1.4s ease-out; border-radius: 6px; }
        @media (prefers-reduced-motion: reduce) {
          .tv-reveal, .tv-live, .tv-flash { animation: none; }
        }
      `}</style>
    </main>
  );
}
