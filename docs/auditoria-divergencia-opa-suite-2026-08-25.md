# Auditoria — Divergências SGP Suporte (UNI Workspace) vs. painel oficial OPA Suite

Data: 2026-08-25. Investigação técnica pura — nenhuma alteração de código feita
nesta etapa. Ver [docs/plano-analise-opa-suite-atendimentos.md](plano-analise-opa-suite-atendimentos.md)
para o contexto das fases já implementadas.

## Confirmação de alinhamento

`docs/STATUS.md` e `docs/00-TRILHA-0.md` batem com o código real (Fases 2, 3A,
3B, 3C concluídas, nada mudou desde a última atualização). Sem divergência
documental — a investigação abaixo é sobre divergência de **dado**, não de
código desatualizado.

## Limitação desta auditoria

Não tenho acesso ao painel oficial do OPA Suite (é uma tela em outro sistema,
fora deste repositório, e não tenho credenciais/URL dela). Tudo abaixo foi
apurado comparando **nosso banco de dados, nosso código e a API real do OPA
Suite** (`https://opasuite.souuni.com`, testada ao vivo). Onde não dá pra
confirmar o comportamento exato do painel oficial sem acesso a ele, isso está
marcado explicitamente como **hipótese**, não fato.

---

## 1. Divergência de quantidade de atendimentos

### Fato confirmado — causa mais provável: sincronização automática está desligada

```sql
SELECT key, value FROM app_settings WHERE key LIKE 'support_opa_sync%';
-- support_opa_sync_enabled = false
```

O UNI Workspace **não atualiza sozinho**. Os dados só mudam quando alguém
clica "Importar dados" manualmente na aba Sincronização. O último import
completo (`run 30`, cobrindo 2026-08-01 a 2026-08-25) terminou às
**17:31:39 UTC de hoje (13:31 em Porto Velho)**. Qualquer atendimento aberto
no OPA Suite depois desse horário **não existe ainda no UNI**, enquanto o
painel oficial do OPA (se for ao vivo) mostra tudo até o segundo atual.

**Se a comparação de volume foi feita "hoje" ou num período recente, isso
sozinho já explica boa parte da diferença** — não é bug de cálculo, é
defasagem de sincronização.

```sql
SELECT id, date_from, date_to, mode, finished_at, status
FROM support_opa_import_runs WHERE status='completed' ORDER BY id DESC LIMIT 5;
```

### Fato confirmado — importações antigas tiveram rejeição, mas foram corrigidas depois

```sql
SELECT status, mode, count(*), sum(rejected_count), sum(fetched_count), sum(created_count)
FROM support_opa_import_runs GROUP BY 1,2 ORDER BY 1,2;
```

Houve 21.106 registros rejeitados no total, concentrados em:
- 5 runs de 2026-08-16 (bootstrap/teste inicial, 100% rejeitado, 0 criado) — de
  antes do mapeamento de campos real ter sido corrigido (mesma época da
  `docs/auditoria-evolucao-opa-suite-2026-08-16.md`).
- 1 run de 2026-08-20 com 106 rejeitados de 2.608.

**Fato**: os dois casos foram **superados por reimportações completas
posteriores** (`run 21` e `run 30`) que cobriram os mesmos períodos com
`rejected_count = 0`. A contagem atual do banco (53.482) bate exatamente com
o `fetched_count` acumulado do último `run 30` completo. **Não há indício de
que rejeições antigas estejam causando um buraco de dados hoje.**

```sql
SELECT date(opened_at) dia, to_char(opened_at,'Dy') dow, count(*)
FROM support_opa_attendances GROUP BY 1,2 ORDER BY 1;
```

Confirma também que o dia mais baixo (2026-08-16, 461 atendimentos) é
**domingo**, na mesma faixa dos outros domingos do mês (537, 548, 480) — não é
um buraco de importação, é volume normal de fim de semana.

### Hipótese — critério de data pode divergir do painel oficial

O UNI filtra **só por `opened_at` (abertura)**, nunca por `closed_at`
(`backend/app/modules/support/opa_filters.py::opa_period_bounds`). Se o
painel oficial do OPA contar "atendimentos do dia" por data de encerramento,
por última interação, ou por outro campo, os totais de um dia específico vão
divergir — principalmente em atendimentos que atravessam a virada do dia.
**Não dá pra confirmar isso sem ver o painel oficial ou a documentação do
critério dele** — fica como pergunta para o usuário/fornecedor.

### Fato confirmado — sem duplicidade nem paginação perdida

`source_id` tem `UNIQUE CONSTRAINT` (`uq_support_opa_attendances_source_id`),
então duplicidade de atendimento é estruturalmente impossível no banco. A
paginação usa checkpoint com `next_skip` persistido e reimport idempotente
(`updated_count` em vez de duplicar) — testado em
`test_opa_attendances_processes_all_pages_without_fixed_1000_limit`.

---

## 2. Divergência de TMR

### Como o UNI calcula hoje (fato, direto do código)

- `tmr_seconds`: média dos intervalos entre uma mensagem do **cliente** e a
  próxima mensagem de um atendente **humano** (`tipo != "bot"` no
  `/api/v1/usuario`), ignorando completamente mensagens de bot (não fecham
  nem resetam o intervalo pendente). Calculado em
  `opa_ingestion._human_response_metrics`.
- `first_response_at`: instante da **primeira** dessas respostas humanas na
  conversa — separado da média das seguintes.
- `average_tmr_seconds` (`/opa/overview`, summary por atendente): `AVG(tmr_seconds)`
  simples sobre o conjunto filtrado.
- `average_first_response_seconds`: calculado em Python (não SQL) como média
  de `first_response_at - opened_at`, só sobre linhas com `first_response_at`
  preenchido.

### Fato confirmado — `usuario.tipo` está bem preenchido

```sql
SELECT count(*), count(*) FILTER (WHERE payload_json->>'tipo' IS NOT NULL),
       count(*) FILTER (WHERE payload_json->>'tipo'='bot')
FROM support_opa_dimensions WHERE dimension_type='user';
-- 244 total, 244 com tipo, 10 bots
```

Só 2 de 148 atendentes distintos (e só 2 atendimentos no total) não têm
correspondência na dimensão — impacto irrelevante na exatidão do TMR.

### Fato confirmado — cobertura de TMR é maior que a política documentada

```sql
SELECT count(*), count(*) FILTER (WHERE tmr_seconds IS NOT NULL),
       count(*) FILTER (WHERE handled_by_bot IS NOT NULL)
FROM support_opa_attendances;
-- 53.482 total | 22.162 com tmr_seconds | 53.306 classificados bot/humano
```

A política documentada era "TMR só vale pra importações novas a partir de
25/08, sem backfill". **Na prática isso não é mais verdade**: o `run 30`
(reimportação manual completa de 01/08 a 25/08, feita hoje) reprocessou TODO
o mês com o código já corrigido — e como a ingestão é idempotente e recalcula
esses campos em toda atualização, isso **backfilled de fato** TMR/bot-humano
para praticamente todo o histórico (99,7% classificado). Isso é bom para
completude, mas quer dizer que a promessa "sem chamada extra em massa à API
do OPA" foi rompida por uma reimportação manual ampla — vale confirmar com o
usuário se isso foi intencional.

### Fato confirmado — por que 24.187 atendimentos não têm TMR

```sql
SELECT count(*) FROM support_opa_attendances WHERE handled_by_bot=true AND reached_human=false;
-- 24.187
```

45% dos atendimentos nunca chegaram a um humano (só bot) — TMR humano
corretamente `NULL`, não é bug.

### Fato confirmado — os 6.957 casos "chegou a humano mas TMR nulo" são legítimos

```sql
SELECT count(*) FROM support_opa_attendances
WHERE handled_by_bot IS NOT NULL AND tmr_seconds IS NULL AND reached_human=true;
-- 6.957
```

Amostra manual (atendimento `6a79ebb6fece2ebb4df0c010`, thread de mensagens
buscada ao vivo): só existem mensagens do atendente humano, **nenhuma do
cliente**. Sem mensagem de cliente pra responder, TMR fica `NULL`
corretamente — comportamento certo, não bug.

### Hipótese forte — a definição de TMR do painel oficial provavelmente é diferente

Não consegui confirmar a fórmula exata do painel oficial (sem acesso a ele).
Cenários mais prováveis, por ordem de probabilidade:

1. **TMR do OPA inclui as respostas do bot.** Como o bot responde quase
   instantaneamente (testado: 5–15 segundos) e domina o volume (18.849 de
   53.482 atendimentos são só do "Theo", o bot), um TMR que misture bot com
   humano tende a ficar **muito mais baixo** que o TMR humano puro que o UNI
   calcula. Se o painel oficial mostra um número bem menor que o do UNI, essa
   é a explicação mais provável.
2. Painel oficial pode calcular TMR só sobre atendimentos **finalizados**
   (`status=F`), enquanto o UNI inclui qualquer atendimento com
   `tmr_seconds` calculável, independente do status atual.
3. Painel oficial pode agregar por **encerramento**, não por abertura — um
   atendimento pode ter TMR computado no dia em que foi respondido, mas cair
   num "dia" diferente se o critério de agrupamento for outro campo.

**Decisão do usuário necessária**: confirmar com o print/export do painel
oficial (ou com o suporte do OPA Suite) se o TMR deles inclui bot ou não, e
se filtra por status. Sem isso, não dá pra saber qual das duas definições
"está errada" — podem ser, ambas, definições válidas mas diferentes.

---

## 3. Código do cliente aparecendo em vez do nome

### Fato confirmado e causa raiz identificada — sincronização de clientes truncada em 50.000

```python
# backend/app/services/opa_client.py
def list_clients(self) -> list[dict[str, Any]]:
    return self.list_collection("/api/v1/cliente/", max_records=50000)
```

```sql
SELECT count(*) FROM support_opa_dimensions WHERE dimension_type='customer';
-- exatamente 50.000
```

Testei ao vivo contra a API real do OPA Suite pedindo registros além desse
limite:

```bash
curl .../api/v1/cliente/ -d '{"filter":{},"options":{"limit":2,"skip":100000}}'
# retorna registros reais (ex.: "LUZIA DE LIMA MACHADO", id "99811")
```

**A base real de clientes do OPA Suite tem mais de 100.000 registros. O UNI
só sincroniza os primeiros 50.000** (limite fixo no código, não da API).
Qualquer atendimento cujo cliente esteja fora dessa primeira leva nunca
ganha nome.

```sql
SELECT count(*) FROM support_opa_attendances a
WHERE a.customer_id IS NOT NULL AND (a.customer_name IS NULL OR a.customer_name='')
AND NOT EXISTS (SELECT 1 FROM support_opa_dimensions d
                WHERE d.dimension_type='customer' AND d.source_id=a.customer_id AND d.name IS NOT NULL);
-- 33.866
```

De 45.491 atendimentos com `customer_id`, só 11.625 (25,6%) têm nome —
**33.866 clientes referenciados simplesmente não existem no conjunto
sincronizado**, não é falha de lookup nem de backfill.

### Fato confirmado — `_backfill_customer_names` funciona corretamente

```sql
SELECT count(*) FROM support_opa_attendances a
WHERE a.customer_id IS NOT NULL AND (a.customer_name IS NULL OR a.customer_name='')
AND EXISTS (SELECT 1 FROM support_opa_dimensions d
            WHERE d.dimension_type='customer' AND d.source_id=a.customer_id AND d.name IS NOT NULL);
-- 0
```

Zero casos de "nome existe na dimensão mas não foi propagado" — a rotina de
backfill (`opa_ingestion._backfill_customer_names`) está correta. **O
problema é 100% de cobertura de sincronização, não de lookup.**

### Fato confirmado — payload do atendimento nunca traz nome embutido

Testado ao vivo: `/api/v1/atendimento` (listagem) sempre devolve `id_cliente`
como string simples (só o ID), nunca como objeto com nome — só
`/api/v1/atendimento/{id}` (detalhe individual) expande pra objeto com nome,
e isso só é chamado sob demanda por atendimento no drawer de detalhe, não em
massa na importação. Então a única fonte de nome em volume é mesmo a
dimensão `/api/v1/cliente/`, que está truncada.

### Frontend — auditoria de onde código aparece

| Local | Comportamento atual |
|---|---|
| `frontend/app/suporte/page.tsx` — tabela Dados (`AttendanceRow`) | Já prefere nome; sem nome mostra **"Cliente sem nome cadastrado"** (não o código bruto) como texto principal, código aparece só como legenda secundária pequena |
| `frontend/app/suporte/page.tsx` — drawer do atendente, "Atendimentos recentes" | Mesmo padrão acima (reusa `customerNameLabel`/`customerCodeLabel`) |
| `frontend/app/suporte/page.tsx` — drawer de detalhe do atendimento, bloco "Cliente" | Mesmo padrão — campo "Cliente" mostra "Cliente sem nome cadastrado", campo "Código do cliente" é separado |
| `frontend/app/suporte/_components/opa-module-components.tsx:736` — **`TopRecurringCustomers`** (ranking de clientes recorrentes, Fase 2) | **Aqui sim mostra o código bruto como texto principal** quando não há nome: `{item.customer_name ?? item.customer_id ?? "Não identificado"}` — sem o wrapper "sem nome cadastrado" usado em todo o resto da tela. **Este é o ponto concreto que mais provavelmente gerou a reclamação.** |
| `backend/app/modules/support/router.py::_opa_breakdown_rows` (dimensão `customer` de `/opa/breakdowns`) | O próprio backend usa `COALESCE(MAX(customer_name), customer_id, 'Não identificado')` como `label` — se não há nome, o `label` retornado já É o código. Não está renderizado em nenhuma tela hoje (não encontrei consumo desse breakdown por cliente no frontend), mas é uma inconsistência latente caso alguém use esse endpoint no futuro. |

---

## Resumo — fatos vs. hipóteses vs. decisão do usuário

**Fatos confirmados (evidência direta, sem necessidade de decisão):**
- Sincronização automática está desligada; dado é sempre um retrato do
  último import manual.
- Rejeições antigas de importação já foram corrigidas por reimportações
  completas; não há buraco de dado hoje.
- `usuario.tipo` está bem preenchido (100% dos 244 usuários sincronizados).
- TMR humano do UNI está tecnicamente correto nos casos auditados
  manualmente (nulo é nulo por falta real de dado, não por bug).
- Cobertura de TMR ficou muito maior que a política "sem backfill" documentada,
  por causa de uma reimportação manual completa recente.
- Causa raiz do "código em vez de nome": sincronização de clientes truncada
  em 50.000 registros por um limite fixo no código, enquanto a base real do
  OPA Suite tem mais de 100.000.
- `TopRecurringCustomers` no frontend é o ponto concreto que expõe o código
  bruto sem fallback amigável.

**Hipóteses (prováveis, mas não confirmáveis sem acesso ao painel oficial):**
- TMR do painel oficial provavelmente inclui respostas de bot (explicaria
  número bem menor que o do UNI).
- Painel oficial pode filtrar por status finalizado e/ou agrupar por
  encerramento em vez de abertura.

**Decisões que dependem do usuário:**
1. Confirmar a definição real de TMR do painel oficial (bot incluído ou não,
   filtro de status, campo de agrupamento) — só com isso dá pra saber se
   ajusta o cálculo do UNI ou se são métricas diferentes por natureza.
2. Decidir se liga a sincronização automática (`support_opa_sync_enabled`) —
   resolveria a defasagem de volume "hoje", mas tem custo operacional (já
   documentado no plano da integração).
3. Decidir se aumenta/remove o limite de 50.000 na sincronização de clientes
   — impacto: dobrar (ou mais) o tempo/custo da sincronização de dimensões a
   cada importação.
4. Autorizar a correção pontual do `TopRecurringCustomers` (usar o mesmo
   fallback "sem nome cadastrado" já usado no resto da tela) — mudança
   pequena e de baixo risco, mas ainda peço autorização antes de tocar em
   código, conforme pedido.

## Proposta de correção em etapas (não implementada ainda)

1. **Baixo risco, alto impacto** — trocar o fallback de `TopRecurringCustomers`
   pra usar `customerNameLabel`/`customerCodeLabel` como o resto da tela.
2. **Médio risco** — remover ou aumentar substancialmente o `max_records=50000`
   de `list_clients`, com paginação em lote controlada (mesmo padrão já usado
   em `list_attendances`), pra fechar a lacuna real de clientes não
   sincronizados. Precisa medir o tempo real de sincronização com a base
   maior antes de decidir o novo limite.
3. **Depende de decisão do usuário** — se confirmado que o painel oficial
   inclui bot no TMR, avaliar expor **os dois números** (TMR humano e TMR
   com bot) lado a lado no UNI, em vez de substituir um pelo outro — evita
   escolher "qual está certo" quando são, na verdade, métricas diferentes.
4. **Operacional, sem código** — decidir sobre ligar a sincronização
   automática, e rodar uma nova importação manual completa após qualquer uma
   das mudanças acima, pra recalcular clientes/nome em massa.

## Arquivos envolvidos

- `backend/app/services/opa_client.py` (`list_clients`, limite de 50.000)
- `backend/app/modules/support/opa_ingestion.py` (`_backfill_customer_names`,
  `_human_response_metrics`, `_classify_bot_human`, `_load_attendant_types`)
- `backend/app/modules/support/opa_filters.py` (`opa_period_bounds` — critério
  de data)
- `backend/app/modules/support/router.py` (`_opa_breakdown_rows`, label de
  cliente)
- `backend/app/modules/support/opa_overview_service.py` (`customer_metrics`)
- `frontend/app/suporte/page.tsx` (`customerNameLabel`, `customerCodeLabel`)
- `frontend/app/suporte/_components/opa-module-components.tsx`
  (`TopRecurringCustomers`)
- `app_settings` (`support_opa_sync_enabled=false`)
