"use client";

import Link from "next/link";
import { Building2, Layers, Loader2, ShieldCheck, Trophy, UserRound } from "lucide-react";
import { FormEvent, ReactNode, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type WorkspaceLoginVariant = "workspace" | "portal";

type Highlight = { icon: typeof ShieldCheck; label: string };

type Props = {
  isLoading: boolean;
  error: string | null;
  onLogin: (email: string, password: string) => Promise<unknown>;
  /** Selo curto acima do título (ex: "UNI Workspace", "Portal do Colaborador"). */
  eyebrow?: string;
  /** Título principal da tela de login. */
  title?: string;
  /** Linha curta abaixo do título, perto do formulário. */
  subtitle?: string;
  /** Texto mais longo exibido no painel de marca (some no mobile). Usa `subtitle` quando ausente. */
  description?: string;
  /** Texto auxiliar discreto abaixo do botão de entrar (ex: como pedir acesso) - aceita um link
   *  (ex: para /solicitar-acesso, Fase 2D), não só texto puro. */
  helperText?: ReactNode;
  /** Ajusta copy padrão, ícone e destaques por contexto - visual continua o mesmo, é a mesma tela de login do Workspace. */
  variant?: WorkspaceLoginVariant;
  /** Mostra um link secundário para `/portal`, abaixo do botão "Entrar" - só a tela inicial (`/`)
   *  passa essa prop, pra não repetir o link nas telas de login de cada módulo específico. */
  showPortalLink?: boolean;
};

const VARIANT_COPY: Record<
  WorkspaceLoginVariant,
  { eyebrow: string; title: string; subtitle: string; icon: typeof ShieldCheck; highlights: Highlight[] }
> = {
  workspace: {
    eyebrow: "UNI Workspace",
    title: "Acesse o ecossistema",
    subtitle: "Use seu usuário do UNI Workspace.",
    icon: Layers,
    // Sem destaques por padrão: o Workspace reúne módulos bem diferentes entre si (Operação,
    // Gestão, Suporte...), então uma lista de benefícios genérica valeria menos que não ter
    // nenhuma - cada tela específica pode passar a própria lista via prop, quando fizer sentido.
    highlights: []
  },
  portal: {
    eyebrow: "Portal do Colaborador",
    title: "Acompanhe seu resultado",
    subtitle: "Pontuação, O.S. e fechamento em um só lugar.",
    icon: Trophy,
    highlights: [
      { icon: ShieldCheck, label: "Acesso seguro e individual" },
      { icon: UserRound, label: "Só os seus próprios dados" },
      { icon: Trophy, label: "Pontuação, O.S. e fechamento" },
      { icon: Building2, label: "Mesmo login do ecossistema UNI" }
    ]
  }
};

export function WorkspaceLogin({ isLoading, error, onLogin, eyebrow, title, subtitle, description, helperText, variant = "workspace", showPortalLink = false }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();
  const copy = VARIANT_COPY[variant];
  const Icon = copy.icon;
  const resolvedEyebrow = eyebrow ?? copy.eyebrow;
  const resolvedTitle = title ?? copy.title;
  const resolvedSubtitle = subtitle ?? copy.subtitle;
  const resolvedDescription = description ?? resolvedSubtitle;

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await onLogin(email, password);
    } catch {
      // A mensagem amigável é controlada pelo hook de autenticação.
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-blue-950/10 md:grid-cols-[1fr_1.1fr]">
        {/* Painel azul agora aparece em toda largura de tela, não só a partir de `md`: no mobile
            ele empilha em cima do formulário (o grid vira 1 coluna abaixo de `md` sozinho, por
            causa do `md:grid-cols-[1fr_1.1fr]` no container pai). Lista de destaques e rodapé só
            aparecem a partir de `md` pra não empurrar os campos de login pra fora da primeira
            tela no celular - logo, selo e título já bastam pra dar o mesmo acabamento no mobile. */}
        <div className="uni-gradient relative flex flex-col overflow-hidden p-6 text-white sm:p-8 md:p-10">
          {/* `self-start`: sem isso, o container flex-col esticava a logo pra preencher toda a
              largura do painel (align-items:stretch é o padrão de flex-col), distorcendo a
              proporção original (804x535) em algo perto de 9:1 - o efeito visual era "borrado e
              esticado", não um problema de resolução da imagem. */}
          <img src="/brand/uni-logo-white.png" alt="" className="h-8 w-auto self-start object-contain drop-shadow-sm md:h-9" />
          <div className="mt-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-white/85">
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {resolvedEyebrow}
            </span>
            <h2 className="mt-4 text-2xl font-semibold leading-[1.15] tracking-tight md:mt-5 md:text-3xl">{resolvedTitle}</h2>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/80 md:mt-3">{resolvedDescription}</p>
            {copy.highlights.length ? (
              <ul className="mt-5 hidden gap-3 md:mt-7 md:grid">
                {copy.highlights.map((item) => {
                  const HighlightIcon = item.icon;
                  return (
                    <li key={item.label} className="flex items-center gap-3 text-sm text-white/90">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                        <HighlightIcon className="h-4 w-4" aria-hidden="true" />
                      </span>
                      {item.label}
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
          {/* Espaçador flexível em vez de `justify-between`: com a lista de destaques, o bloco
              principal já podia ocupar toda a altura do painel e zerar o respiro antes do rodapé
              (achado real: `gap` chegou a 0px na primeira versão). `flex-1` absorve o espaço
              sobrando quando há; `mt-8` no rodapé garante um mínimo mesmo quando não sobra nada.
              Ambos somem no mobile junto com a lista de destaques - sem eles, não sobra altura
              nenhuma pra absorver e o rodapé viraria só um texto solto colado no título. */}
          <div className="hidden flex-1 md:block" />
          <p className="mt-6 hidden text-xs text-white/60 md:mt-8 md:block">UNI Internet · Ecossistema operacional</p>
        </div>

        <form onSubmit={submit} className="flex flex-col justify-center gap-6 p-8 sm:p-10 md:p-12" noValidate>
          {/* Título/subtítulo só a partir de `md`: no mobile o painel azul logo acima já mostra
              logo, selo e título - repetir aqui embaixo, colado, seria duplicação visual (antes
              disso o painel azul ficava oculto no mobile, então essa repetição fazia sentido). */}
          <div className="hidden md:block">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{resolvedTitle}</h1>
            <p className="mt-2 text-sm text-slate-500">{resolvedSubtitle}</p>
          </div>
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor={emailId}>E-mail</Label>
              <Input
                id={emailId}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                autoFocus
                className="focus-visible:ring-[#2d5fff]"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={passwordId}>Senha</Label>
              <Input
                id={passwordId}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete="current-password"
                className="focus-visible:ring-[#2d5fff]"
              />
            </div>
            {error ? (
              <p id={errorId} role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </p>
            ) : null}
            <Button type="submit" disabled={isLoading} aria-describedby={error ? errorId : undefined} className="mt-1 w-full rounded-xl">
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              {isLoading ? "Entrando..." : "Entrar"}
            </Button>
            {showPortalLink ? (
              <Link
                href="/portal"
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:border-blue-200 hover:bg-blue-50/60 hover:text-blue-700"
              >
                <Trophy className="h-4 w-4" aria-hidden="true" />
                Acessar Portal do Colaborador
              </Link>
            ) : null}
            {helperText ? <p className="text-center text-xs text-slate-400">{helperText}</p> : null}
          </div>
        </form>
      </div>
    </main>
  );
}
