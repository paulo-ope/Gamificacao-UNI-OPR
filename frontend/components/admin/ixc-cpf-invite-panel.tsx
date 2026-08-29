"use client";

import { AlertTriangle, Building2, CheckCircle2, IdCard, Loader2, Mail, Phone, Search, ShieldCheck, UserPlus, UserRound } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { formatCpf, isValidCpf, onlyDigits } from "@/lib/masks";
import type { AdminPersonStructure, IxcCpfLookupResult, PortalInvite, PortalInviteCreateResult } from "@/lib/types";

type LookupState = "idle" | "loading" | "found" | "not_found" | "error";

type Props = {
  people: AdminPersonStructure[];
  invites: PortalInvite[];
  onInviteCreated: (result: PortalInviteCreateResult) => void;
};

const MATCH_KIND_LABELS: Record<string, string> = {
  ixc_employee_id: "vínculo confirmado (mesmo funcionário do IXC já usado antes)",
  cpf: "vínculo por CPF já cadastrado",
  name: "sugestão por nome - confirme antes de convidar",
};

export function IxcCpfInvitePanel({ people, invites, onInviteCreated }: Props) {
  const [cpf, setCpf] = useState("");
  const [status, setStatus] = useState<LookupState>("idle");
  const [result, setResult] = useState<IxcCpfLookupResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedCollaboratorId, setSelectedCollaboratorId] = useState("");
  const [email, setEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function reset() {
    setStatus("idle");
    setResult(null);
    setErrorMessage(null);
    setSelectedCollaboratorId("");
    setEmail("");
    setCreateError(null);
  }

  async function handleSearch() {
    if (!isValidCpf(cpf)) {
      setStatus("error");
      setErrorMessage("CPF inválido. Confira os números.");
      return;
    }
    setStatus("loading");
    setErrorMessage(null);
    setCreateError(null);
    try {
      const found = await api.lookupIxcCpf(onlyDigits(cpf));
      setResult(found);
      setSelectedCollaboratorId(found.local_collaborator_id ? String(found.local_collaborator_id) : "");
      setEmail(found.email || "");
      setStatus("found");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Não foi possível consultar o IXC.";
      // `request()` (lib/api.ts) só devolve a mensagem de erro, sem o status HTTP - distinguir
      // "não encontrado" (pra mostrar orientação, não erro) depende do texto exato que
      // `lookup_ixc_cpf_route` devolve em 404 (api/routes/invites.py). Se aquela mensagem mudar,
      // este trecho precisa acompanhar.
      if (message.toLowerCase().includes("nenhum funcionário encontrado")) {
        setStatus("not_found");
      } else {
        setStatus("error");
        setErrorMessage(message);
      }
    }
  }

  async function handleCreateInvite() {
    if (!result || !selectedCollaboratorId || !email.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createInviteFromIxc({
        cpf: onlyDigits(cpf),
        collaborator_id: Number(selectedCollaboratorId),
        email: email.trim(),
      });
      onInviteCreated(created);
      reset();
      setCpf("");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Não foi possível gerar o convite.");
    } finally {
      setCreating(false);
    }
  }

  const unlinkedPeople = people.filter((person) => !person.portal_user_id);
  const linkedCollaborator = result?.local_collaborator_id
    ? people.find((person) => person.id === result.local_collaborator_id)
    : undefined;
  const alreadyHasPortalUser = Boolean(linkedCollaborator?.portal_user_id);
  const pendingInviteForCollaborator = result?.local_collaborator_id
    ? invites.find((invite) => invite.collaborator_id === result.local_collaborator_id && invite.status === "pending")
    : undefined;
  const suggestionUnavailable = Boolean(result?.local_collaborator_id) && !unlinkedPeople.some((p) => p.id === result?.local_collaborator_id);

  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="uni-gradient flex items-center gap-3 p-5 text-white">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/15">
          <IdCard className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Convidar colaborador por CPF</h3>
          <p className="text-sm text-white/80">Busca inteligente no IXC - encontra, confirma e já gera o convite vinculado.</p>
        </div>
      </div>

      <div className="grid gap-5 p-5">
        <div className="grid gap-1.5 sm:max-w-xs">
          <Label htmlFor="ixc-cpf-search">CPF do colaborador</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <IdCard className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                id="ixc-cpf-search"
                className="pl-9"
                inputMode="numeric"
                placeholder="000.000.000-00"
                value={cpf}
                onChange={(event) => {
                  setCpf(formatCpf(event.target.value));
                  if (status !== "idle") reset();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    handleSearch();
                  }
                }}
              />
            </div>
            <Button type="button" disabled={status === "loading" || !cpf.trim()} onClick={handleSearch}>
              {status === "loading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Buscar no IXC
            </Button>
          </div>
        </div>

        {status === "error" ? (
          <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{errorMessage}</p>
          </div>
        ) : null}

        {status === "not_found" ? (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Nenhum funcionário encontrado no IXC para este CPF.</p>
              <p className="mt-1 text-amber-800">Confira se o CPF foi digitado corretamente ou se o cadastro existe no IXC.</p>
            </div>
          </div>
        ) : null}

        {status === "found" && result ? (
          <div className="grid gap-4 rounded-2xl border border-[#2d5fff]/20 bg-[#2d5fff]/5 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-[#0028f3] shadow-sm">
                  <UserRound className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-semibold text-slate-950">{result.name}</p>
                  <p className="text-xs text-slate-500">CPF {result.cpf_masked} · funcionário #{result.ixc_employee_id}</p>
                </div>
              </div>
              <Badge className={result.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600"}>
                {result.active ? "Ativo no IXC" : "Inativo no IXC"}
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
                <Mail className="h-4 w-4 shrink-0 text-slate-400" />
                {result.email || "sem e-mail no IXC"}
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
                <Phone className="h-4 w-4 shrink-0 text-slate-400" />
                {result.phone || "sem telefone no IXC"}
              </div>
            </div>

            {result.local_match_kind ? (
              <div className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                <Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Cadastro local encontrado: <strong>{result.local_collaborator_name}</strong> - {MATCH_KIND_LABELS[result.local_match_kind]}.
                </span>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Nenhum cadastro local correspondente - selecione manualmente o colaborador para vincular.</span>
              </div>
            )}

            {alreadyHasPortalUser ? (
              <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Este colaborador já possui uma conta no Portal - não é possível convidar de novo.</span>
              </div>
            ) : null}
            {pendingInviteForCollaborator ? (
              <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Já existe um convite pendente para este colaborador ({pendingInviteForCollaborator.email}).</span>
              </div>
            ) : null}

            <div className="grid gap-4 border-t border-[#2d5fff]/15 pt-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label>Vincular ao colaborador</Label>
                <select
                  value={selectedCollaboratorId}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setSelectedCollaboratorId(event.target.value)}
                >
                  <option value="">Selecione...</option>
                  {unlinkedPeople.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                      {person.id === result.local_collaborator_id ? " (sugestão)" : ""}
                    </option>
                  ))}
                </select>
                {suggestionUnavailable ? (
                  <p className="text-xs text-amber-700">O colaborador sugerido já tem conta ou convite - escolha outro, se aplicável.</p>
                ) : null}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="ixc-invite-email">E-mail do convite</Label>
                <Input id="ixc-invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
            </div>

            {createError ? <p className="text-xs text-rose-600">{createError}</p> : null}

            <div className="flex justify-end">
              <Button
                type="button"
                disabled={creating || !selectedCollaboratorId || !email.trim() || alreadyHasPortalUser || Boolean(pendingInviteForCollaborator)}
                onClick={handleCreateInvite}
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
                Gerar convite
              </Button>
            </div>
          </div>
        ) : null}

        {status === "idle" ? (
          <p className="flex items-center gap-2 text-xs text-slate-400">
            <ShieldCheck className="h-3.5 w-3.5" /> O CPF nunca aparece completo em nenhuma tela - só os últimos dígitos.
          </p>
        ) : null}
        {status === "found" && result ? (
          <p className="flex items-center gap-2 text-xs text-slate-400">
            <CheckCircle2 className="h-3.5 w-3.5" /> Nada é criado até você confirmar e clicar em "Gerar convite".
          </p>
        ) : null}
      </div>
    </div>
  );
}
