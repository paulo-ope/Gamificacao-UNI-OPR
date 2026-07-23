# Contratos entre módulos

## Princípios

Contratos são estáveis, versionados e orientados a dados de negócio. Eles evitam que um módulo dependa de modelos ORM, tabelas ou regras internas de outro.

## Projeção de O.S. operacional para consumidores

Contrato inicial proposto: `operations.order-assessment.v1`.

```json
{
  "source": "ixc",
  "source_order_id": "1245969",
  "order_code": "IXC-1245969",
  "status": "closed",
  "opened_at": "2026-07-20T08:00:00-04:00",
  "closed_at": "2026-07-20T16:30:00-04:00",
  "sla": {
    "status": "out_of_time",
    "target_hours": 24,
    "elapsed_hours": 32.5,
    "calculation_version": 1
  },
  "warranty": {
    "is_within_window": false,
    "origin_order_id": null
  },
  "classification": {
    "regional": "JI PARANA",
    "service_type": "Manutenção",
    "subject": "Suporte Externo Fibra Urbana"
  },
  "calculated_at": "2026-07-20T20:30:00Z"
}
```

## Responsabilidades

| Produtor | Consumidor | Dados | Regra |
|---|---|---|---|
| Operação Analítica | Gamificação | situação de SLA, duração, garantia, classificação e identidade da O.S. | Operação mede; Gamificação decide pontos e pagamento. |
| Identidade | Todos os módulos | usuário, permissões e escopo | cada API valida autorização no servidor. |
| IXC | Operação Analítica | dados brutos e atualizações | dados são normalizados, auditados e versionados antes de consumo. |

## Regras de compatibilidade

- `source` e `source_order_id` formam a identidade externa da O.S.
- Datas devem trazer offset ou UTC explícito.
- Valores ausentes devem ser `null`; não usar textos como "não informado" em contratos de integração.
- O consumidor deve ignorar campos novos que não reconhece.
- A alteração de significado de um campo exige uma versão nova do contrato.
- A Gamificação não atualiza o resultado operacional; ajustes de pontos permanecem em seu próprio domínio.
