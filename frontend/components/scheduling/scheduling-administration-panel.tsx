"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SchedulingSyncHealth, SchedulingSyncStatus } from "@/lib/scheduling-api";

import { SchedulingSettingsPanel } from "./scheduling-settings-panel";
import { SchedulingSyncPanel } from "./scheduling-sync-panel";
import { SchedulingTeamPanel } from "./scheduling-team-panel";

// Equipe, Configurações e Sincronização eram 3 itens de menu próprios (baixa frequência de uso) -
// agora vivem como sub-abas de uma única aba "Administração" (pedido do usuário 2026-08-31).
export function SchedulingAdministrationPanel({
  canManage,
  canSync,
  syncHealth,
  syncStatus,
  onSaved,
  onSynced,
}: {
  canManage: boolean;
  canSync: boolean;
  syncHealth: SchedulingSyncHealth | null;
  syncStatus: SchedulingSyncStatus | null;
  onSaved: () => void;
  onSynced: () => void;
}) {
  return (
    <Tabs defaultValue="sincronizacao">
      <TabsList>
        <TabsTrigger value="sincronizacao">Sincronização</TabsTrigger>
        {canManage ? <TabsTrigger value="equipe">Equipe</TabsTrigger> : null}
        {canManage ? <TabsTrigger value="configuracoes">Configurações</TabsTrigger> : null}
      </TabsList>
      <TabsContent value="sincronizacao">
        <SchedulingSyncPanel health={syncHealth} status={syncStatus} canSync={canSync} onSynced={onSynced} />
      </TabsContent>
      {canManage ? (
        <TabsContent value="equipe">
          <SchedulingTeamPanel onSaved={onSaved} />
        </TabsContent>
      ) : null}
      {canManage ? (
        <TabsContent value="configuracoes">
          <SchedulingSettingsPanel onSaved={onSaved} />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}
