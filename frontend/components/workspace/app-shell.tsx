"use client";

import Link from "next/link";
import { ChevronDown, LogOut, Menu, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useVisibleModules } from "@/hooks/use-visible-modules";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import type { AuthUser, WorkspaceVisibleModule } from "@/lib/types";
import { cn } from "@/lib/utils";
import { moduleScreenHref, visibleModuleScreens, type ModuleScreen } from "@/lib/module-screens";
import { moduleIcon, visibleWorkspaceScreens } from "@/lib/workspace-navigation";

const SIDEBAR_STORAGE_KEY = "uni_workspace_sidebar_expanded";

/**
 * Casca de aplicação do ecossistema: menu lateral persistente + cabeçalho único.
 *
 * É o primeiro passo da transição de "entrar em um módulo e ficar preso nele" para "navegar de
 * tela em tela": as telas transversais (Visão Geral, Módulos) já vivem aqui, e cada módulo pode
 * adotar esta casca depois, um por vez, sem que a navegação principal mude de novo. Por isso a
 * autenticação mora aqui e não em cada página - era o trecho copiado em toda página de módulo.
 *
 * No desktop a barra nasce completa e permanece assim, com as telas de cada módulo abrindo em
 * submenu ali mesmo - é a navegação principal, não um detalhe escondido. Quem quiser mais espaço
 * pode recolher para a trilha de ícones, e a escolha fica guardada. No mobile continua sendo a
 * gaveta (`Sheet`), onde trilha de ícones não faria sentido.
 */
export function WorkspaceAppShell({
  activePath,
  eyebrow = "UNI Workspace",
  title,
  subtitle,
  actions,
  children,
}: {
  activePath: string;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /**
   * Aceita uma função para receber o usuário já autenticado. A casca é quem resolve a
   * autenticação, então sem isso cada tela filha teria que chamar `useWorkspaceAuth` de novo só
   * pra saber as permissões - e cada instância do hook refaz `/auth/me`.
   */
  children: ReactNode | ((user: AuthUser) => ReactNode);
}) {
  const { user, checking, error, login, logout } = useWorkspaceAuth();
  const modules = useVisibleModules(user);
  // Nasce COMPLETA (pedido do usuário em 2026-09-03): a barra lateral inteira é a navegação
  // principal do ecossistema, não um detalhe a ser descoberto. Recolher para a trilha de ícones
  // continua possível, mas é escolha de quem quer mais espaço - nunca o padrão.
  const [expanded, setExpanded] = useState(true);

  // Lido em efeito, não na inicialização do estado: `localStorage` não existe na renderização do
  // servidor, e ler ali geraria divergência de hidratação. Só respeita a preferência quando ela
  // existe de verdade - chave ausente mantém o padrão completo. Falha em silêncio de propósito:
  // navegador em modo privado ou com armazenamento bloqueado só perde a preferência, não a tela.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (stored !== null) setExpanded(stored === "true");
    } catch {
      // Sem preferência acessível: segue completa.
    }
  }, []);

  function toggleSidebar() {
    setExpanded((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        // Preferência é conveniência: não impedir a interação se o armazenamento falhar.
      }
      return next;
    });
  }

  if (checking && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando UNI Workspace...
      </main>
    );
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={error} onLogin={login} showPortalLink />;

  const screens = visibleWorkspaceScreens(user.permissions);

  return (
    <div className="min-h-screen bg-slate-50 lg:flex">
      <aside
        className={cn(
          // `lg:sticky lg:top-0 lg:h-screen`: sem isso a barra é só mais um item do flex-row e
          // `align-items: stretch` (padrão) a esticava até a altura da COLUNA DE CONTEÚDO - numa
          // tela como a Visão Geral (vários cartões e gráficos, mais alta que a viewport), a barra
          // esticava junto, e o `flex-1` do `<nav>` abaixo enchia esse excesso todo de vão em
          // branco entre o último módulo e o rodapé (medido: 934px numa página de 1599px de
          // altura, crescendo sem limite conforme a página cresce - achado real, 2026-09-03).
          // `h-screen` fixa a altura na viewport (não mais na altura da coluna irmã) e `sticky`
          // mantém a barra visível enquanto a página rola.
          "hidden shrink-0 border-r border-slate-200 bg-white transition-[width] duration-200 lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col",
          expanded ? "w-64" : "w-[68px]",
        )}
      >
        <div
          className={cn(
            "flex items-center gap-2 border-b border-slate-100 py-4",
            expanded ? "px-4" : "justify-center px-2",
          )}
        >
          <button
            type="button"
            onClick={toggleSidebar}
            aria-expanded={expanded}
            aria-label={expanded ? "Recolher menu lateral" : "Expandir menu lateral"}
            title={expanded ? "Recolher menu" : "Expandir menu"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            {expanded ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeftOpen className="h-5 w-5" />}
          </button>
          {expanded ? (
            <div className="min-w-0">
              <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-uni-royal">UNI Workspace</p>
              <p className="truncate text-sm font-semibold text-slate-950">Ecossistema Operacional</p>
            </div>
          ) : null}
        </div>
        <ShellNavigation
          activePath={activePath}
          screens={screens}
          modules={modules}
          permissions={user.permissions}
          expanded={expanded}
          onExpandRequest={() => !expanded && toggleSidebar()}
        />
        {expanded ? (
          <div className="border-t border-slate-100 px-4 py-3">
            <p className="truncate text-[11px] font-semibold text-slate-700">{user.name}</p>
            <p className="truncate text-[10px] text-slate-400">{user.email}</p>
          </div>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <div className="lg:hidden">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button type="button" size="icon" variant="outline" aria-label="Abrir menu do ecossistema">
                      <Menu className="h-5 w-5" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent className="left-0 right-auto w-[88vw] border-l-0 border-r bg-white p-0 text-slate-950 sm:max-w-sm">
                    <SheetHeader className="shrink-0 border-slate-100">
                      <SheetTitle className="text-slate-950">UNI Workspace</SheetTitle>
                      <SheetDescription className="text-slate-500">Telas e módulos do ecossistema</SheetDescription>
                    </SheetHeader>
                    <ShellNavigation
                      activePath={activePath}
                      screens={screens}
                      modules={modules}
                      permissions={user.permissions}
                      expanded
                      closeOnNavigate
                    />
                  </SheetContent>
                </Sheet>
              </div>
              <div className="min-w-0">
                <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-uni-royal">{eyebrow}</p>
                <h1 className="truncate text-base font-semibold text-slate-950">{title}</h1>
                {subtitle ? <p className="truncate text-[11px] text-slate-500">{subtitle}</p> : null}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {actions}
              <NotificationBell />
              <Button type="button" variant="ghost" onClick={logout} aria-label="Sair">
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Sair</span>
              </Button>
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">
          {typeof children === "function" ? children(user) : children}
        </main>
      </div>
    </div>
  );
}

function ShellNavigation({
  activePath,
  screens,
  modules,
  permissions,
  expanded,
  onExpandRequest,
  closeOnNavigate = false,
}: {
  activePath: string;
  screens: ReturnType<typeof visibleWorkspaceScreens>;
  modules: WorkspaceVisibleModule[];
  permissions: readonly string[];
  expanded: boolean;
  /** Recolhido não há onde desenhar submenu: clicar em "expandir telas" abre a barra primeiro. */
  onExpandRequest?: () => void;
  closeOnNavigate?: boolean;
}) {
  return (
    <nav
      className={cn("min-h-0 flex-1 overflow-y-auto", expanded ? "p-3" : "px-2 py-3")}
      aria-label="Navegação do ecossistema"
    >
      <NavGroup label="Telas" expanded={expanded}>
        {screens.map((screen) => (
          <NavItem
            key={screen.key}
            href={screen.path}
            label={screen.name}
            description={screen.description}
            icon={screen.icon}
            selected={activePath === screen.path}
            expanded={expanded}
            closeOnNavigate={closeOnNavigate}
          />
        ))}
      </NavGroup>
      {modules.length ? (
        <NavGroup label="Módulos" expanded={expanded}>
          {modules.map((module) => (
            <ModuleNavEntry
              key={module.key}
              module={module}
              activePath={activePath}
              permissions={permissions}
              expanded={expanded}
              onExpandRequest={onExpandRequest}
              closeOnNavigate={closeOnNavigate}
            />
          ))}
        </NavGroup>
      ) : null}
    </nav>
  );
}

/**
 * Um módulo no menu lateral: o próprio módulo mais as telas de dentro dele.
 *
 * O submenu existe para o pedido de "navegar por todos os lugares sem sair da Visão Geral": cada
 * tela interna vira um link direto (`/operacao?tab=sla`), em vez de abrir o módulo e caçar a aba
 * no menu de lá. As telas vêm de `lib/module-screens.ts`, que reaproveita a lista de navegação de
 * cada módulo e filtra pelas permissões do usuário.
 */
function ModuleNavEntry({
  module,
  activePath,
  permissions,
  expanded,
  onExpandRequest,
  closeOnNavigate,
}: {
  module: WorkspaceVisibleModule;
  activePath: string;
  permissions: readonly string[];
  expanded: boolean;
  onExpandRequest?: () => void;
  closeOnNavigate: boolean;
}) {
  const icon = moduleIcon(module.key);
  const screens = visibleModuleScreens(module.key, icon, permissions);
  const isActiveModule = activePath === module.web_path;
  // Abre já aberto no módulo em que se está: quem entrou na Operação Analítica vê as telas dela
  // sem precisar de um clique extra.
  const [open, setOpen] = useState(isActiveModule);

  const canExpand = screens.length > 0;

  return (
    <div>
      <div className={cn("flex items-center", expanded ? "gap-0.5" : "justify-center")}>
        {/* `min-w-0 flex-1` no invólucro: o próprio item é `w-full`, então sem isto ele ocupa a
            largura inteira da barra e empurra o botão de expandir para fora dela. */}
        <div className="min-w-0 flex-1">
          <NavItem
            href={module.web_path}
            label={module.name}
            description={module.description}
            icon={icon}
            selected={isActiveModule}
            expanded={expanded}
            closeOnNavigate={closeOnNavigate}
          />
        </div>
        {expanded && canExpand ? (
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
            aria-label={`${open ? "Recolher" : "Expandir"} telas de ${module.name}`}
            className="flex h-8 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
          </button>
        ) : null}
      </div>
      {expanded && canExpand && open ? (
        <ul className="mb-1 ml-6 mt-0.5 space-y-0.5 border-l border-slate-200 pl-2">
          {screens.map((screen) => (
            <ModuleScreenLink
              key={screen.value}
              href={moduleScreenHref(module.web_path, screen)}
              screen={screen}
              closeOnNavigate={closeOnNavigate}
            />
          ))}
        </ul>
      ) : null}
      {!expanded && canExpand ? (
        <button
          type="button"
          onClick={() => {
            setOpen(true);
            onExpandRequest?.();
          }}
          aria-label={`Expandir telas de ${module.name}`}
          title={`Telas de ${module.name}`}
          className="mx-auto mt-0.5 flex h-4 w-9 items-center justify-center rounded text-slate-300 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <ChevronDown className="h-3 w-3" />
        </button>
      ) : null}
    </div>
  );
}

function ModuleScreenLink({
  href,
  screen,
  closeOnNavigate,
}: {
  href: string;
  screen: ModuleScreen;
  closeOnNavigate: boolean;
}) {
  const link = (
    <Link
      href={href}
      title={screen.description}
      className="block truncate rounded-lg px-2.5 py-1.5 text-[12px] text-slate-600 transition-colors hover:bg-slate-50 hover:text-uni-royal"
    >
      {screen.label}
    </Link>
  );
  return <li>{closeOnNavigate ? <SheetClose asChild>{link}</SheetClose> : link}</li>;
}

function NavGroup({ label, expanded, children }: { label: string; expanded: boolean; children: ReactNode }) {
  return (
    <div className="mb-4 last:mb-0">
      {expanded ? (
        <p className="px-3 pb-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      ) : (
        // Recolhido não cabe o rótulo do grupo: um divisor mantém a separação visível entre
        // "Telas" e "Módulos" sem texto cortado.
        <div className="mx-2 mb-2 border-t border-slate-100 first:border-t-0" aria-hidden="true" />
      )}
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function NavItem({
  href,
  label,
  description,
  icon: Icon,
  selected,
  expanded,
  closeOnNavigate,
}: {
  href: string;
  label: string;
  description: string;
  icon: ReturnType<typeof moduleIcon>;
  selected: boolean;
  expanded: boolean;
  closeOnNavigate: boolean;
}) {
  const link = (
    <Link
      href={href}
      aria-current={selected ? "page" : undefined}
      // Recolhido, o ícone é a única pista do destino: `title` dá o tooltip nativo e `aria-label`
      // garante o nome para leitor de tela, já que o texto não está na árvore.
      title={expanded ? undefined : `${label} - ${description}`}
      aria-label={expanded ? undefined : label}
      className={cn(
        "flex w-full items-center rounded-xl text-left transition-colors",
        expanded ? "gap-3 px-3 py-2.5" : "justify-center px-1 py-1.5",
        selected ? "bg-uni-royal/10 text-uni-royal" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
      )}
    >
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
          selected ? "bg-uni-royal text-white" : "bg-slate-100 text-slate-500",
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      {expanded ? (
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold">{label}</span>
          <span className={cn("block truncate text-[11px]", selected ? "text-uni-royal/70" : "text-slate-400")}>
            {description}
          </span>
        </span>
      ) : null}
    </Link>
  );
  return closeOnNavigate ? <SheetClose asChild>{link}</SheetClose> : link;
}
