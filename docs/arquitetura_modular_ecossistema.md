# Arquitetura modular do UNI Workspace

## Decisão

O produto evoluirá como **monólito modular**: uma implantação de backend, frontend e PostgreSQL, organizada em domínios independentes. Um container não é a fronteira de um módulo; responsabilidades, dados, APIs e permissões são.

Essa decisão reaproveita autenticação, banco, Docker e observabilidade, evitando a complexidade prematura de serviços distribuídos. Um módulo pode ser extraído no futuro se houver necessidade concreta de escala, equipe ou implantação independentes.

## Estrutura-alvo

```text
backend/app/
  modules/
    registry.py
    shared/
    operations/
      api/ domain/ repositories/ schemas/ services/ tests/
  api/routes/                 # legado da Gamificação durante a transição

frontend/
  app/gamificacao/
  app/operacao/
  components/gamification/
  components/operations/
  lib/module-registry.ts
```

Nenhum código existente precisa ser movido para iniciar um módulo novo. Migrações de legado devem ocorrer separadamente, com testes de regressão.

## Registro de módulos

Cada módulo deve declarar identificador estável, nome, rota web, prefixo de API, permissões requeridas, status e descrição. Os estados são:

- `active`: disponível para usuários autorizados.
- `planned`: registrado e documentado, sem rota ou funcionalidade exposta.
- `disabled`: existente, mas desabilitado operacionalmente.

O backend é a fonte de autorização; o frontend usa o registro apenas para navegação e descoberta visual.

## Fronteiras de dados

- Cada módulo é dono de suas tabelas e migrations. Tabelas usam prefixo do domínio, como `operations_orders` e `operations_daily_snapshots`.
- Um módulo não lê nem escreve tabelas privadas de outro diretamente.
- Dados compartilhados usam contratos de API/projeção versionados e IDs estáveis.
- A Gamificação mantém `service_orders` enquanto a Operação constrói sua base canônica. Uma migração de consumo somente ocorre depois da validação dos números.
- Logs de auditoria e identidade podem ser compartilhados como capacidades de plataforma, desde que a autorização continue no backend.

## Contrato e versionamento

- Rotas públicas entre módulos usam prefixo de domínio e versão quando houver quebra: `/api/operations/v1/...`.
- Novos campos compatíveis podem ser adicionados; remoções ou mudanças semânticas exigem nova versão.
- Eventos e projeções devem incluir `source`, `source_id`, `occurred_at`, `calculated_at` e versão de regra quando aplicável.

## Segurança

- Permissões seguem o padrão `modulo:acao`, como `operations:read` e `operations:manage`.
- Empresa e regional são escopo de acesso no servidor, nunca somente filtros de interface.
- Credenciais de integrações ficam no backend e em `.env`; não são incluídas em respostas, logs ou frontend.
- A extração futura de um módulo exige token com emissor, audiência e rotação de chave; o token atual pode ser usado apenas enquanto o monólito permanecer único.

## Operação e extração futura

No MVP de Operação Analítica não existe worker automático: a consulta ao IXC é disparada pelo usuário e limitada ao intervalo selecionado do mês atual. Se a sincronização automática for habilitada no futuro, tarefas agendadas deverão ter liderança única ou ser movidas para worker dedicado quando houver múltiplas réplicas do backend.

Para extrair Operação no futuro: mover o pacote, criar banco próprio, manter o contrato de leitura/projeção, publicar eventos com outbox e consumir com idempotência. Nenhum consumidor deve depender de joins no banco do módulo extraído.
