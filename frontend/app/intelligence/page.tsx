"use client";

import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  BellRing,
  ExternalLink,
  Home,
  LogOut,
  MonitorCog,
  Newspaper,
  Radar,
  RefreshCw,
  Settings2,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionCard } from "@/components/ui/section-card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { MultiSelect } from "@/components/ui/multi-select";
import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import type { Tone } from "@/lib/tones";
import {
  intelligenceCockpitApi,
  type AdminContent,
  type AdminProfile,
  type FilterCatalog,
  type IntelligenceAlert,
  type IntelligenceAlertDetail,
  type MonitorInfo,
  type WidgetEntry,
} from "@/lib/intelligence-cockpit-api";

const FALLBACK_PROFILES = [
  { key: "uni-geral", name: "UNI Geral" },
  { key: "machadinho-operacional", name: "Machadinho Operacional" },
  { key: "executivo-uni", name: "Executivo UNI" },
];

const SCOPE_FIELDS = ["regionals", "cities", "sectors", "os_subjects", "team_models", "responsibles"] as const;

const FIELD_LABELS: Record<string, string> = {
  regionals: "Regionais",
  cities: "Cidades",
  sectors: "Setores",
  os_subjects: "Assuntos de O.S.",
  team_models: "Modelos de equipe",
  responsibles: "Responsáveis",
  content_type: "Tipo de conteúdo",
  severity: "Severidade",
  status: "Status",
};

const CONTENT_TYPES = ["AI_INSIGHT", "MANUAL_MESSAGE", "ANNOUNCEMENT", "OPERATIONAL_PRIORITY", "INCIDENT_UPDATE", "MAINTENANCE_NOTICE", "INFO"];
const SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
const ALERT_STATUSES = ["ACTIVE", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"];

function severityTone(severity: string): Tone {
  if (severity === "CRITICAL") return "red";
  if (severity === "HIGH") return "amber";
  if (severity === "MEDIUM") return "blue";
  return "slate";
}

function csv(values: string[]) {
  return values.join(", ");
}

function parseCsv(text: string) {
  return text
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function optionsForField(field: string, catalog: FilterCatalog | null): string[] | null {
  if (!catalog) return null;
  if (field === "regionals") return catalog.regionals;
  if (field === "sectors") return catalog.sectors;
  if (field === "os_subjects") return catalog.os_subjects;
  if (field === "team_models") return catalog.team_models;
  if (field === "content_type") return catalog.content_types;
  if (field === "severity") return catalog.content_severities;
  return null;
}

function FilterValuesEditor({
  field,
  values,
  options,
  onChange,
}: {
  field: string;
  values: string[];
  options: string[] | null;
  onChange: (values: string[]) => void;
}) {
  if (options && options.length) {
    return <MultiSelect values={values} options={options} ariaLabel={FIELD_LABELS[field] ?? field} onChange={onChange} />;
  }
  return <Input defaultValue={csv(values)} placeholder="valor1, valor2" onBlur={(event) => onChange(parseCsv(event.target.value))} />;
}

export default function IntelligencePage() {
  const { user, checking, error: authError, login, logout } = useWorkspaceAuth();
  const [tab, setTab] = useState("cockpit");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canRead = Boolean(user?.permissions.includes("intelligence:read"));
  const canManage = Boolean(user?.permissions.includes("intelligence:manage"));
  const canPublish = Boolean(user?.permissions.includes("intelligence:publish"));

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando UNI Intelligence...</main>;
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;

  if (!canRead) {
    return (
      <main className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-xl font-semibold">Acesso ao UNI Intelligence necessário</h1>
          <p className="mt-2 text-sm">Seu usuário não possui permissão intelligence:read.</p>
          <Link href="/" className="mt-4 inline-flex text-sm font-semibold text-amber-800">Voltar ao ecossistema</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
          <div className="flex items-center gap-3">
            <Link href="/" aria-label="Voltar ao ecossistema" className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Workspace</p>
              <h1 className="text-base font-semibold text-slate-950">UNI Intelligence</h1>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <Button type="button" variant="ghost" onClick={logout}><LogOut className="h-4 w-4" /> Sair</Button>
          </div>
        </div>
      </header>

      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <section className="px-4 py-6 lg:px-7">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-auto flex-wrap">
            <TabsTrigger value="cockpit"><Radar className="mr-1.5 h-4 w-4" /> Cockpit</TabsTrigger>
            <TabsTrigger value="alertas"><BellRing className="mr-1.5 h-4 w-4" /> Alertas/Incidentes</TabsTrigger>
            {canManage ? <TabsTrigger value="publicacoes"><Newspaper className="mr-1.5 h-4 w-4" /> Publicações</TabsTrigger> : null}
            {canManage ? <TabsTrigger value="profiles"><Settings2 className="mr-1.5 h-4 w-4" /> Profiles</TabsTrigger> : null}
            {canManage ? <TabsTrigger value="monitores"><MonitorCog className="mr-1.5 h-4 w-4" /> Monitores</TabsTrigger> : null}
          </TabsList>

          <TabsContent value="cockpit"><CockpitTab canManage={canManage} /></TabsContent>
          <TabsContent value="alertas"><AlertasTab canManage={canManage} onError={setError} onMessage={setMessage} /></TabsContent>
          {canManage ? (
            <TabsContent value="publicacoes"><PublicacoesTab canPublish={canPublish} onError={setError} onMessage={setMessage} /></TabsContent>
          ) : null}
          {canManage ? (
            <TabsContent value="profiles"><ProfilesTab onError={setError} onMessage={setMessage} /></TabsContent>
          ) : null}
          {canManage ? (
            <TabsContent value="monitores"><MonitoresTab onError={setError} onMessage={setMessage} /></TabsContent>
          ) : null}
        </Tabs>
      </section>
    </main>
  );
}

function CockpitTab({ canManage }: { canManage: boolean }) {
  const [profiles, setProfiles] = useState<Array<{ key: string; name: string; active?: boolean }>>(FALLBACK_PROFILES);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!canManage) return;
    setLoading(true);
    intelligenceCockpitApi
      .listProfiles()
      .then((rows) => setProfiles(rows.map((profile) => ({ key: profile.key, name: profile.name, active: profile.active }))))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [canManage]);

  return (
    <SectionCard
      eyebrow="UNI Intelligence"
      title="Cockpit (TV)"
      subtitle="Abra a TV de cada profile em uma nova aba. Escopo, widgets e filtros ficam na aba Profiles."
    >
      {loading ? <p className="text-sm text-slate-500">Carregando profiles...</p> : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {profiles.map((profile) => (
          <div key={profile.key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-950">{profile.name}</p>
            <p className="mt-1 text-[11px] text-slate-500">{profile.key}</p>
            {profile.active === false ? <Badge className="mt-2 border-slate-200 bg-slate-50 text-slate-500">Inativo</Badge> : null}
            <Link
              href={`/cockpit/${profile.key}`}
              target="_blank"
              className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-blue-700 hover:text-blue-800"
            >
              Abrir TV <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function AlertasTab({
  canManage,
  onError,
  onMessage,
}: {
  canManage: boolean;
  onError: (value: string | null) => void;
  onMessage: (value: string | null) => void;
}) {
  const [items, setItems] = useState<IntelligenceAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [statuses, setStatuses] = useState<string[]>(["ACTIVE"]);
  const [severities, setSeverities] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<IntelligenceAlertDetail | null>(null);

  async function load() {
    setLoading(true);
    try {
      const page = await intelligenceCockpitApi.listAlerts({
        statuses: statuses.length ? statuses : undefined,
        severities: severities.length ? severities : undefined,
        kinds: kinds.length ? kinds : undefined,
        page: 1,
        page_size: 100,
      });
      setItems(page.items);
      setTotal(page.total);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao carregar alertas.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openDetail(id: number) {
    setSelectedId(id);
    setDetail(null);
    try {
      const data = await intelligenceCockpitApi.getAlert(id);
      setDetail(data);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao carregar alerta.");
    }
  }

  async function dismiss(id: number) {
    try {
      const data = await intelligenceCockpitApi.dismissAlert(id);
      setDetail(data);
      onMessage("Alerta descartado.");
      void load();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao descartar alerta.");
    }
  }

  return (
    <div className="grid gap-4">
      <SectionCard eyebrow="UNI Intelligence" title="Alertas e incidentes" subtitle={`${total} registro(s) no filtro atual`}>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <p className="mb-1 text-[11px] font-semibold text-slate-500">Status</p>
            <MultiSelect values={statuses} options={ALERT_STATUSES} ariaLabel="Status" onChange={setStatuses} />
          </div>
          <div>
            <p className="mb-1 text-[11px] font-semibold text-slate-500">Severidade</p>
            <MultiSelect values={severities} options={SEVERITIES.filter((value) => value !== "INFO")} ariaLabel="Severidade" onChange={setSeverities} />
          </div>
          <div>
            <p className="mb-1 text-[11px] font-semibold text-slate-500">Tipo</p>
            <MultiSelect values={kinds} options={["ALERT", "INCIDENT"]} ariaLabel="Tipo" onChange={setKinds} />
          </div>
        </div>
        <Button type="button" className="mt-3" onClick={() => void load()} disabled={loading}>
          <RefreshCw className="h-4 w-4" /> {loading ? "Carregando..." : "Aplicar filtros"}
        </Button>
      </SectionCard>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <Table className="min-w-[840px]">
            <TableHeader>
              <TableRow>
                <TableHead>Detectado</TableHead>
                <TableHead>Título</TableHead>
                <TableHead>Regional</TableHead>
                <TableHead>Severidade</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((alert) => (
                <TableRow key={alert.id} className="cursor-pointer hover:bg-slate-50" onClick={() => void openDetail(alert.id)}>
                  <TableCell className="whitespace-nowrap text-xs">{new Date(alert.first_detected_at).toLocaleString("pt-BR")}</TableCell>
                  <TableCell className="max-w-72 truncate font-medium text-slate-900" title={alert.title}>{alert.title}</TableCell>
                  <TableCell>{alert.regional ?? "-"}</TableCell>
                  <TableCell><StatusBadge tone={severityTone(alert.severity)}>{alert.severity}</StatusBadge></TableCell>
                  <TableCell>{alert.status}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        void openDetail(alert.id);
                      }}
                    >
                      Detalhe
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!items.length && !loading ? (
                <TableRow><TableCell colSpan={6} className="py-8 text-center text-sm text-slate-500">Nenhum alerta para o filtro atual.</TableCell></TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>

      <Sheet
        open={selectedId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedId(null);
            setDetail(null);
          }
        }}
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{detail?.title ?? "Detalhe do alerta"}</SheetTitle>
            <SheetDescription>{detail ? `${detail.alert_type} · ${detail.monitor_key}` : "Carregando..."}</SheetDescription>
          </SheetHeader>
          {detail ? (
            <div className="mt-4 grid gap-3 text-sm">
              <p className="text-slate-700">{detail.summary}</p>
              {detail.recommended_action ? (
                <p className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-blue-800">
                  <strong>Ação recomendada:</strong> {detail.recommended_action}
                </p>
              ) : null}
              <div className="grid grid-cols-2 gap-3 text-xs text-slate-600">
                <span>Regional: {detail.regional ?? "-"}</span>
                <span>Confiança: {detail.confidence != null ? `${Math.round(detail.confidence * 100)}%` : "-"}</span>
                <span>Primeira detecção: {new Date(detail.first_detected_at).toLocaleString("pt-BR")}</span>
                <span>Última observação: {new Date(detail.last_seen_at).toLocaleString("pt-BR")}</span>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Linha do tempo</p>
                <div className="space-y-2">
                  {detail.events.map((event) => (
                    <div key={event.id} className="rounded-lg border border-slate-200 p-2 text-xs">
                      <p className="font-semibold text-slate-800">{event.event_type}</p>
                      <p className="text-slate-500">{new Date(event.created_at).toLocaleString("pt-BR")}</p>
                    </div>
                  ))}
                  {!detail.events.length ? <p className="text-xs text-slate-500">Sem eventos registrados.</p> : null}
                </div>
              </div>
              {canManage && detail.status === "ACTIVE" ? (
                <Button type="button" variant="outline" onClick={() => void dismiss(detail.id)}>Descartar alerta</Button>
              ) : null}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">Carregando...</p>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function PublicacoesTab({
  canPublish,
  onError,
  onMessage,
}: {
  canPublish: boolean;
  onError: (value: string | null) => void;
  onMessage: (value: string | null) => void;
}) {
  const [items, setItems] = useState<AdminContent[]>([]);
  const [profiles, setProfiles] = useState<AdminProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [form, setForm] = useState({ content_type: "MANUAL_MESSAGE", profile_key: "", title: "", body: "", severity: "INFO", valid_until: "" });
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [rows, profileRows] = await Promise.all([
        intelligenceCockpitApi.listAdminContent(statusFilter ? { status: statusFilter } : {}),
        intelligenceCockpitApi.listProfiles(),
      ]);
      setItems(rows);
      setProfiles(profileRows);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao carregar publicações.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function submit() {
    if (!form.title.trim() || !form.body.trim()) {
      onError("Título e corpo são obrigatórios.");
      return;
    }
    setSubmitting(true);
    try {
      await intelligenceCockpitApi.publishContent({
        content_type: form.content_type,
        profile_key: form.profile_key || null,
        title: form.title,
        body: form.body,
        severity: form.severity,
        valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
      });
      onMessage("Publicação criada.");
      setForm((current) => ({ ...current, title: "", body: "" }));
      void load();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao publicar.");
    } finally {
      setSubmitting(false);
    }
  }

  async function dismissContent(id: number) {
    try {
      await intelligenceCockpitApi.dismissAdminContent(id);
      onMessage("Publicação encerrada.");
      void load();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao encerrar publicação.");
    }
  }

  return (
    <div className="grid gap-4">
      {canPublish ? (
        <SectionCard eyebrow="UNI Intelligence" title="Nova publicação" subtitle="Reaproveita o mesmo conteúdo exibido na TV (intelligence_cockpit_content).">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Tipo</p>
              <select
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                value={form.content_type}
                onChange={(event) => setForm((current) => ({ ...current, content_type: event.target.value }))}
              >
                {CONTENT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Severidade</p>
              <select
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                value={form.severity}
                onChange={(event) => setForm((current) => ({ ...current, severity: event.target.value }))}
              >
                {SEVERITIES.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Destino (profile)</p>
              <select
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                value={form.profile_key}
                onChange={(event) => setForm((current) => ({ ...current, profile_key: event.target.value }))}
              >
                <option value="">Todos os profiles</option>
                {(profiles.length ? profiles : FALLBACK_PROFILES).map((profile) => (
                  <option key={profile.key} value={profile.key}>{profile.name}</option>
                ))}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Válido até (opcional)</p>
              <Input type="datetime-local" value={form.valid_until} onChange={(event) => setForm((current) => ({ ...current, valid_until: event.target.value }))} />
            </div>
            <div className="sm:col-span-2">
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Título</p>
              <Input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="Título curto exibido na TV" />
            </div>
            <div className="sm:col-span-2">
              <p className="mb-1 text-[11px] font-semibold text-slate-500">Mensagem</p>
              <Textarea value={form.body} onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))} rows={4} placeholder="Texto da publicação" />
            </div>
          </div>
          <Button type="button" className="mt-3" onClick={() => void submit()} disabled={submitting}>Publicar</Button>
        </SectionCard>
      ) : null}

      <SectionCard
        eyebrow="UNI Intelligence"
        title="Publicações"
        subtitle={`${items.length} registro(s)`}
        actions={
          <select className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">Todos os status</option>
            <option value="ACTIVE">Ativos</option>
            <option value="DISMISSED">Encerrados</option>
          </select>
        }
      >
        <div className="grid gap-2">
          {loading ? <p className="text-sm text-slate-500">Carregando...</p> : null}
          {!loading && !items.length ? <p className="text-sm text-slate-500">Nenhuma publicação encontrada.</p> : null}
          {items.map((content) => {
            const expired = Boolean(content.valid_until && new Date(content.valid_until).getTime() < Date.now());
            return (
              <div key={content.id} className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className="border-slate-200 bg-slate-50 text-slate-600">{content.content_type}</Badge>
                    <StatusBadge tone={severityTone(content.severity)}>{content.severity}</StatusBadge>
                    <span className="text-[11px] text-slate-500">{content.status}{expired && content.status === "ACTIVE" ? " (expirado)" : ""}</span>
                    <span className="text-[11px] text-slate-400">{content.source_type}</span>
                  </div>
                  <p className="mt-1 font-semibold text-slate-900">{content.title}</p>
                  <p className="mt-1 text-sm text-slate-600">{content.body}</p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Destino: {content.profile_key ?? "todos"} · Criado em {new Date(content.created_at).toLocaleString("pt-BR")}
                  </p>
                </div>
                {content.status === "ACTIVE" ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void dismissContent(content.id)}>
                    <Trash2 className="h-3.5 w-3.5" /> Encerrar
                  </Button>
                ) : null}
              </div>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}

function emptyWidgetEntry(key: string): WidgetEntry {
  return { key, filters: {} };
}

function ProfilesTab({
  onError,
  onMessage,
}: {
  onError: (value: string | null) => void;
  onMessage: (value: string | null) => void;
}) {
  const [profiles, setProfiles] = useState<AdminProfile[]>([]);
  const [catalog, setCatalog] = useState<FilterCatalog | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<AdminProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newName, setNewName] = useState("");

  async function loadAll() {
    setLoading(true);
    try {
      const [profileRows, filterCatalog] = await Promise.all([intelligenceCockpitApi.listProfiles(), intelligenceCockpitApi.getFilterCatalog()]);
      setProfiles(profileRows);
      setCatalog(filterCatalog);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao carregar profiles.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectProfile(key: string) {
    const profile = profiles.find((item) => item.key === key) ?? null;
    setSelectedKey(key);
    setDraft(
      profile
        ? { ...profile, scope: { ...profile.scope }, widgets: profile.widgets.map((widget) => ({ key: widget.key, filters: { ...widget.filters } })) }
        : null,
    );
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      const updated = await intelligenceCockpitApi.updateProfile(draft.key, {
        name: draft.name,
        purpose: draft.purpose,
        scope: draft.scope,
        widgets: draft.widgets,
        refresh_seconds: draft.refresh_seconds,
        active: draft.active,
      });
      onMessage("Profile salvo.");
      setProfiles((current) => current.map((profile) => (profile.key === updated.key ? updated : profile)));
      setDraft({ ...updated, scope: { ...updated.scope }, widgets: updated.widgets.map((widget) => ({ key: widget.key, filters: { ...widget.filters } })) });
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao salvar profile.");
    } finally {
      setSaving(false);
    }
  }

  async function createProfile() {
    if (!newKey.trim() || !newName.trim()) {
      onError("Key e nome são obrigatórios para criar um profile.");
      return;
    }
    setCreating(true);
    try {
      const created = await intelligenceCockpitApi.createProfile({
        key: newKey.trim(),
        name: newName.trim(),
        purpose: "REGIONAL_TV",
        scope: { regionals: [] },
        widgets: [],
        active: true,
      });
      onMessage("Profile criado.");
      setNewKey("");
      setNewName("");
      setProfiles((current) => [...current, created]);
      selectProfile(created.key);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao criar profile.");
    } finally {
      setCreating(false);
    }
  }

  function updateScopeField(field: string, values: string[]) {
    setDraft((current) => (current ? { ...current, scope: { ...current.scope, [field]: values } } : current));
  }

  function moveWidget(index: number, direction: -1 | 1) {
    setDraft((current) => {
      if (!current) return current;
      const widgets = [...current.widgets];
      const target = index + direction;
      if (target < 0 || target >= widgets.length) return current;
      [widgets[index], widgets[target]] = [widgets[target], widgets[index]];
      return { ...current, widgets };
    });
  }

  function toggleWidget(key: string, enabled: boolean) {
    setDraft((current) => {
      if (!current) return current;
      if (enabled) return { ...current, widgets: [...current.widgets, emptyWidgetEntry(key)] };
      return { ...current, widgets: current.widgets.filter((widget) => widget.key !== key) };
    });
  }

  function updateWidgetFilter(widgetKey: string, field: string, values: string[]) {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        widgets: current.widgets.map((widget) => {
          if (widget.key !== widgetKey) return widget;
          const filters = { ...widget.filters };
          if (values.length) filters[field] = values;
          else delete filters[field];
          return { ...widget, filters };
        }),
      };
    });
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <SectionCard eyebrow="UNI Intelligence" title="Profiles" subtitle={loading ? "Carregando..." : `${profiles.length} profile(s)`}>
        <div className="grid gap-2">
          {profiles.map((profile) => (
            <button
              key={profile.key}
              type="button"
              onClick={() => selectProfile(profile.key)}
              className={`rounded-lg border px-3 py-2 text-left text-sm ${
                selectedKey === profile.key ? "border-uni-royal bg-uni-royal/5 text-uni-royal" : "border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <p className="font-semibold">{profile.name}</p>
              <p className="text-[11px] text-slate-500">{profile.key} · {profile.active ? "ativo" : "inativo"}</p>
            </button>
          ))}
        </div>
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
          <p className="text-[11px] font-semibold text-slate-500">Novo profile</p>
          <Input value={newKey} onChange={(event) => setNewKey(event.target.value)} placeholder="key (ex.: regional-xyz)" />
          <Input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Nome de exibição" />
          <Button type="button" size="sm" variant="outline" onClick={() => void createProfile()} disabled={creating}>Criar profile</Button>
        </div>
      </SectionCard>

      {draft ? (
        <div className="grid gap-4">
          <SectionCard
            eyebrow="Profile"
            title={draft.name}
            subtitle={draft.key}
            actions={<Button type="button" onClick={() => void save()} disabled={saving}>{saving ? "Salvando..." : "Salvar"}</Button>}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-[11px] font-semibold text-slate-500">Nome</p>
                <Input value={draft.name} onChange={(event) => setDraft((current) => (current ? { ...current, name: event.target.value } : current))} />
              </div>
              <div>
                <p className="mb-1 text-[11px] font-semibold text-slate-500">Finalidade</p>
                <select
                  className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                  value={draft.purpose}
                  onChange={(event) => setDraft((current) => (current ? { ...current, purpose: event.target.value } : current))}
                >
                  {(catalog?.profile_purposes ?? [draft.purpose]).map((purpose) => <option key={purpose} value={purpose}>{purpose}</option>)}
                </select>
              </div>
              <div>
                <p className="mb-1 text-[11px] font-semibold text-slate-500">Atualização (segundos)</p>
                <Input
                  type="number"
                  min={15}
                  value={draft.refresh_seconds}
                  onChange={(event) => setDraft((current) => (current ? { ...current, refresh_seconds: Number(event.target.value) } : current))}
                />
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input
                  type="checkbox"
                  id="profile-active"
                  checked={draft.active}
                  onChange={(event) => setDraft((current) => (current ? { ...current, active: event.target.checked } : current))}
                />
                <label htmlFor="profile-active" className="text-sm text-slate-700">Profile ativo</label>
              </div>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Escopo base" title="Escopo do profile" subtitle="Filtro base de toda a TV - widgets só podem restringir, nunca ampliar este escopo.">
            <div className="grid gap-3 sm:grid-cols-2">
              {SCOPE_FIELDS.map((field) => (
                <div key={field}>
                  <p className="mb-1 text-[11px] font-semibold text-slate-500">{FIELD_LABELS[field]}</p>
                  <FilterValuesEditor
                    field={field}
                    values={(draft.scope[field] as string[] | undefined) ?? []}
                    options={optionsForField(field, catalog)}
                    onChange={(values) => updateScopeField(field, values)}
                  />
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard eyebrow="Widgets" title="Widgets habilitados" subtitle="Ordem = prioridade de exibição na TV. Cada filtro só restringe o escopo acima.">
            <div className="grid gap-3">
              {(catalog?.widgets ?? []).map((widgetCatalog) => {
                const index = draft.widgets.findIndex((widget) => widget.key === widgetCatalog.key);
                const enabled = index >= 0;
                const entry = enabled ? draft.widgets[index] : null;
                return (
                  <div key={widgetCatalog.key} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <label className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                        <input type="checkbox" checked={enabled} onChange={(event) => toggleWidget(widgetCatalog.key, event.target.checked)} />
                        {widgetCatalog.key}
                      </label>
                      {enabled ? (
                        <div className="flex items-center gap-1">
                          <Button type="button" variant="ghost" size="sm" onClick={() => moveWidget(index, -1)} disabled={index === 0}>
                            <ArrowUp className="h-3.5 w-3.5" />
                          </Button>
                          <Button type="button" variant="ghost" size="sm" onClick={() => moveWidget(index, 1)} disabled={index === draft.widgets.length - 1}>
                            <ArrowDown className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ) : null}
                    </div>
                    {enabled && widgetCatalog.allowed_filters.length ? (
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {widgetCatalog.allowed_filters.map((field) => (
                          <div key={field}>
                            <p className="mb-1 text-[11px] font-semibold text-slate-500">{FIELD_LABELS[field] ?? field}</p>
                            <FilterValuesEditor
                              field={field}
                              values={(entry?.filters[field] as string[] | undefined) ?? []}
                              options={optionsForField(field, catalog)}
                              onChange={(values) => updateWidgetFilter(widgetCatalog.key, field, values)}
                            />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </SectionCard>
        </div>
      ) : (
        <SectionCard eyebrow="UNI Intelligence" title="Selecione um profile" subtitle="Escolha um profile à esquerda para editar escopo e widgets." />
      )}
    </div>
  );
}

function MonitoresTab({
  onError,
  onMessage,
}: {
  onError: (value: string | null) => void;
  onMessage: (value: string | null) => void;
}) {
  const [monitors, setMonitors] = useState<MonitorInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await intelligenceCockpitApi.listMonitors();
      setMonitors(data.items);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao carregar monitores.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function updateMonitor(monitor: MonitorInfo, patch: { enabled?: boolean; interval_minutes?: number; resolve_after_misses?: number }) {
    setSavingKey(monitor.key);
    try {
      const updated = await intelligenceCockpitApi.updateMonitor(monitor.key, patch);
      setMonitors((current) => current.map((item) => (item.key === updated.key ? updated : item)));
      onMessage(`Monitor ${monitor.name} atualizado.`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Falha ao atualizar monitor.");
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <SectionCard eyebrow="UNI Intelligence" title="Monitores" subtitle={loading ? "Carregando..." : `${monitors.length} monitor(es)`}>
      <div className="overflow-x-auto">
        <Table className="min-w-[860px]">
          <TableHeader>
            <TableRow>
              <TableHead>Monitor</TableHead>
              <TableHead>Ativo</TableHead>
              <TableHead>Intervalo (min)</TableHead>
              <TableHead>Falhas p/ resolver</TableHead>
              <TableHead>Última execução</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Falhas seguidas</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {monitors.map((monitor) => (
              <TableRow key={monitor.key}>
                <TableCell>
                  <p className="font-medium text-slate-900">{monitor.name}</p>
                  <p className="text-[11px] text-slate-500">{monitor.description}</p>
                </TableCell>
                <TableCell>
                  <input
                    type="checkbox"
                    checked={monitor.enabled}
                    disabled={savingKey === monitor.key}
                    onChange={(event) => void updateMonitor(monitor, { enabled: event.target.checked })}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={1}
                    max={1440}
                    defaultValue={monitor.interval_minutes}
                    className="h-8 w-24"
                    onBlur={(event) => {
                      const value = Number(event.target.value);
                      if (value && value !== monitor.interval_minutes) void updateMonitor(monitor, { interval_minutes: value });
                    }}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={1}
                    defaultValue={monitor.resolve_after_misses}
                    className="h-8 w-20"
                    onBlur={(event) => {
                      const value = Number(event.target.value);
                      if (value && value !== monitor.resolve_after_misses) void updateMonitor(monitor, { resolve_after_misses: value });
                    }}
                  />
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {monitor.last_run_at ? new Date(monitor.last_run_at).toLocaleString("pt-BR") : "nunca"}
                </TableCell>
                <TableCell className="text-xs">{monitor.last_run_status ?? "-"}</TableCell>
                <TableCell className="text-right tabular-nums">{monitor.consecutive_failures}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </SectionCard>
  );
}
