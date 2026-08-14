"use client";

import { Key, Plus, RefreshCw, Save, ScrollText, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  aiGovernanceApi,
  AI_API_TOKEN_SCOPES,
  type AiAccessAuditLog,
  type AiApiKey,
  type AiEndpoint,
  type AiFieldPermission,
  type AiProfileEndpointGrant,
  type AiProfileFieldGrant,
} from "@/lib/ai-governance-api";
import type { AccessProfile, AuthUser } from "@/lib/types";

type SubTab = "endpoints" | "fields" | "profiles" | "tokens" | "logs";

const SUB_TABS: Array<{ value: SubTab; label: string }> = [
  { value: "endpoints", label: "Endpoints" },
  { value: "fields", label: "Campos" },
  { value: "profiles", label: "Perfis" },
  { value: "tokens", label: "Tokens" },
  { value: "logs", label: "Logs" },
];

function formatDateTime(value: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("pt-BR");
  } catch {
    return value;
  }
}

function OnOffBadge({ on }: { on: boolean }) {
  return (
    <Badge className={on ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-500"}>
      {on ? "Ativo" : "Inativo"}
    </Badge>
  );
}

function TogglePill({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-xl border px-3 py-1 text-xs font-medium transition ${
        on ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-500"
      } ${disabled ? "opacity-60" : "hover:bg-slate-50"}`}
    >
      {on ? "Habilitado" : "Desabilitado"}
    </button>
  );
}

export function AiGovernancePanel({ user, profiles }: { user: AuthUser; profiles: AccessProfile[] }) {
  const canWrite = user.permissions.includes("admin:ai_governance:write");
  const canManageTokens = user.permissions.includes("admin:ai_tokens:manage");

  const [subTab, setSubTab] = useState<SubTab>("endpoints");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [endpoints, setEndpoints] = useState<AiEndpoint[]>([]);
  const [fields, setFields] = useState<AiFieldPermission[]>([]);
  const [fieldEntityFilter, setFieldEntityFilter] = useState<string>("");
  const [tokens, setTokens] = useState<AiApiKey[]>([]);
  const [logs, setLogs] = useState<AiAccessAuditLog[]>([]);

  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(profiles[0]?.id ?? null);
  const [endpointGrants, setEndpointGrants] = useState<AiProfileEndpointGrant[]>([]);
  const [fieldGrants, setFieldGrants] = useState<AiProfileFieldGrant[]>([]);

  const [newTokenName, setNewTokenName] = useState("");
  const [newTokenScopes, setNewTokenScopes] = useState<string[]>([]);
  const [newTokenExpiresInDays, setNewTokenExpiresInDays] = useState<string>("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  const fieldEntities = useMemo(() => Array.from(new Set(fields.map((item) => item.entity))).sort(), [fields]);

  async function loadEndpoints() {
    setBusy(true);
    try {
      setEndpoints(await aiGovernanceApi.listEndpoints());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar endpoints.");
    } finally {
      setBusy(false);
    }
  }

  async function loadFields() {
    setBusy(true);
    try {
      setFields(await aiGovernanceApi.listFields());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar campos.");
    } finally {
      setBusy(false);
    }
  }

  async function loadTokens() {
    setBusy(true);
    try {
      setTokens(await aiGovernanceApi.listTokens());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar tokens.");
    } finally {
      setBusy(false);
    }
  }

  async function loadLogs() {
    setBusy(true);
    try {
      setLogs(await aiGovernanceApi.listAuditLogs({ limit: 100 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar logs.");
    } finally {
      setBusy(false);
    }
  }

  async function loadProfileGrants(profileId: number) {
    setBusy(true);
    try {
      const [endpointGrantsResult, fieldGrantsResult] = await Promise.all([
        aiGovernanceApi.listProfileEndpointGrants(profileId),
        aiGovernanceApi.listProfileFieldGrants(profileId),
      ]);
      setEndpointGrants(endpointGrantsResult);
      setFieldGrants(fieldGrantsResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar restrições do perfil.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (subTab === "endpoints" && endpoints.length === 0) void loadEndpoints();
    if (subTab === "fields" && fields.length === 0) void loadFields();
    if (subTab === "tokens" && tokens.length === 0) void loadTokens();
    if (subTab === "logs" && logs.length === 0) void loadLogs();
    if (subTab === "profiles") {
      if (endpoints.length === 0) void loadEndpoints();
      if (fields.length === 0) void loadFields();
      if (selectedProfileId !== null) void loadProfileGrants(selectedProfileId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subTab, selectedProfileId]);

  async function toggleEndpoint(endpoint: AiEndpoint, key: "enabled_api" | "enabled_mcp" | "enabled_ai") {
    if (!canWrite) return;
    setBusy(true);
    try {
      const updated = await aiGovernanceApi.updateEndpoint(endpoint.key, { [key]: !endpoint[key] });
      setEndpoints((current) => current.map((item) => (item.key === updated.key ? updated : item)));
      setMessage(`Endpoint "${updated.label}" atualizado.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar endpoint.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFieldCapability(
    item: AiFieldPermission,
    key: "filterable" | "text_filterable" | "groupable" | "returnable" | "selectable" | "detail_available" | "enabled",
  ) {
    if (!canWrite) return;
    setBusy(true);
    try {
      const updated = await aiGovernanceApi.updateField(item.entity, item.field, { [key]: !item[key] });
      setFields((current) => current.map((row) => (row.entity === updated.entity && row.field === updated.field ? updated : row)));
      setMessage(`Campo "${updated.entity}.${updated.field}" atualizado.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar campo.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleProfileEndpointGrant(endpointKey: string) {
    if (!canWrite || selectedProfileId === null) return;
    const existing = endpointGrants.find((grant) => grant.endpoint_key === endpointKey);
    setBusy(true);
    try {
      if (!existing) {
        const created = await aiGovernanceApi.upsertProfileEndpointGrant(selectedProfileId, endpointKey, false);
        setEndpointGrants((current) => [...current, created]);
      } else if (existing.granted) {
        const updated = await aiGovernanceApi.upsertProfileEndpointGrant(selectedProfileId, endpointKey, false);
        setEndpointGrants((current) => current.map((grant) => (grant.endpoint_key === endpointKey ? updated : grant)));
      } else {
        await aiGovernanceApi.deleteProfileEndpointGrant(selectedProfileId, endpointKey);
        setEndpointGrants((current) => current.filter((grant) => grant.endpoint_key !== endpointKey));
      }
      setMessage("Restrição de perfil atualizada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar restrição.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleProfileFieldGrant(entity: string, field: string) {
    if (!canWrite || selectedProfileId === null) return;
    const existing = fieldGrants.find((grant) => grant.entity === entity && grant.field === field);
    setBusy(true);
    try {
      if (!existing) {
        const created = await aiGovernanceApi.upsertProfileFieldGrant(selectedProfileId, entity, field, false);
        setFieldGrants((current) => [...current, created]);
      } else if (existing.granted) {
        const updated = await aiGovernanceApi.upsertProfileFieldGrant(selectedProfileId, entity, field, false);
        setFieldGrants((current) => current.map((grant) => (grant.entity === entity && grant.field === field ? updated : grant)));
      } else {
        await aiGovernanceApi.deleteProfileFieldGrant(selectedProfileId, entity, field);
        setFieldGrants((current) => current.filter((grant) => !(grant.entity === entity && grant.field === field)));
      }
      setMessage("Restrição de campo do perfil atualizada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar restrição de campo.");
    } finally {
      setBusy(false);
    }
  }

  async function createToken() {
    if (!newTokenName.trim()) {
      setError("Informe um nome para o token.");
      return;
    }
    const expiresInDays = newTokenExpiresInDays.trim() ? Number(newTokenExpiresInDays) : null;
    setBusy(true);
    try {
      const response = await aiGovernanceApi.createToken(newTokenName.trim(), newTokenScopes, expiresInDays);
      setTokens((current) => [response.key, ...current]);
      setRevealedKey(response.raw_key);
      setNewTokenName("");
      setNewTokenScopes([]);
      setNewTokenExpiresInDays("");
      setMessage("Token criado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar token.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeToken(token: AiApiKey) {
    setBusy(true);
    try {
      const updated = await aiGovernanceApi.revokeToken(token.source, token.id);
      setTokens((current) => current.map((item) => (item.source === updated.source && item.id === updated.id ? updated : item)));
      setMessage(`Token "${updated.name}" revogado.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao revogar token.");
    } finally {
      setBusy(false);
    }
  }

  const visibleFields = fieldEntityFilter ? fields.filter((item) => item.entity === fieldEntityFilter) : fields;
  const endpointGrantByKey = new Map(endpointGrants.map((grant) => [grant.endpoint_key, grant]));
  const fieldGrantByKey = new Map(fieldGrants.map((grant) => [`${grant.entity}.${grant.field}`, grant]));

  return (
    <div className="grid gap-4">
      <StatusToast error={error} message={message} busy={busy} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <div className="flex flex-wrap gap-2">
        {SUB_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setSubTab(tab.value)}
            className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${
              subTab === tab.value ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {subTab === "endpoints" ? (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 p-5">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Endpoints e tools</h3>
              <p className="mt-1 text-sm text-slate-500">Habilite/desabilite cada endpoint da API e tool MCP - efeito imediato, sem reiniciar o backend.</p>
            </div>
            <Button type="button" variant="outline" onClick={() => void loadEndpoints()} disabled={busy}>
              <RefreshCw className="h-4 w-4" /> Atualizar
            </Button>
          </div>
          <div className="overflow-x-auto p-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>API</TableHead>
                  <TableHead>MCP</TableHead>
                  <TableHead>IA</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {endpoints.map((endpoint) => (
                  <TableRow key={endpoint.key}>
                    <TableCell>
                      <div className="font-medium text-slate-900">{endpoint.label}</div>
                      <div className="text-xs text-slate-500">{endpoint.key}</div>
                    </TableCell>
                    <TableCell className="text-xs uppercase text-slate-500">{endpoint.kind}</TableCell>
                    <TableCell>
                      <TogglePill on={endpoint.enabled_api} disabled={!canWrite || busy} onClick={() => void toggleEndpoint(endpoint, "enabled_api")} />
                    </TableCell>
                    <TableCell>
                      <TogglePill on={endpoint.enabled_mcp} disabled={!canWrite || busy} onClick={() => void toggleEndpoint(endpoint, "enabled_mcp")} />
                    </TableCell>
                    <TableCell>
                      <TogglePill on={endpoint.enabled_ai} disabled={!canWrite || busy} onClick={() => void toggleEndpoint(endpoint, "enabled_ai")} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}

      {subTab === "fields" ? (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-5">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Campos e capacidades</h3>
              <p className="mt-1 text-sm text-slate-500">Fonte real: introspecção do banco. Desabilitar um campo aqui bloqueia imediatamente API, MCP e IA.</p>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={fieldEntityFilter}
                onChange={(event) => setFieldEntityFilter(event.target.value)}
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                <option value="">Todas as entidades</option>
                {fieldEntities.map((entity) => (
                  <option key={entity} value={entity}>
                    {entity}
                  </option>
                ))}
              </select>
              <Button type="button" variant="outline" onClick={() => void loadFields()} disabled={busy}>
                <RefreshCw className="h-4 w-4" /> Atualizar
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto p-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Campo</TableHead>
                  <TableHead>Filtrável</TableHead>
                  <TableHead>Texto</TableHead>
                  <TableHead>Agrupável</TableHead>
                  <TableHead>Retornável</TableHead>
                  <TableHead>Selecionável</TableHead>
                  <TableHead>Detalhe</TableHead>
                  <TableHead>Sensível</TableHead>
                  <TableHead>Habilitado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleFields.map((item) => (
                  <TableRow key={`${item.entity}.${item.field}`}>
                    <TableCell>
                      <div className="font-medium text-slate-900">{item.field}</div>
                      <div className="text-xs text-slate-500">{item.entity}</div>
                    </TableCell>
                    {(["filterable", "text_filterable", "groupable", "returnable", "selectable", "detail_available"] as const).map((capability) => (
                      <TableCell key={capability}>
                        <TogglePill on={item[capability]} disabled={!canWrite || busy || item.sensitive} onClick={() => void toggleFieldCapability(item, capability)} />
                      </TableCell>
                    ))}
                    <TableCell>{item.sensitive ? <Badge className="border-amber-200 bg-amber-50 text-amber-700">Sensível</Badge> : <span className="text-xs text-slate-400">—</span>}</TableCell>
                    <TableCell>
                      <TogglePill on={item.enabled} disabled={!canWrite || busy} onClick={() => void toggleFieldCapability(item, "enabled")} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {visibleFields.length === 0 && !busy ? <p className="p-4 text-sm text-slate-500">Nenhum campo carregado ainda.</p> : null}
          </div>
        </div>
      ) : null}

      {subTab === "profiles" ? (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-5">
            <h3 className="text-lg font-semibold text-slate-950">Restrições por perfil</h3>
            <p className="mt-1 text-sm text-slate-500">
              Opcional: um perfil sem nenhuma restrição aqui usa só o estado geral de Endpoints/Campos acima. Restringir cria uma allow-list só para este perfil.
            </p>
            <div className="mt-3 max-w-sm">
              <Label>Perfil</Label>
              <select
                value={selectedProfileId ?? ""}
                onChange={(event) => setSelectedProfileId(event.target.value ? Number(event.target.value) : null)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {selectedProfileId !== null ? (
            <div className="grid gap-4 p-5 lg:grid-cols-2">
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-800">Endpoints permitidos</h4>
                <div className="grid gap-1.5">
                  {endpoints.map((endpoint) => {
                    const grant = endpointGrantByKey.get(endpoint.key);
                    const restricted = grant !== undefined && !grant.granted;
                    return (
                      <div key={endpoint.key} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2 text-sm">
                        <span className="text-slate-700">{endpoint.label}</span>
                        <TogglePill on={!restricted} disabled={!canWrite || busy} onClick={() => void toggleProfileEndpointGrant(endpoint.key)} />
                      </div>
                    );
                  })}
                </div>
              </div>
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-800">Campos permitidos</h4>
                <div className="max-h-96 overflow-y-auto grid gap-1.5">
                  {fields.map((item) => {
                    const key = `${item.entity}.${item.field}`;
                    const grant = fieldGrantByKey.get(key);
                    const restricted = grant !== undefined && !grant.granted;
                    return (
                      <div key={key} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2 text-sm">
                        <span className="text-slate-700">{item.field}</span>
                        <TogglePill on={!restricted} disabled={!canWrite || busy} onClick={() => void toggleProfileFieldGrant(item.entity, item.field)} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <p className="p-5 text-sm text-slate-500">Nenhum perfil de acesso disponível.</p>
          )}
        </div>
      ) : null}

      {subTab === "tokens" ? (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 p-5">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Tokens de API</h3>
              <p className="mt-1 text-sm text-slate-500">Chave de acesso de máquina para o conector MCP local/Claude Desktop - sempre exige a permissão ai:query, e opcionalmente um escopo mais fino por token.</p>
            </div>
            <Button type="button" variant="outline" onClick={() => void loadTokens()} disabled={busy}>
              <RefreshCw className="h-4 w-4" /> Atualizar
            </Button>
          </div>
          {canManageTokens ? (
            <div className="grid gap-3 border-b border-slate-200 p-5">
              <div className="flex flex-wrap items-end gap-3">
                <div className="grid gap-2">
                  <Label>Nome do token</Label>
                  <Input value={newTokenName} onChange={(event) => setNewTokenName(event.target.value)} placeholder='Ex.: "Claude Desktop - Fulano"' />
                </div>
                <div className="grid gap-2">
                  <Label>Expira em (dias, opcional)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={newTokenExpiresInDays}
                    onChange={(event) => setNewTokenExpiresInDays(event.target.value)}
                    placeholder="Sem expiração"
                    className="w-40"
                  />
                </div>
                <Button type="button" onClick={() => void createToken()} disabled={busy}>
                  <Plus className="h-4 w-4" /> Emitir token
                </Button>
              </div>
              <div className="grid gap-2">
                <Label>Escopos (opcional - vazio nega busca/detalhe de O.S.; demais tools continuam liberadas por ai:query)</Label>
                <div className="flex flex-wrap gap-2">
                  {AI_API_TOKEN_SCOPES.map((scope) => {
                    const checked = newTokenScopes.includes(scope);
                    return (
                      <button
                        key={scope}
                        type="button"
                        onClick={() =>
                          setNewTokenScopes((current) => (checked ? current.filter((item) => item !== scope) : [...current, scope]))
                        }
                        className={`rounded-lg border px-2.5 py-1 text-xs font-mono transition ${
                          checked ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {scope}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}
          {revealedKey ? (
            <div className="m-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="flex items-center gap-2 font-semibold">
                <Key className="h-4 w-4" /> Copie agora - esta chave não será mostrada de novo:
              </div>
              <code className="mt-2 block break-all rounded-lg bg-white p-2 text-xs">{revealedKey}</code>
              <Button type="button" variant="outline" className="mt-3" onClick={() => setRevealedKey(null)}>
                Já copiei
              </Button>
            </div>
          ) : null}
          <div className="overflow-x-auto p-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Prefixo</TableHead>
                  <TableHead>Proprietário</TableHead>
                  <TableHead>Escopos</TableHead>
                  <TableHead>Expira em</TableHead>
                  <TableHead>Último uso</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {tokens.map((token) => (
                  <TableRow key={`${token.source}-${token.id}`}>
                    <TableCell>
                      {token.name}
                      {token.source === "legacy" ? <span className="ml-1.5 text-xs text-slate-400">(legado)</span> : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{token.key_prefix}***</TableCell>
                    <TableCell className="text-xs text-slate-500">{token.owner_name}</TableCell>
                    <TableCell className="text-xs text-slate-500">
                      {token.scopes === null ? "irrestrito (legado)" : token.scopes.length ? token.scopes.join(", ") : "nenhum"}
                    </TableCell>
                    <TableCell className="text-xs text-slate-500">{token.expires_at ? formatDateTime(token.expires_at) : "—"}</TableCell>
                    <TableCell className="text-xs text-slate-500">{formatDateTime(token.last_used_at)}</TableCell>
                    <TableCell>
                      <OnOffBadge on={token.active} />
                    </TableCell>
                    <TableCell>
                      {token.active && canManageTokens ? (
                        <Button type="button" variant="outline" onClick={() => void revokeToken(token)} disabled={busy}>
                          <Trash2 className="h-4 w-4" /> Revogar
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {tokens.length === 0 && !busy ? <p className="p-4 text-sm text-slate-500">Nenhum token emitido ainda.</p> : null}
          </div>
        </div>
      ) : null}

      {subTab === "logs" ? (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 p-5">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Auditoria de uso (API/MCP)</h3>
              <p className="mt-1 text-sm text-slate-500">Últimas 100 chamadas aos endpoints já governados - quem, quando, o quê, sem valores sensíveis de filtro.</p>
            </div>
            <Button type="button" variant="outline" onClick={() => void loadLogs()} disabled={busy}>
              <RefreshCw className="h-4 w-4" /> Atualizar
            </Button>
          </div>
          <div className="overflow-x-auto p-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quando</TableHead>
                  <TableHead>Usuário</TableHead>
                  <TableHead>Token</TableHead>
                  <TableHead>Origem</TableHead>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>Campos</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead>Duração</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-xs text-slate-500">{formatDateTime(log.occurred_at)}</TableCell>
                    <TableCell className="text-xs text-slate-500">{log.user_name || "—"}</TableCell>
                    <TableCell className="text-xs text-slate-500">{log.token_name || "—"}</TableCell>
                    <TableCell className="text-xs uppercase text-slate-500">{log.origin}</TableCell>
                    <TableCell className="font-mono text-xs">{log.endpoint_key}</TableCell>
                    <TableCell className="text-xs text-slate-500">{log.fields_requested?.length ? log.fields_requested.join(", ") : "todos"}</TableCell>
                    <TableCell className="text-xs text-slate-500">{log.result_count ?? "—"}</TableCell>
                    <TableCell className="text-xs text-slate-500">{log.duration_ms !== null ? `${log.duration_ms}ms` : "—"}</TableCell>
                    <TableCell>
                      <Badge className={log.status === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}>
                        {log.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {logs.length === 0 && !busy ? (
              <p className="flex items-center gap-2 p-4 text-sm text-slate-500">
                <ScrollText className="h-4 w-4" /> Nenhuma chamada registrada ainda.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {!canWrite ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <ShieldCheck className="h-4 w-4" /> Seu perfil só tem leitura (admin:ai_governance:read) - alterações exigem admin:ai_governance:write.
        </div>
      ) : null}
    </div>
  );
}
