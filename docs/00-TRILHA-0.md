# Trilha 0 — Baseline do Ecossistema UNI Workspace

Este documento é o ponto de partida fixo do projeto. Ele muda raramente — só quando a
estrutura organizacional real muda (novo módulo, nova stack, nova convenção de branch).
Detalhes de features específicas ficam nos demais documentos de `docs/`, nunca aqui.

## O que é este repositório

Ecossistema modular da operação da UNI. Uma única aplicação (mesma autenticação,
mesmo banco, mesma infra) hospeda vários módulos de negócio independentes entre si
em regra de negócio, mas compartilhados em plataforma.

Stack: Next.js/TypeScript/Tailwind no frontend, FastAPI/SQLAlchemy/Pydantic no
backend, PostgreSQL como banco, Docker Compose como infra. Detalhes de setup estão
no [README.md](../README.md).

## Estrutura organizacional (módulos)

Cada módulo tem rota web própria, prefixo de API próprio e permissão própria. Fonte
de verdade: [frontend/lib/module-registry.ts](../frontend/lib/module-registry.ts) e
[backend/app/modules/registry.py](../backend/app/modules/registry.py).

| Módulo | Rota web | Prefixo API | O que faz |
|---|---|---|---|
| Gamificação Operacional | `/gamificacao` | `/api` | Remuneração variável, fechamento e auditoria de produtividade a partir das O.S. |
| Operação Analítica | `/operacao` | `/api/operations` | Importa O.S. do IXC, projeta em `operations_*`, calcula SLA/backlog/garantia/produtividade |
| Agendamento | `/agendamento` | `/api/scheduling` | Tempo de resposta, produtividade e fila do setor de agendamento |
| SGP Suporte | `/suporte` | `/api/support` | Atendimentos, TMA/TMR e motivos vindos do OPA Suite |
| Gestão Integrada | `/gestao` | `/api/management` | Estrutura operacional, casos de gestão, justificativas e decisão da matriz |
| Administração | `/admin` | `/api/admin` | Usuários, perfis de acesso, permissões e escopos do ecossistema |
| UNI Intelligence | `/intelligence` | `/api/intelligence` | Cockpit operacional, alertas, monitores e publicações (TVs/gauges) |

Cada módulo backend vive isolado em `backend/app/modules/<modulo>/` (router, models,
schemas, services próprios). Regra de negócio pesada fica em `services/`, nunca na
rota nem na tela — ver [AGENTS.md](../AGENTS.md).

## Integrações externas por módulo

- **Operação Analítica**: API do IXC (O.S., cadastros auxiliares) — ver
  `docs/plano-integracao-ixc.md`.
- **SGP Suporte**: API do OPA Suite (atendimentos, mensagens, dimensões de
  usuário/departamento/motivo/etiqueta/cliente) — ver
  `docs/plano-integracao-opa-suite.md` e `docs/auditoria-evolucao-opa-suite-2026-08-16.md`.
- **Gestão Integrada / UNI Intelligence**: consomem as projeções dos módulos acima,
  não têm fonte externa própria.

## Convenções de trabalho

- Regras obrigatórias de código, segurança e arquitetura: [AGENTS.md](../AGENTS.md).
  Leia antes de qualquer alteração — inclui a exigência de apresentar diagnóstico e
  plano antes de escrever código em tarefa nova.
- Contrato operacional obrigatório de engenharia: [manual_desenvolvimento_senior.md](manual_desenvolvimento_senior.md).
  Leia antes de desenvolver ou modernizar funcionalidades. Ele usa linguagem
  normativa e define critérios verificáveis para layout moderno, backend estável e
  rápido, código organizado, segurança, banco, testes e produção.
- **Norma permanente de métricas, filtros, importações e dashboards:
  [normas-qualidade-dados-metricas.md](normas-qualidade-dados-metricas.md).**
  Obrigatória em qualquer tarefa que crie ou altere KPI, filtro de período,
  rotina de importação ou tela de dashboard, em qualquer módulo.
- Checklist de revisão: `docs/code_review.md`.
- Manual de backend/infra: `docs/manual_programacao_senior.md`.
- Manual de frontend: `docs/manual_frontend_senior.md`.
- Estado atual do trabalho, decisões recentes e próximos passos: **sempre em
  [docs/STATUS.md](STATUS.md)**, nunca neste arquivo.

## Branches

- `main`: branch estável, é o que roda em produção/homolog.
- `claude/*`: branches de trabalho geradas por sessões do Claude Code.
- `feature/*`, `fix/*`: branches de trabalho manuais.

Este arquivo e `docs/STATUS.md` devem existir em todas as branches ativas. Como git
não sincroniza arquivos entre branches sozinho, ao abrir uma branch nova ou retomar
uma antiga, funda/rebase com `main` para trazer a versão mais recente destes dois
arquivos antes de continuar o trabalho.

## Índice comentado dos demais documentos (`docs/`)

- `manual_desenvolvimento_senior.md` — padrão oficial e contrato operacional de
  engenharia: reúne regras verificáveis de layout moderno, backend estável e rápido,
  código limpo, arquitetura, banco, segurança, testes, observabilidade e deploy.
- `normas-qualidade-dados-metricas.md` — **norma permanente** de qualidade de dados e
  métricas: fonte única de regra (KPI vive no service, frontend só formata), contrato
  de filtros (fuso `America/Porto_Velho`, datas inclusivas, `opened_at` vs
  `closed_at`), tempos sempre em segundos, política de histórico/backfill, exigências
  de importação (run rastreável, lock com mensagem clara), validação cruzada contra o
  sistema de origem, testes obrigatórios para métrica nova, checklist de conclusão e
  regra visual permanente para dashboards. Vale para todos os módulos.
- `arquitetura_modular_ecossistema.md` — como os módulos se isolam e se conectam.
- `contratos_modulos.md` — contratos de API entre módulos.
- `controle_acesso_filtros_ecossistema.md` — modelo de permissões e escopos.
- `mapa_funcional_operacao_analitica.md` — mapa funcional completo da Operação Analítica.
- `prd_modulo_operacao_analitica.md` — PRD original do módulo de Operação Analítica.
- `plano-integracao-ixc.md` / `plano-integracao-opa-suite.md` — planos de integração externa.
- `plano-analise-opa-suite-atendimentos.md` — plano de evolução do módulo SGP em análise completa de atendimentos (visão geral, individual, histórico/timeline, metas, IA).
- `plano-ux-visual-sgp-suporte-fase-4a.md` — planejamento da fase visual/UX do SGP Suporte após as fases estruturais da OPA Suite.
- `portal-ciclo-vida-conta-colaborador.md` — planejamento da Fase 2 do Portal do
  Colaborador (ciclo de vida da conta após o primeiro acesso da Fase 1): troca de
  senha pelo próprio usuário, reset administrativo, convite com token, solicitação de
  acesso e recuperação de senha, com modelo de dados sugerido e ordem recomendada de
  implementação.
- `roteiro-comparacao-tmr-opa-suite.md` — roteiro pra comparar TMR do sistema local
  contra o painel oficial do OPA Suite (qual métrica local corresponde ao TMR deles),
  com tabela-modelo e critérios de classificação de divergência.
- `proposta-filter-contract-v1.md` — contrato de filtros compartilhado entre telas.
- `plano-plataforma-inteligencia-operacional.md` — plano do UNI Intelligence.
- `estudo-kpis-agendamento.md` — KPIs do módulo de Agendamento.
- `spec-saldo-pontos-garantia-pos-pagamento.md` — regra de saldo/garantia da Gamificação.
- `audit-findings-2026-07-24.md` / `auditoria-evolucao-opa-suite-2026-08-16.md` — auditorias pontuais, valor histórico.
- `manual_programacao_senior.md` / `manual_frontend_senior.md` / `code_review.md` — manuais de padrão de código.

Documentos de estudo/proposta antigos permanecem como histórico de decisão, não como
verdade atual — se um deles conflitar com o código, o código vence.
