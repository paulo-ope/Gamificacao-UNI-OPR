# Especificação técnica — Saldo de pontos para garantias detectadas após o pagamento

Status: proposta para implementação · Autor: Claude (Cowork) · Data: 2026-07-07

## 1. Problema atual (confirmado no código)

O motor de reincidência/garantia (`services/scoring_detail.py:recurrence_penalties`) só considera como **O.S. "original"** as ordens que estão dentro do período (`orders`) passado para `calculate_scores` — ou seja, apenas as O.S. do mês/regional que está sendo apurado (`services/calculation.py:calculate_scores`, que chama `_period_orders` → `scoring_detail.period_orders`, filtrado por mês/ano/regional).

A busca por O.S. "posteriores" (`all_orders`) é ampla (janela `search_window_days` **para frente** a partir da data da O.S. original), mas a lista de **originais candidatas** (`base_orders`) nunca inclui O.S. de meses anteriores.

Consequência prática: se uma O.S. de julho é paga (run com `status="paid"`) e só em agosto surge a O.S. de garantia/retorno, o par nunca é avaliado — nem no fechamento de julho (a O.S. de agosto ainda não existia) nem no de agosto (a O.S. de julho não está no escopo de "originais" daquele cálculo). Hoje isso significa que **nenhum desconto acontece**. Além disso, mesmo que o motor tentasse reavaliar julho, `services/calculation_closure.py:ensure_period_not_paid` bloqueia recálculo de período pago a menos que se crie uma "revisão" (`allow_paid_revision=True`), que gera um novo `CalculationRun` em `draft` **paralelo**, sem efeito sobre o pagamento já feito.

## 2. Objetivo da nova lógica

Quando uma garantia/reincidência técnica for identificada em um mês **N+1** (ou posterior) referente a uma O.S. original de um mês **N** cujo `CalculationRun` já está `paid`, o sistema deve:

1. Não tentar alterar o `CalculationRun` pago de N (ele permanece intocado, imutável).
2. Lançar um **débito no saldo de pontos do colaborador**, no valor equivalente ao que seria descontado da O.S. original (respeitando o `recurrence_action` já configurado — `annul_original`, `subtract_original`, `no_penalty`, `requires_review`).
3. Aplicar esse débito automaticamente na próxima apuração (`CalculationRun`) desse colaborador, reduzindo os pontos daquele mês.
4. Se o débito for maior que os pontos do mês seguinte, o saldo fica **negativo e continua sendo carregado** para os meses seguintes até ser totalmente compensado.
5. Registrar tudo em auditoria (`AuditLog`), com rastreabilidade: O.S. original, O.S. de garantia que disparou o débito, valor, mês de origem e mês de aplicação.

Decisões já confirmadas com o dono do produto:
- Classificações que disparam débito no saldo: `garantia` e `reincidencia_tecnica` (mesmo conjunto de `RECURRENCE_DISCOUNT_CLASSIFICATIONS` hoje usado no mesmo período).
- Valor do débito: equivalente à pontuação da O.S. original (`order_points(original)`), respeitando o `recurrence_action` configurado (se for `subtract_original`, usa `recurrence_penalty_points`; se `no_penalty`, não gera débito; se `requires_review`, gera pendência de revisão em vez de débito automático).
- Saldo insuficiente no mês seguinte: pode ficar negativo e ser levado adiante (carry-over) até quitar, registrado em auditoria a cada mês.

## 3. Novas entidades de dados

Adicionar em `backend/app/models.py`:

```python
class CollaboratorPointBalance(Base):
    """Saldo corrente (rolling) de pontos de garantia por colaborador."""
    __tablename__ = "collaborator_point_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id"), unique=True, nullable=False, index=True
    )
    balance_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    # negativo = colaborador ainda "deve" pontos de garantias pós-pagamento anteriores
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    collaborator: Mapped["Collaborator"] = relationship()


POINT_BALANCE_ENTRY_TYPES = ("post_payment_warranty_debit", "period_settlement", "manual_adjustment")


class PointBalanceEntry(Base):
    """Lançamento (ledger) de cada movimentação no saldo de pontos."""
    __tablename__ = "point_balance_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collaborator_id: Mapped[int] = mapped_column(ForeignKey("collaborators.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    points: Mapped[float] = mapped_column(Float, nullable=False)
    # negativo = débito (reduz saldo/pagamento), positivo = crédito/estorno

    # origem do lançamento (garantia detectada tardiamente)
    original_service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    related_service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    origin_calculation_run_id: Mapped[int | None] = mapped_column(ForeignKey("calculation_runs.id"), nullable=True)
    # CalculationRun (pago) do período original, ex.: julho

    # aplicação do lançamento (quando ele efetivamente abateu pontos de algum mês)
    applied_calculation_run_id: Mapped[int | None] = mapped_column(ForeignKey("calculation_runs.id"), nullable=True)
    applied_reference_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    # pending -> aguardando a próxima apuração do colaborador
    # applied -> já abatido total ou parcialmente em algum CalculationRun
    # reverted -> estornado manualmente

    recurrence_classification: Mapped[str | None] = mapped_column(String(60), nullable=True)
    recurrence_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
```

Por que ledger + saldo agregado (e não só um campo no `Collaborator`): o ledger dá rastreabilidade individual por O.S./mês (essencial para a auditoria pedida) e permite reconstruir o saldo a qualquer momento; o `CollaboratorPointBalance` é só um cache do saldo corrente para consulta rápida (pode ser recalculado por `SUM(points)` do ledger se divergir).

Adicionar em `CollaboratorScore` (tabela `collaborator_scores`) dois campos para deixar visível no fechamento de cada mês quanto veio de saldo:

```python
    balance_adjustment_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, default=0, nullable=False)
```

Migration Alembic nova em `backend/alembic/versions/` (seguir o padrão de `20260612_0002_phase2_import_audit.py`): cria as duas tabelas, os dois campos novos em `collaborator_scores`, e índices em `collaborator_id`, `status`, `applied_calculation_run_id`.

## 4. Onde e quando detectar a garantia "tardia" (pós-pagamento)

Criar `services/point_balance.py` com a função central:

```python
def detect_post_payment_warranty_debits(db: Session, later_orders: list[ServiceOrder]) -> list[PointBalanceEntry]:
    ...
```

Ela deve rodar em dois gatilhos:

1. **No fim de cada importação bem-sucedida** (`services/upvalue_importer.py:import_upvalue_service_orders`, depois que as linhas foram criadas/atualizadas): para cada O.S. nova/alterada que entrou como "posterior" válida, procurar candidatas "originais" na mesma identidade (`login`/`contract`, reaproveitando `_configured_recurrence_identity_fields` e `_recurrence_identity_for_fields` de `scoring_detail.py`) dentro da janela de reincidência (`recurrence_window_days`), cujo `ServiceOrder` pertença a um período **já pago** (`calculation_closure.find_paid_run_for_period(db, mes_original, ano_original, regional_original)` retorna não-nulo).
2. **No início de `calculate_scores`** para o período/regional que está sendo apurado (mês N+1 em diante), como rede de segurança para pares que não foram detectados na importação (ex.: importação manual antiga, ou reprocessamento). Rodar antes de montar `details_by_collaborator`.

Para cada par candidato, reaproveitar `scoring_detail.classify_recurrence_pair(original, later, days_between, window_days, rules, identity_label)` — a mesma função já usada para reincidência dentro do período — para decidir a classificação. Só seguir adiante se `classification in RECURRENCE_DISCOUNT_CLASSIFICATIONS` (`{"garantia", "reincidencia_tecnica"}`).

Importante (evitar duplicidade): antes de criar um novo `PointBalanceEntry`, verificar se já existe um lançamento com o mesmo `(original_service_order_id, related_service_order_id)` — se sim, não duplicar (idempotência, já que tanto a importação quanto o cálculo podem tentar detectar o mesmo par).

Também não gerar o lançamento se a O.S. original já está fora de um período pago — nesse caso o fluxo normal de `recurrence_penalties` já resolve dentro do mesmo cálculo (não mexer nesse caminho existente).

## 5. Cálculo do valor do débito (reaproveitando `recurrence_action`)

Reaproveitar a mesma configuração (`AppSetting` `recurrence_action`, valores `annul_original` | `subtract_original` | `no_penalty`/`nao_penaliza` | `requires_review`, lidos hoje em `scoring_detail.recurrence_penalties`) para decidir o valor do lançamento:

- `annul_original` (padrão): `points = order_points(original, scoring_rules_lookup)` (mesma função `scoring_detail.order_points`, usando a matriz de pontuação **vigente no momento da detecção** — não o snapshot antigo do run pago, já que a regra pode ter mudado; deixar isso documentado como decisão consciente, ou alternativamente usar `original_run.config_snapshot` para reproduzir a régua vigente à época — **decisão de produto a confirmar**, ver seção 9).
- `subtract_original`: `points = abs(configured_points)` (setting `recurrence_penalty_points`).
- `no_penalty`/`nao_penaliza`: não cria lançamento de débito (mas pode opcionalmente registrar um evento neutro em auditoria para rastreabilidade).
- `requires_review`: cria o `PointBalanceEntry` com `status="pending"` mas `points=0` e uma flag/observação de revisão manual (reaproveitar padrão de `requires_manual_review` já usado em `scoring_detail.py`), para um humano decidir o valor antes de aplicar.

`points` no `PointBalanceEntry` é sempre gravado como valor **negativo** (débito), ex.: `-15.0` para uma O.S. de manutenção de 15 pontos.

## 6. Aplicação do débito na apuração do mês seguinte

Em `services/calculation.py:calculate_scores`, depois de calcular `summary = scoring_detail.summarize_details(...)` para cada colaborador (linha ~315) e antes de gravar o `CollaboratorScore`:

```python
pending_entries = point_balance.pending_entries_for_collaborator(db, collaborator.id)
balance_before = point_balance.current_balance(db, collaborator.id)
adjustment = point_balance.apply_pending_entries(
    db,
    collaborator=collaborator,
    calculation_run=run,
    reference_month=month,
    reference_year=year,
    available_points=float(summary["final_points"]),
    pending_entries=pending_entries,
    user=... ,  # usuário que disparou o cálculo (executed_by), se houver
)
summary["final_points"] = round(float(summary["final_points"]) + adjustment["applied_points"], 2)
summary["estimated_payment"] = round(float(summary["final_points"]) * multiplier_ajuste_se_necessario * value_per_point, 2)
```

Regra de `apply_pending_entries`:
- Soma todos os `PointBalanceEntry` com `status="pending"` do colaborador (ordenados por `created_at`, do mais antigo para o mais novo — FIFO).
- `applied_points = min(0, available_points_do_mes + soma_dos_debitos_pendentes) - available_points_do_mes` alternativamente, mais simples: `new_total = available_points + soma_debitos_pendentes` (soma é negativa); se `new_total >= 0`, todos os lançamentos pendentes são marcados `applied` (débito total absorvido neste mês); se `new_total < 0`, os lançamentos são marcados `applied` mesmo assim (o débito foi "usado" neste mês), mas o saldo negativo restante (`new_total`) fica registrado no `CollaboratorPointBalance.balance_points` e **um novo `PointBalanceEntry`** de tipo `period_settlement` é criado com `points = new_total` (negativo) e `status="pending"`, para ser novamente descontado no mês seguinte (carry-over contínuo).
- Nunca deixar `final_points` do mês negativo no `CollaboratorScore` exibido — a UI deve mostrar `final_points = max(new_total, 0)` para pagamento, mas o `balance_after` no `CollaboratorScore` mostra o saldo real (pode ser negativo) para transparência.
- Gravar em `CollaboratorScore.balance_adjustment_points` a soma aplicada naquele mês, e em `balance_after` o saldo resultante.

Atualizar `CollaboratorPointBalance.balance_points` do colaborador ao final.

## 7. Auditoria (requisito explícito do usuário)

Todo lançamento e toda aplicação devem gerar `AuditLog` via `services/audit_log.record_audit_log` (já usado em quase todas as rotas hoje):

1. **Na detecção** (criação do débito): `action="point_balance_debit_created"`, `entity="point_balance_entry"`, `entity_id=entry.id`, `before_data=None`, `after_data=snapshot(entry)`. Incluir no `reason` do próprio `PointBalanceEntry` texto legível, ex.: `"Garantia detectada em 05/08/2026 pela O.S. UPV-XXXX (agosto) referente à O.S. original OS-1234 (julho, período já pago em CalculationRun #48). Débito de 15.0 pontos a aplicar no próximo fechamento do colaborador."`
2. **Na aplicação** (quando o cálculo do mês seguinte consome o lançamento): `action="point_balance_debit_applied"`, `entity="collaborator_score"`, `entity_id=score.id`, `before_data={"balance_before": ...}`, `after_data={"balance_after": ..., "applied_points": ..., "entry_ids": [...]}`.
3. **No carry-over** (quando sobra saldo negativo para o mês seguinte): `action="point_balance_carry_over"`, mesma entidade, com o valor remanescente.
4. **Em estorno manual** (caso um admin precise reverter, ver seção 8): `action="point_balance_debit_reverted"`.

Isso soma-se (não substitui) à auditoria já existente de reincidência dentro do mesmo período, que continua funcionando como está.

## 8. Endpoints e UI necessários (novo, a criar)

- `GET /collaborators/{id}/point-balance`: saldo atual + histórico de lançamentos (para o financeiro/gestor entender por que o pagamento de um mês veio menor).
- `GET /point-balance/pending`: lista todos os débitos pendentes de aplicação no sistema (útil antes de rodar o cálculo do mês).
- `POST /point-balance/entries/{id}/revert` (somente admin, igual regra de `is_admin_user` já usada em `calculation_closure.ensure_status_change_permission`): estorna um lançamento indevido (ex.: diagnóstico de garantia estava errado), com auditoria.
- No `serialize_run` (`services/calculation.py`) e na tela de fechamento, expor `balance_adjustment_points` e `balance_after` por colaborador, para o revisor ver que aquele mês teve desconto vindo de garantia de mês anterior.
- Card no dashboard: "Colaboradores com saldo negativo" (soma de `CollaboratorPointBalance.balance_points < 0`).

## 9. Pontos que exigem decisão explícita antes de implementar

1. **Régua de pontos usada no débito tardio**: usar a matriz de pontuação vigente hoje (`ScoringSubjectRule` atual) ou reproduzir a régua vigente no mês original via `CalculationRun.config_snapshot` daquele período pago? Recomendação: usar o `config_snapshot` do run pago original, para manter justiça (o colaborador é descontado com base na régua que valia quando ganhou aqueles pontos, não com a régua atual que pode ter mudado).
2. **`recurrence_action = requires_review`**: hoje isso só marca revisão manual sem valor calculado. Para o fluxo pós-pagamento, decidir se o mês seguinte deve segurar (bloquear) o fechamento até a revisão ser resolvida, ou seguir sem o desconto e aplicar depois quando resolvido.
3. **Colaborador desligado/inativo com saldo negativo**: o que fazer quando `Collaborator.active=False` e ele nunca mais terá um próximo mês para descontar? Sugestão: manter o lançamento `pending` indefinidamente e mostrar num relatório de "dívidas de garantia de colaboradores inativos" para decisão financeira manual — não implementar baixa automática sem uma regra explícita.
4. **Interação com revisão pós-pagamento (`allow_paid_revision`)**: se alguém cria uma revisão em draft do período pago original para "corrigir" manualmente, isso não deve duplicar o débito já lançado no saldo do mês seguinte. Regra proposta: revisões (`draft` criado via `allow_paid_revision=True`) nunca disparam a detecção de garantia tardia (ela só olha para `CalculationRun.status == "paid"` original, e revisões não pagam automaticamente).

## 10. Resumo do plano de implementação (ordem sugerida)

1. Migration + models novos (`CollaboratorPointBalance`, `PointBalanceEntry`, colunas novas em `collaborator_scores`).
2. `services/point_balance.py`: `detect_post_payment_warranty_debits`, `pending_entries_for_collaborator`, `current_balance`, `apply_pending_entries`, `revert_entry` — todos gravando `AuditLog`.
3. Hook na importação (`upvalue_importer.import_upvalue_service_orders`) chamando a detecção ao final, por O.S. importada.
4. Hook em `calculation.calculate_scores`: detecção de segurança no início + aplicação do saldo por colaborador antes de persistir `CollaboratorScore`.
5. Schemas Pydantic (`schemas.py`) para os novos endpoints.
6. Rotas novas (`api/routes/point_balance.py` ou dentro de `collaborators.py`/`calculation_runs.py`).
7. Ajustes de UI (frontend) para exibir saldo, histórico e alerta de saldo negativo.
8. Testes: (a) garantia dentro do mesmo período continua funcionando como hoje; (b) garantia detectada em N+1 contra original pago em N gera débito e aplica em N+1; (c) débito maior que os pontos de N+1 gera carry-over para N+2; (d) `no_penalty`/`requires_review` não geram débito automático; (e) idempotência (mesmo par não gera dois lançamentos); (f) auditoria criada em cada etapa.

## Arquivos-chave já lidos e referenciados nesta spec

`backend/app/models.py`, `backend/app/services/calculation.py`, `backend/app/services/calculation_closure.py`, `backend/app/services/scoring_detail.py`, `backend/app/services/audit_log.py`, `backend/app/services/upvalue_importer.py` (fluxo de importação e chamada de auditoria por linha).
