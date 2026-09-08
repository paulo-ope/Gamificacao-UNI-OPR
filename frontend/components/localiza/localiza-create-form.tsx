"use client";

import { ChevronDown, ChevronUp, IdCard, Link2, MapPin } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { localizaApi, type IxcCustomerMatch, type LocationRequestCreateResult } from "@/lib/localiza-api";
import { LocalizaIxcSearch } from "./localiza-ixc-search";

const EMPTY_FORM = { order_code: "", opa_protocol: "", customer_id: "", customer_name: "", registered_latitude: "", registered_longitude: "" };

// O link recém-gerado é mostrado no painel de detalhe, que abre automaticamente logo depois de
// criar (ver `app/localiza/page.tsx`) - mostrar aqui TAMBÉM duplicava o botão de copiar atrás de
// um painel que cobre a tela inteira (achado real, reportado pelo usuário ao ver ao vivo).
//
// Pedido do usuário (2026-09-08, "preciso deixar mais intuitivo... só colocar o CPF do cliente sem
// aqueles outros campos embaixo solicitando mais informação"): a busca por CPF/login é o caminho
// principal e único visível de cara - os campos manuais (O.S., protocolo, ajuste de coordenada)
// ficam escondidos atrás de um "Mais opções", só pra quando o cliente não é achado no IXC ou o
// atendente precisa complementar algo.
export function LocalizaCreateForm({ onCreated }: { onCreated: (item: LocationRequestCreateResult) => void }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectedMatch, setSelectedMatch] = useState<IxcCustomerMatch | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    // Nenhum campo é obrigatório sozinho - o link costuma ser enviado ANTES de existir O.S. no
    // IXC. Mas a solicitação precisa de pelo menos um identificador pra dar pra achar depois
    // (mesma regra do backend, checada aqui só pra feedback imediato).
    if (![form.order_code, form.opa_protocol, form.customer_id, form.customer_name].some((value) => value.trim())) {
      setError("Busque o cliente pelo CPF ou login acima, ou informe ao menos um identificador em \"Mais opções\".");
      return;
    }
    const hasLat = form.registered_latitude.trim() !== "";
    const hasLon = form.registered_longitude.trim() !== "";
    if (hasLat !== hasLon) {
      setError("Informe latitude e longitude cadastradas juntas, ou nenhuma das duas.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await localizaApi.create({
        order_code: form.order_code.trim() || null,
        opa_protocol: form.opa_protocol.trim() || null,
        customer_id: form.customer_id.trim() || null,
        customer_name: form.customer_name.trim() || null,
        registered_latitude: hasLat ? Number(form.registered_latitude) : null,
        registered_longitude: hasLon ? Number(form.registered_longitude) : null
      });
      setForm(EMPTY_FORM);
      setSelectedMatch(null);
      setDetailsOpen(false);
      onCreated(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao gerar o link de localização.");
    } finally {
      setSubmitting(false);
    }
  }

  function applyIxcMatch(match: IxcCustomerMatch) {
    setSelectedMatch(match);
    setForm((prev) => ({
      ...prev,
      customer_name: match.name,
      customer_id: match.login || String(match.cliente_id),
      registered_latitude: match.latitude !== null ? String(match.latitude) : prev.registered_latitude,
      registered_longitude: match.longitude !== null ? String(match.longitude) : prev.registered_longitude
    }));
  }

  function clearSelectedMatch() {
    setSelectedMatch(null);
    setForm(EMPTY_FORM);
  }

  return (
    <Card className="rounded-2xl border-slate-200 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-blue-600" aria-hidden="true" />
          Gerar link de localização
        </CardTitle>
        <p className="text-xs text-slate-500">
          Busque o cliente pelo CPF (ou pelo login) e gere o link - ele abre pelo celular do cliente, que compartilha
          a localização, e você recebe a posição confirmada aqui.
        </p>
      </CardHeader>
      <CardContent className="grid gap-4">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <LocalizaIxcSearch onSelect={applyIxcMatch} />

          {selectedMatch ? (
            <div className="flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4">
              <IdCard className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-950">{selectedMatch.name}</p>
                <p className="text-xs text-slate-600">
                  {selectedMatch.login ? `Login ${selectedMatch.login}` : "Sem login ativo"}
                  {selectedMatch.cpf_masked ? ` · CPF ${selectedMatch.cpf_masked}` : ""}
                </p>
                {selectedMatch.latitude !== null && selectedMatch.longitude !== null ? (
                  <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                    <MapPin className="h-3 w-3" aria-hidden="true" /> Coordenada cadastrada preenchida automaticamente
                  </p>
                ) : null}
              </div>
              <button type="button" onClick={clearSelectedMatch} className="text-xs font-medium text-blue-700 hover:underline">
                Trocar
              </button>
            </div>
          ) : null}

          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700">
              {detailsOpen ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
              {selectedMatch ? "Mais opções (O.S., protocolo, ajustar coordenada)" : "Não achou o cliente? Preencher manualmente"}
            </CollapsibleTrigger>
            <CollapsibleContent className="grid gap-3 pt-3 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="localiza-order-code">Código da O.S.</Label>
                <Input
                  id="localiza-order-code"
                  value={form.order_code}
                  onChange={(event) => setForm((prev) => ({ ...prev, order_code: event.target.value }))}
                  placeholder="Preencha se a O.S. já existir"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="localiza-opa-protocol">Protocolo OPA</Label>
                <Input
                  id="localiza-opa-protocol"
                  value={form.opa_protocol}
                  onChange={(event) => setForm((prev) => ({ ...prev, opa_protocol: event.target.value }))}
                  placeholder="Protocolo do atendimento"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="localiza-customer-name">Nome do cliente</Label>
                <Input
                  id="localiza-customer-name"
                  value={form.customer_name}
                  onChange={(event) => setForm((prev) => ({ ...prev, customer_name: event.target.value }))}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="localiza-customer-id">Identificador do cliente</Label>
                <Input
                  id="localiza-customer-id"
                  value={form.customer_id}
                  onChange={(event) => setForm((prev) => ({ ...prev, customer_id: event.target.value }))}
                  placeholder="Login, contrato, CPF..."
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1.5">
                  <Label htmlFor="localiza-lat">Latitude cadastrada</Label>
                  <Input
                    id="localiza-lat"
                    type="number"
                    step="any"
                    value={form.registered_latitude}
                    onChange={(event) => setForm((prev) => ({ ...prev, registered_latitude: event.target.value }))}
                    placeholder="Opcional"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="localiza-lon">Longitude cadastrada</Label>
                  <Input
                    id="localiza-lon"
                    type="number"
                    step="any"
                    value={form.registered_longitude}
                    onChange={(event) => setForm((prev) => ({ ...prev, registered_longitude: event.target.value }))}
                    placeholder="Opcional"
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          <div>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Gerando..." : "Gerar link de localização"}
            </Button>
          </div>
        </form>

        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
