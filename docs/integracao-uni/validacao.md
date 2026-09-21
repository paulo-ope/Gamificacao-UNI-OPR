# Validação — evidências, divergências e pendências

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data: 2026-09-17 · Ambiente: desenvolvimento local
(`docker compose`, backend já em execução na máquina do autor desta análise, `APP_ENV=development`).

## O que foi de fato executado e verificado nesta análise

| Verificação | Comando/evidência | Resultado |
|---|---|---|
| Backend local respondendo | `curl http://localhost:8000/api/health` | `{"status":"ok"}` — 200 |
| Schema OpenAPI real extraído do FastAPI em execução | `curl http://localhost:8000/openapi.json` | 330 rotas, 392 operações, 518 schemas — salvo em [openapi.yaml](openapi.yaml) sem edição manual do conteúdo gerado pelo FastAPI, só metadados (`info`, `servers`, `tags`) adicionados por cima |
| Rota protegida rejeita chamada sem credencial | `curl -o /dev/null -w "%{http_code}" http://localhost:8000/api/operations/overview` (sem header `Authorization`) | `401` — confirma que a proteção por `Depends(require_permission(...))` está ativa neste ambiente, como o código faz supor |
| Esquemas de segurança declarados no OpenAPI | inspeção do JSON extraído (`components.securitySchemes`) | `HTTPBearer` (Bearer JWT) para a API principal, `APIKeyHeader` (`x-api-key`) para `/api/ai` — confirma a seção 1 de [acesso.md](acesso.md) |
| Sintaxe do script consumidor | `python -m py_compile exemplos/consumidor.py` | sem erro |
| Consistência `catalogo.json` ↔ `catalogo.md` | `catalogo.md` foi gerado **programaticamente** a partir de `catalogo.json` (script descartável, não versionado), não escrito à mão em paralelo | elimina divergência estrutural↔legível por construção |
| Leitura literal completa de 3 arquivos antes só inferidos por uso externo | `backend/app/services/scoring_detail.py` (2382 linhas), `backend/app/services/leadership_bonus.py` (535 linhas), `backend/app/modules/management/cases.py` (lógica de severidade/idempotência/escopo) | Fórmulas de pontuação de O.S., penalidades, bônus de liderança e severidade de caso atualizadas em `catalogo.json`/`catalogo.md` com evidência exata; 2 novos achados técnicos adicionados como gaps (ver abaixo) |

## Atualização — 2026-09-17, ambiente de produção real

- **URL de produção confirmada pelo usuário (dono do sistema, acesso real ao ambiente)**:
  `https://operacao.souuni.com`. Tela de login carregada com sucesso via navegador (título "UNI
  Workspace", mesma identidade visual do sistema documentado) — evidência de que o host é real e
  está no ar. `servers:` de `openapi.yaml` e a tabela de ambientes de `README.md` atualizados.
- **Ainda não verificado em produção**: `APP_ENV` exato do servidor, login efetivo, criação do
  perfil `cubo_corporativo_readonly` e do usuário de serviço (aguardando o usuário executar essas
  etapas manualmente — ver seção abaixo).

## Atualização — 2026-09-21, credencial real criada e testada (desenvolvimento local)

Diferente da entrada de 2026-09-17 (que registrava a criação de credencial como bloqueada), esta
rodada **executou o provisionamento de ponta a ponta** em desenvolvimento local, com o dono do
sistema decidindo os dois pontos que bloqueavam antes (escopo = todos os módulos; canal do segredo
= entrega direta via SSH, sem depender de secrets manager formal). Nada disto foi simulado —
comandos e saídas reais abaixo.

| Verificação | Comando/evidência | Resultado |
|---|---|---|
| `AccessProfile` "Cubo de Dados Corporativo - Leitura" criado | script Python via `docker exec` (ORM direto, mesmo padrão usado para a migration de grupos de SLA) | `profile_id: 9`, 28 permissões, `has_any_write: False` (checado programaticamente contra sufixos `:write`/`:manage`/`:sync`/`:delete`/`:review`/`calculation:run`/`:publish`) |
| Usuário de serviço `cubo-uni@internal.souuni.com` criado | idem | `user_id: 179`, vinculado só a esse perfil |
| Login real | `POST /api/auth/login` com email/senha da conta | `200`, `access_token` (JWT) válido, `user.permissions` com as 28 chaves esperadas |
| Leitura permitida | `GET /api/operations/period` e `GET /api/operations/sla?...` com o Bearer da conta | `200` nos dois |
| Escrita bloqueada | `PUT /api/operations/ixc-sync-settings` e `POST /api/calculation-runs/calculate` com o mesmo Bearer | `403` nos dois — confirma que a restrição é aplicada pelo backend por operação, não só pela ausência de botão na tela |
| Doc de integração acessível pela própria conta | `GET /api/admin/docs/integracao-uni/openapi.json` com o Bearer da conta | `200`, schema com 182 operações, todas `GET` |
| Script consumidor completo (`exemplos/consumidor.py`) rodado de ponta a ponta | `python exemplos/consumidor.py` com `UNI_API_EMAIL`/`UNI_API_PASSWORD` reais, contra `http://localhost:8000/api` | Login automático (28 permissões relatadas pelo próprio script); consulta filtrada de overview (10 campos retornados); **paginação real de 39.183 registros** de atendimentos OPA; consulta do indicador SLA (lista vazia no recorte de teste, resultado válido — sem O.S. com prazo mensurável nesse período/filtro, não é erro); erro 404 tratado corretamente em rota inexistente. Saída completa do script arquivada nesta sessão. |

**Ainda não verificado em produção** (ver [deploy.md](deploy.md) para o status exato e o checklist
de verificação pós-deploy): réplica do perfil/usuário na VM real, login e chamadas de leitura/
escrita contra `https://operacao.souuni.com`, e reexecução do `consumidor.py` apontando pra lá.

## O que NÃO foi executado (pendências reais, não simuladas)

| Item pedido | Status em 2026-09-21 | Como desbloquear o que resta |
|---|---|---|
| Criação da identidade técnica read-only real (usuário/perfil/token) | ✅ **Feito em desenvolvimento local** (ver seção acima). ⏳ Produção pendente. | Réplica em produção — ver [deploy.md](deploy.md) |
| Execução real de `exemplos/consumidor.py` contra a API autenticada | ✅ **Feito contra desenvolvimento local** (ver seção acima, saída real do script). ⏳ Produção pendente. | Reexecutar apontando `UNI_API_BASE_URL` pra produção depois do deploy |
| Validação cruzada dos indicadores (SLA, TMA/TMR, TTFA, pontuação) contra o sistema de origem/relatórios existentes, nos 3 recortes exigidos pela norma (dia pequeno, dia grande, período de 7 dias) | ❌ Ainda não feito | Repetir o roteiro de `docs/roteiro-comparacao-tmr-opa-suite.md` (já existente no projeto, usado como modelo) para cada indicador do catálogo, com uma pessoa da área validando os números |
| Aprovação de negócio da classificação de dados pessoais/sensíveis (`acesso.md §4`) | ❌ Ainda não feito | Levar `acesso.md §4` para a área responsável (RH/DPO) |
| Confirmação da URL real de homologação/produção | ✅ Produção confirmada (`https://operacao.souuni.com`). Homologação: não existe ambiente separado identificado. | — |
| Bloqueio de escrita testado | ✅ **Feito em desenvolvimento local** — `PUT /operations/ixc-sync-settings` e `POST /calculation-runs/calculate` com a credencial do cubo devolveram `403` (ver seção acima). ⏳ Produção pendente. | Repetir contra produção depois do deploy, documentar aqui |

## Divergências encontradas entre documentação e código (achados reais, não hipotéticos)

- **`docs/api-gamificacao.md`**: exemplo de resposta de `GET /collaborators/{id}/point-balance` usa
  um campo `"kind"` que não existe no serializador real (`entry_type` é o nome correto), e omite
  campos reais como `requires_review`, `recurrence_classification`, `target_reference_month/year`.
  Exemplo desatualizado, não um erro de contrato.
- **`docs/plano-integracao-ixc.md`**: não trata do módulo Operação Analítica (`modules/operations`)
  como o nome sugere — é inteiramente sobre o pipeline de importação da Gamificação
  (`ServiceOrder`). Não usar este documento como referência de negócio da Operação Analítica.
- **`docs/normas-qualidade-dados-metricas.md`** (regra de importação: run "running" precisa ser
  commitada isoladamente antes do processamento longo, e status final precisa sobreviver a
  rollback): não foi possível confirmar, só pela leitura estática de
  `backend/app/modules/operations/ixc_ingestion.py`, que o fluxo síncrono de `/imports` segue essa
  regra à risca — `db.commit()` parece acontecer só no router, após toda a importação, o que
  poderia reverter o registro da run inteira em caso de falha de infraestrutura no meio do
  processo. **Não confirmado em runtime, só sinalizado como risco a validar** (ver
  `catalogo.json` para o texto completo do achado).
- **`ManagementCase` sem `UniqueConstraint` de banco** (`gap.management_case_race_condition`):
  confirmado por leitura literal de `backend/app/modules/management/cases.py` e
  `backend/app/modules/management/models.py:154-158` — a idempotência de criação de caso
  (diário/mensal) é garantida só em código Python (SELECT + checagem em memória, sem
  `SELECT...FOR UPDATE`), não por constraint. Risco teórico de duplicidade sob concorrência real,
  não testado em runtime.
- **Duas funções de filtro de período na Gamificação sem explicação da divergência**
  (`gap.period_orders_ambiguity`): `period_orders` (filtro estrito de mês/ano) e
  `period_orders_for_aggregation` (mais permissiva) em `scoring_detail.py` — nenhum comentário no
  código explica por que ambas existem. Um cubo que replique "contagem de O.S. do período" precisa
  escolher uma delas conscientemente, não presumir equivalência.

## Validação contra painel real de produção (2026-09-17)

O dono do sistema compartilhou um print real do "Painel do CEO — Operações" (ambiente de
produção) e a tabela de agrupamento por tecnologia usada nele
(`regras-agrupamento-sla-tecnologia.json`, cópia salva neste pacote). Cruzamento contra o código:

- **SLA de Ativação/Suporte por Fibra Urbana/Fibra Rural/Rádio** — confirmado que vem de
  `GET /api/operations/sla?group_by=subject`, com o rollup por tecnologia feito no lado do
  consumidor usando a tabela de regras. Detalhe completo em
  [cobertura.md](cobertura.md#achados-validados-contra-o-painel-executivo-real-2026-09-17).
  Isso fecha uma divergência que a primeira versão desta análise não tinha identificado (o
  primeiro instinto foi supor confusão com o módulo SGP Suporte — não é, é Operação Analítica).
- **CSAT Suporte Interno**: confirmado real (`SupportOpaAttendance.rating`, agregado em
  `/api/support/opa/overview`).
- **CSAT Suporte de Campo**: **gap real, ainda não resolvido** — nenhuma fonte encontrada em
  Operação Analítica. Pendência a esclarecer com quem mantém o painel.

## Diferença entre "documentação completa" e "acesso completo" (lembrete explícito)

Este pacote documenta 7 módulos de negócio com evidência de código. Isso **não** significa que
todos os dados estão liberados para o cubo hoje: `acesso.md` restringe a identidade técnica a uma
lista específica de permissões de leitura, e `cobertura.md` marca explicitamente que nenhum item
está "validado pela área de negócio" nesta análise. Documentação e acesso são entregues como
resultados separados, como pedido.
