# Estudo — Viabilidade de recriar o frontend com base no backend atual

Status: proposta para validação · Autor: Claude (Cowork) · Data: 2026-07-30

## 1. Contexto e o que motivou este estudo

O usuário percebe o frontend atual como "poluído" e quer saber se, dado que o backend já está maduro e estável, seria viável recriar o frontend do zero em cima dele. Este estudo levanta os fatos concretos (tamanho da superfície de API, estado real do código atual, cobertura de testes) para responder isso com números, não impressão.

## 2. O backend hoje: superfície e contrato

| Métrica | Valor |
|---|---|
| Endpoints totais | **189**, em 20 arquivos de rota |
| Classes Pydantic (`BaseModel`) | **213** |
| Testes de backend | 21 arquivos, 5.481 linhas |
| OpenAPI/Swagger | Habilitado por padrão (`/docs`, `/openapi.json`) — nenhuma rota desabilita o schema |

Distribuição dos endpoints por área:

| Área | Arquivo | Endpoints |
|---|---|---|
| Operação analítica | `modules/operations/router.py` | 45 |
| Agendamento | `modules/scheduling/router.py` | 19 |
| Regras de pontuação | `api/routes/rules.py` | 13 |
| Portal do colaborador | `api/routes/portal.py` | 12 |
| Colaboradores | `api/routes/collaborators.py` | 12 |
| Scoring/cálculo | `api/routes/scoring.py` | 17 |
| Liderança | `api/routes/leadership.py` | 10 |
| Gestão de ecossistema | `modules/management/router.py` | 8 |
| Importações | `api/routes/imports.py` | 8 |
| Config. de gamificação | `api/routes/gamification.py` | 7 |
| Fechamentos | `api/routes/calculation_runs.py` | 6 |
| Admin | `modules/admin/router.py` | 6 |
| Auditoria | `api/routes/audit.py` | 5 |
| O.S | `api/routes/service_orders.py` | 5 |
| Dashboard | `api/routes/dashboard.py` | 3 |
| Usuários / Auth / Settings / Saldo / Health | 4 arquivos | 15 |

**Leitura**: o backend é grande (189 endpoints é bastante superfície), tipado de ponta a ponta com Pydantic, e já expõe um contrato OpenAPI completo sem precisar de nenhum trabalho extra. Isso significa que um cliente TypeScript tipado poderia ser **gerado automaticamente** a partir do `/openapi.json` (com `openapi-typescript`, `orval` ou similar), em vez de escrito à mão como hoje.

## 3. O frontend hoje: onde está a "poluição"

| Métrica | Valor |
|---|---|
| Páginas (`app/**/page.tsx`) | 7 |
| Arquivos `.tsx`/`.ts` totais | 108 (29.491 linhas) |
| Testes de frontend | 5 arquivos, 399 linhas — **zero teste de componente, página ou E2E** |
| Chamadas HTTP fora dos clients de API | 0 (bom sinal — tudo passa por `lib/api.ts` e afins) |
| Arquivos com `type`/`interface` fora de `lib/types.ts` | 44 |

Os 10 maiores arquivos concentram a maior parte da complexidade:

| Arquivo | Linhas |
|---|---|
| `components/gamification/logic-configuration-panel.tsx` | 3.081 |
| `app/operacao/page.tsx` | 2.233 |
| `app/gamificacao/page.tsx` | 2.056 |
| `app/agendamento/page.tsx` | 1.865 |
| `components/operations/operations-team-configuration.tsx` | 1.560 |
| `components/operations/operations-monthly-calendar.tsx` | 1.505 |
| `components/operations/operations-filter-panel.tsx` | 1.167 |
| `components/gamification/collaborator-registry-panel.tsx` | 959 |
| `components/gamification/leadership-bonus-panel.tsx` | 880 |
| `components/gamification/audit-panel.tsx` | 830 |

Esses 10 arquivos somam **~16.200 linhas** — mais da metade do frontend inteiro está concentrada em 10 componentes/páginas. Isso confirma a percepção: a "poluição" não está espalhada uniformemente, está concentrada em telas específicas (configuração de gamificação, operação analítica, agendamento) que acumularam funcionalidade ao longo do tempo sem serem quebradas em partes menores.

A fragmentação de tipos (44 arquivos com tipos locais próprios) é sintoma do mesmo problema: cada tela cresceu isolada, duplicando definições em vez de reaproveitar `lib/types.ts`.

## 4. O que uma recriação aproveitaria de graça

- **Geração automática de cliente TypeScript** a partir do OpenAPI — elimina a manutenção manual de `lib/api.ts` (650 linhas), `lib/operations-api.ts` (1.080 linhas) e `lib/scheduling-api.ts` (345 linhas), e resolve a fragmentação de tipos de uma vez (tipos gerados diretamente dos schemas Pydantic, sempre em sincronia com o backend).
- **Nenhuma mudança no backend é necessária** — os 189 endpoints e as regras de negócio (todas as que auditamos nesta conversa: garantia, liderança, reincidência, saúde operacional) continuam intocadas. O risco de regressão fica 100% concentrado no frontend.

## 5. O risco real não é o backend — é a falta de rede de segurança no frontend

Este é o ponto mais importante do estudo: **o frontend atual não tem nenhum teste de componente, página ou E2E**. Os 5 testes existentes cobrem só funções utilitárias isoladas em `lib/`.

Isso significa que, hoje, a única forma de saber se uma tela "faz a coisa certa" é abrir no navegador e testar manualmente — e ao longo desta conversa vimos repetidamente telas com regras de negócio não-óbvias acumuladas (ex.: como a auditoria de garantia interpreta status "reincidência" vs "demanda diferente", como a config de liderança valida sobreposição de filial, como o painel de saldo de pontos distingue "pendente" de "carry-over"). Uma recriação do zero, sem antes capturar essas regras em testes ou documentação, corre o risco real de **perder comportamento que não está escrito em lugar nenhum além do próprio código da tela atual** — e isso só apareceria depois, em produção, como os bugs de garantia/liderança que auditamos nesta mesma conversa.

## 6. Duas abordagens possíveis

### A. Recriação completa ("big bang")
Jogar fora o frontend atual, gerar cliente TS do OpenAPI, redesenhar as 7 páginas do zero.

- **Vantagem**: resultado final mais limpo, sem carregar decisões de design antigas.
- **Risco**: 29.491 linhas acumularam ~1 ano de correções reais (o histórico de commits desta sessão mostra isso claramente: fixes de garantia, liderança, SLA, etc.). Recriar do zero sem migrar esse conhecimento é o cenário de maior risco de regressão silenciosa, especialmente sem testes E2E para pegar o que quebrar.
- **Esforço**: alto, tudo de uma vez, app fica "em obra" até terminar.

### B. Extração incremental por módulo
Manter o app no ar, e substituir **um módulo por vez** (ex.: comece pelo menor/menos crítico — Dashboard ou Admin — e só migre para Operação/Gamificação depois de validar o padrão), gerando o cliente TS do OpenAPI desde o primeiro módulo.

- **Vantagem**: cada módulo migrado pode ser comparado lado a lado com a versão antiga antes de substituir de fato. Risco de regressão fica contido a um módulo por vez. O app nunca fica indisponível.
- **Risco**: mais tempo total até o frontend inteiro estar "novo"; por um período, o app roda com um design misto (telas antigas + novas).
- **Esforço**: espalhado, mais fácil de encaixar entre outras demandas.

## 7. Recomendação

Backend está pronto — isso é fato, confirmado pelos números. Mas dado que **zero das regras de negócio do frontend estão cobertas por teste automatizado**, a abordagem B (incremental, módulo por módulo, começando pelo menor) é a que carrega menos risco de perder comportamento sem ninguém notar. O "big bang" só seria razoável se antes disso fosse escrita uma suíte de testes E2E cobrindo o comportamento atual das telas mais complexas (os 10 arquivos gigantes listados na seção 3) — o que é, na prática, quase o mesmo trabalho de já ter feito a extração incremental.

## 8. Decisões que precisam do dono do produto

1. Big bang ou incremental por módulo? (recomendação: incremental)
2. Se incremental, qual módulo migrar primeiro — o menor (Dashboard/Admin, baixo risco, valida o padrão) ou o mais "poluído" (Config. de gamificação — `logic-configuration-panel.tsx`, 3.081 linhas — maior ganho percebido, mas maior risco)?
3. Vale investir em gerar o cliente TS a partir do OpenAPI já no frontend atual (sem trocar as telas), como primeiro passo independente que já reduz a fragmentação de tipos hoje, antes de decidir sobre recriar telas?
4. Escrever testes E2E das telas atuais antes de tocar nelas é um investimento aceitável, mesmo sabendo que parte desse esforço "não sobra" pro frontend novo (o teste E2E de tela antiga não se aproveita 1:1 na tela nova)?
