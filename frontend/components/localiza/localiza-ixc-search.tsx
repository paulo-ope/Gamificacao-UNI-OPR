"use client";

import { AlertTriangle, IdCard, Loader2, Search, UserRound } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatCpf, isValidCpf, onlyDigits } from "@/lib/masks";
import { localizaApi, type IxcCustomerMatch } from "@/lib/localiza-api";

type Mode = "login" | "cpf";

// Busca ao vivo no IXC pra autopreencher o formulário, em vez do atendente digitar tudo à mão -
// mesmo espírito de `components/admin/ixc-cpf-invite-panel.tsx`, reduzido ao essencial (sem fluxo
// de criação de conta). CPF é o modo padrão (pedido do usuário 2026-09-08: "só colocar o CPF do
// cliente") - login continua disponível pra quando é isso que o atendente tem em mãos.
export function LocalizaIxcSearch({ onSelect }: { onSelect: (match: IxcCustomerMatch) => void }) {
  const [mode, setMode] = useState<Mode>("cpf");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [matches, setMatches] = useState<IxcCustomerMatch[]>([]);

  async function handleSearch() {
    setError(null);
    if (mode === "cpf" && !isValidCpf(query)) {
      setError("CPF inválido. Confira os números.");
      return;
    }
    if (mode === "login" && !query.trim()) {
      setError("Informe o login (número ou texto).");
      return;
    }
    setLoading(true);
    setSearched(false);
    try {
      const result = mode === "login" ? await localizaApi.searchIxcByLogin(query.trim()) : await localizaApi.searchIxcByCpf(onlyDigits(query));
      setMatches(result.matches);
      setSearched(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível consultar o IXC.");
    } finally {
      setLoading(false);
    }
  }

  function handleSelect(match: IxcCustomerMatch) {
    onSelect(match);
    setMatches([]);
    setSearched(false);
    setQuery("");
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-blue-600" aria-hidden="true" />
        <p className="text-sm font-semibold text-slate-950">Buscar cliente no IXC</p>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Encontra o cliente pelo CPF (ou pelo login, se preferir) e preenche nome, identificador e coordenada
        cadastrada automaticamente - sem digitar tudo à mão.
      </p>

      <div className="mt-3 inline-flex rounded-lg border border-slate-200 bg-white p-1">
        <button
          type="button"
          onClick={() => {
            setMode("cpf");
            setError(null);
          }}
          className={`h-8 rounded-md px-3 text-xs font-medium ${mode === "cpf" ? "bg-slate-100 text-slate-950" : "text-slate-500"}`}
        >
          CPF
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError(null);
          }}
          className={`h-8 rounded-md px-3 text-xs font-medium ${mode === "login" ? "bg-slate-100 text-slate-950" : "text-slate-500"}`}
        >
          Login
        </button>
      </div>

      <div className="mt-2 flex gap-2">
        <div className="relative flex-1">
          <IdCard className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
          <Input
            className="pl-8"
            placeholder={mode === "login" ? "Número do login ou login escrito" : "000.000.000-00"}
            value={query}
            onChange={(event) => setQuery(mode === "cpf" ? formatCpf(event.target.value) : event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleSearch();
              }
            }}
          />
        </div>
        <Button type="button" size="sm" disabled={loading || !query.trim()} onClick={handleSearch}>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Search className="h-3.5 w-3.5" aria-hidden="true" />}
          Buscar
        </Button>
      </div>

      {error ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-rose-600">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /> {error}
        </p>
      ) : null}

      {searched && matches.length === 0 ? (
        <p className="mt-2 text-xs text-amber-700">Nenhum cliente encontrado no IXC para essa busca.</p>
      ) : null}

      {matches.length > 0 ? (
        <ul className="mt-3 grid gap-1.5">
          {matches.map((match) => (
            <li key={`${match.cliente_id}-${match.login_id ?? "sem-login"}`}>
              <button
                type="button"
                onClick={() => handleSelect(match)}
                className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm hover:border-blue-300 hover:bg-blue-50"
              >
                <UserRound className="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-slate-950">{match.name}</span>
                  <span className="block truncate text-xs text-slate-500">
                    {match.login ? `Login ${match.login}` : "Sem login ativo"}
                    {match.cpf_masked ? ` · CPF ${match.cpf_masked}` : ""}
                    {match.latitude !== null && match.longitude !== null ? " · com coordenada cadastrada" : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
