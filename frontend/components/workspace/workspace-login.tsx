"use client";

import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  ChartNoAxesCombined,
  Check,
  Eye,
  EyeOff,
  Layers,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
  Trophy,
  UsersRound,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useId, useState } from "react";
import { WorkspacePasswordRecovery } from "./password-recovery";
import type { PasswordRecoveryApi } from "@/lib/password-recovery";
import { workspacePasswordRecoveryApi } from "@/lib/workspace-password-recovery-api";
import "./workspace-login.css";

type Props = {
  isLoading: boolean;
  error: string | null;
  onLogin: (email: string, password: string) => Promise<unknown>;
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  description?: string;
  helperText?: ReactNode;
  variant?: "workspace" | "portal";
  showPortalLink?: boolean;
  recoveryApi?: PasswordRecoveryApi;
};

const REMEMBERED_EMAIL_KEY = "uni-workspace-remembered-email";

function WorkspaceConnections() {
  return (
    <div className="uni-access-connections" aria-hidden="true">
      <div className="uni-access-orbit uni-access-orbit-outer" />
      <div className="uni-access-orbit uni-access-orbit-inner" />
      <svg
        className="uni-access-connection-lines"
        viewBox="0 0 580 290"
        preserveAspectRatio="none"
        fill="none"
      >
        <defs>
          <linearGradient
            id="uni-connection-gradient"
            x1="0"
            y1="0"
            x2="580"
            y2="290"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#27d9bf" />
            <stop offset="1" stopColor="#2d5fff" />
          </linearGradient>
        </defs>
        <path
          d="M290 145C220 145 200 60 120 60M290 145C360 145 370 70 460 70M290 145C220 145 195 230 115 230M290 145C365 145 380 232 465 232"
          stroke="url(#uni-connection-gradient)"
          strokeOpacity=".36"
          strokeWidth="1.5"
        />
        <path
          d="M120 60C80 155 125 260 290 270M460 70C510 180 460 265 290 270"
          stroke="#c4d8f0"
          strokeDasharray="3 7"
        />
        <circle cx="195" cy="100" r="4" fill="#27d9bf" />
        <circle cx="377" cy="191" r="4" fill="#2d5fff" />
        <circle cx="290" cy="270" r="3" fill="#97accf" />
      </svg>
      <div className="uni-access-hub">
        <Layers size={32} strokeWidth={1.5} />
        <span>Workspace</span>
      </div>
      <div className="uni-access-node uni-access-node-operations">
        <span className="uni-access-node-icon">
          <Layers size={19} />
        </span>
        <div>
          <strong>Operação</strong>
          <small>Fluxos conectados</small>
        </div>
        <span className="uni-access-node-dot" />
      </div>
      <div className="uni-access-node uni-access-node-people">
        <span className="uni-access-node-icon">
          <UsersRound size={19} />
        </span>
        <div>
          <strong>Pessoas</strong>
          <small>Talentos que somam</small>
        </div>
      </div>
      <div className="uni-access-node uni-access-node-results">
        <span className="uni-access-node-icon">
          <ChartNoAxesCombined size={19} />
        </span>
        <div>
          <strong>Resultados</strong>
          <small>Uma visão mais clara</small>
        </div>
      </div>
      <div className="uni-access-node uni-access-node-growth">
        <span className="uni-access-node-icon">
          <Trophy size={19} />
        </span>
        <div>
          <strong>Evolução</strong>
          <small>Cada conquista conta</small>
        </div>
        <span className="uni-access-node-dot" />
      </div>
      <span className="uni-access-floating-dot uni-access-floating-dot-one" />
      <span className="uni-access-floating-dot uni-access-floating-dot-two" />
    </div>
  );
}

export function WorkspaceLogin({
  isLoading,
  error,
  onLogin,
  title,
  subtitle,
  description,
  helperText,
  variant = "workspace",
  showPortalLink = false,
  recoveryApi = workspacePasswordRecoveryApi,
}: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();
  const busy = isLoading || submitting;
  const portal = variant === "portal";

  useEffect(() => {
    try {
      const saved = localStorage.getItem(REMEMBERED_EMAIL_KEY);
      if (saved) {
        setEmail(saved);
        setRememberEmail(true);
      }
    } catch {
      /* Login remains available when browser storage is disabled. */
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setSubmitting(true);
    try {
      await onLogin(email.trim(), password);
      try {
        if (rememberEmail)
          localStorage.setItem(REMEMBERED_EMAIL_KEY, email.trim());
        else localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      } catch {
        /* Remembering an email is optional. */
      }
    } catch {
      // Authentication errors are supplied by the existing authentication hook.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="uni-access-page">
      <header className="uni-access-header">
        <a
          href="/"
          className="uni-access-brand"
          aria-label="UNI Workspace, página inicial"
        >
          <img
            src="/brand/uni-logo.png"
            alt="UNI Internet"
            width="72"
            height="48"
          />
          <span className="uni-access-brand-divider" />
          <span>
            workspace<span className="uni-access-brand-period">.</span>
          </span>
        </a>
        <div className="uni-access-header-label">
          <LockKeyhole size={14} aria-hidden="true" /> Acesso corporativo
        </div>
      </header>
      <div className="uni-access-layout">
        <section
          className="uni-access-intro"
          aria-labelledby="uni-access-intro-title"
        >
          <h2 id="uni-access-intro-title">
            Seu trabalho.
            <br />
            <span>Mais conectado.</span>
          </h2>
          <p className="uni-access-intro-description">
            {description ??
              "Pessoas, operações e conquistas em um só lugar. Um espaço para simplificar sua rotina e ir mais longe, juntos."}
          </p>
          <WorkspaceConnections />
          <div className="uni-access-intro-footnote">
            <span className="uni-access-sparkle">
              <Sparkles size={16} aria-hidden="true" />
            </span>
            <p>
              Uma conexão. <strong>Novas possibilidades.</strong>
            </p>
          </div>
        </section>
        <section
          className="uni-access-card"
          aria-labelledby="uni-access-form-title"
        >
          <div className="uni-access-card-top">
            <span className="uni-access-card-icon">
              <Layers size={22} strokeWidth={1.7} aria-hidden="true" />
            </span>
            <span className="uni-access-card-badge">
              <ShieldCheck size={13} aria-hidden="true" /> Ambiente seguro
            </span>
          </div>
          <div className="uni-access-card-heading">
            <p className="uni-access-kicker">
              {portal ? "SEU ESPAÇO NA UNI" : "BEM-VINDO AO WORKSPACE"}
            </p>
            <h1 id="uni-access-form-title">
              {title ??
                (portal
                  ? "Seu próximo passo começa aqui"
                  : "Bom ter você por aqui.")}
            </h1>
            <p>{subtitle ?? "Entre com sua conta e conecte-se ao seu dia."}</p>
          </div>
          <form
            className="uni-access-form"
            method="post"
            onSubmit={submit}
            aria-busy={busy}
          >
            <div className="uni-access-field">
              <label htmlFor={emailId}>E-mail de acesso</label>
              <div className="uni-access-input-wrap">
                <Mail size={18} aria-hidden="true" />
                <input
                  id={emailId}
                  name="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  autoComplete="username"
                  placeholder="voce@souuni.com"
                  disabled={busy}
                  aria-describedby={error ? errorId : undefined}
                />
              </div>
            </div>
            <div className="uni-access-field">
              <label htmlFor={passwordId}>Senha</label>
              <div className="uni-access-input-wrap">
                <LockKeyhole size={18} aria-hidden="true" />
                <input
                  id={passwordId}
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="Digite sua senha"
                  disabled={busy}
                  aria-describedby={error ? errorId : undefined}
                />
                <button
                  type="button"
                  className="uni-access-password-toggle"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                  aria-pressed={showPassword}
                  aria-controls={passwordId}
                >
                  {showPassword ? (
                    <EyeOff size={18} aria-hidden="true" />
                  ) : (
                    <Eye size={18} aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>
            <div className="uni-access-form-options">
              <label className="uni-access-checkbox">
                <input
                  type="checkbox"
                  name="rememberEmail"
                  checked={rememberEmail}
                  onChange={(event) => {
                    setRememberEmail(event.target.checked);
                    if (!event.target.checked) {
                      try {
                        localStorage.removeItem(REMEMBERED_EMAIL_KEY);
                      } catch {}
                    }
                  }}
                />
                <span>Lembrar meu e-mail</span>
              </label>
              <Dialog.Root open={recoveryOpen} onOpenChange={setRecoveryOpen}>
                <Dialog.Trigger asChild>
                  <button
                    type="button"
                    className="uni-access-text-button"
                    data-recovery-trigger
                  >
                    Esqueci minha senha
                  </button>
                </Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Overlay className="uni-access-dialog-overlay" />
                  <Dialog.Content className="uni-access-dialog uni-recovery-dialog">
                    <WorkspacePasswordRecovery
                      api={recoveryApi}
                      initialEmail={email}
                      onRecovered={setEmail}
                      onClose={() => setRecoveryOpen(false)}
                    />
                    <Dialog.Close asChild>
                      <button
                        type="button"
                        className="uni-access-dialog-close"
                        aria-label="Fechar recuperação de senha"
                      >
                        <X size={20} aria-hidden="true" />
                      </button>
                    </Dialog.Close>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </div>
            {error ? (
              <p id={errorId} className="uni-access-error" role="alert">
                {error}
              </p>
            ) : null}
            <p className="uni-access-demo-feedback" role="status" hidden />
            <button
              className="uni-access-primary"
              type="submit"
              disabled={busy}
            >
              <span>
                {busy
                  ? "Conectando..."
                  : portal
                    ? "Entrar no Portal"
                    : "Entrar no Workspace"}
              </span>
              {busy ? (
                <Loader2
                  size={19}
                  className="uni-access-spinner"
                  aria-hidden="true"
                />
              ) : (
                <ArrowRight size={19} aria-hidden="true" />
              )}
            </button>
          </form>
          {showPortalLink ? (
            <>
              <div className="uni-access-separator">
                <span>UM ESPAÇO PARA VOCÊ</span>
              </div>
              <Link href="/portal" className="uni-access-portal">
                <span className="uni-access-portal-icon">
                  <UsersRound size={19} aria-hidden="true" />
                </span>
                <span>
                  <strong>Portal do Colaborador</strong>
                  <small>Seu desempenho e suas conquistas</small>
                </span>
                <ArrowRight size={17} aria-hidden="true" />
              </Link>
            </>
          ) : null}
          {helperText ? (
            <div className="uni-access-helper">{helperText}</div>
          ) : null}
          <div className="uni-access-card-bottom">
            <ShieldCheck size={16} aria-hidden="true" />
            <span>Seu acesso é pessoal. Sua conexão é com a UNI.</span>
          </div>
        </section>
      </div>
      <footer className="uni-access-footer">
        <p>
          © {new Date().getFullYear()} UNI Internet <span>·</span> Feito para
          conectar.
        </p>
        <Link href="/politica-de-privacidade">
          Privacidade
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
        <span className="uni-access-footer-tag">
          <Check size={13} aria-hidden="true" /> UNI Workspace
        </span>
      </footer>
    </main>
  );
}
