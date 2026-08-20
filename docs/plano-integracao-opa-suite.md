# Plano tecnico - Integracao OPA Suite

Status: plano de implementacao para substituir importacoes manuais por API OPA Suite em um modulo SGP/Suporte separado da Operacao Analitica.
Data: 2026-08-16.
Projeto alvo: Gamificacao UNI OPR.

## 1. Objetivo

Implementar a integracao com a API do OPA Suite de forma rapida, objetiva, padronizada e limpa, reaproveitando padroes tecnicos da integracao IXC sem acoplar a OPA ao modulo Operacao Analitica.

O resultado esperado e:

- parar de depender de planilhas para indicadores vindos do OPA;
- manter tokens e credenciais somente no backend/VM;
- salvar dados normalizados no PostgreSQL;
- expor dados para dashboards por rotas internas autenticadas;
- manter importacao manual/planilha apenas como contingencia durante a transicao.

## 2. Diagnostico do projeto atual

O projeto ja possui a base necessaria para essa integracao:

- backend FastAPI;
- SQLAlchemy + PostgreSQL;
- migrations Alembic;
- Docker/VM;
- autenticacao e permissoes no backend;
- `httpx` ja instalado;
- integracao IXC estruturada com client, ingestion, scheduler, logs e configuracao por `AppSetting`.

Arquivos de referencia:

- `backend/app/services/ixc_client.py`
- `backend/app/modules/operations/ixc_ingestion.py`
- `backend/app/services/ixc_scheduler.py`
- `backend/app/modules/operations/router.py`
- `frontend/components/workspace/ixc-sync-settings-card.tsx`
- `frontend/lib/operations-api.ts`
- `backend/app/core/config.py`
- `backend/app/main.py`

Decisao tecnica: a OPA deve seguir o mesmo padrao tecnico da IXC, mas em dominio proprio (`support`). Nao criar rotas, tabelas ou permissoes OPA dentro de `operations`, porque Operacao Analitica permanece dominio IXC.

## 3. Arquitetura alvo

Fluxo recomendado:

```text
OPA Suite
  -> backend FastAPI na VM
  -> opa_client.py
  -> modules/support/opa_ingestion.py
  -> PostgreSQL
  -> rotas internas /api
  -> dashboards Next.js
```

Tokens nunca devem sair do backend.

Nao chamar a API OPA diretamente pelo frontend, pois isso exporia `OPA_API_TOKEN` no navegador e dificultaria logs, retries e controle de carga.

## 4. Escopo rapido do MVP

O MVP deve ser pequeno e validavel:

1. Criar cliente HTTP OPA.
2. Buscar atendimentos por periodo.
3. Normalizar dados em estrutura propria.
4. Persistir dados brutos e/ou normalizados.
5. Criar importacao manual por periodo.
6. Expor status da ultima sincronizacao.
7. Criar testes do client e ingestion.

Nao incluir no primeiro corte:

- remover uploads existentes;
- recalcular todos os dashboards automaticamente;
- alterar regras de pontuacao;
- criar telas grandes novas;
- misturar OPA com IXC sem validacao de equivalencia semantica.

## 5. Endpoints OPA previstos

Validar no ambiente real da UNI antes de fechar o mapeamento. Pelas referencias publicas/collection OPA, os endpoints esperados sao:

| Finalidade | Endpoint previsto |
|---|---|
| Listar atendimentos | `GET /api/v1/atendimento` |
| Buscar atendimento detalhado | `GET /api/v1/atendimento/{id}` |
| Listar mensagens | `GET /api/v1/atendimento/mensagem` |
| Listar usuarios/atendentes | `GET /api/v1/usuario/` |
| Listar motivos | `GET /api/v1/atendimento/motivo` |
| Listar periodos | `GET /api/v1/atendimento/periodo` |
| Listar departamentos | `GET /api/v1/departamento/` |
| Listar clientes | `GET /api/v1/cliente/` |

Filtros previstos para atendimento:

- `dataInicialAbertura`
- `dataFinalAbertura`
- `dataInicialEncerramento`
- `dataFinalEncerramento`
- `id_atendente`
- `status`
- `canal_id`
- `setor`
- `id_cliente`
- `motivos.idMotivo`

Regra operacional: processar por janelas curtas, preferencialmente dia a dia ou semana a semana. Evitar consultas historicas grandes.

## 6. Variaveis de ambiente

Adicionar em `.env.example`, `docker-compose.yml` e `backend/app/core/config.py`:

```env
OPA_API_BASE_URL=
OPA_API_TOKEN=
OPA_API_VERIFY_SSL=true
OPA_SYNC_ENABLED=false
OPA_SYNC_INTERVAL_MINUTES=20
OPA_SYNC_LOOKBACK_DAYS=1
```

Regras:

- `OPA_API_TOKEN` nunca deve ser commitado.
- Logs nao devem imprimir token.
- Em producao, usar usuario API exclusivo no OPA com permissao minima necessaria.

## 7. Arquivos a criar

Backend:

```text
backend/app/services/opa_client.py
backend/app/modules/support/opa_ingestion.py
backend/app/modules/support/models.py
backend/app/modules/support/router.py
backend/app/modules/support/schemas.py
backend/app/services/opa_scheduler.py
backend/tests/test_opa_client.py
backend/tests/test_opa_ingestion.py
backend/tests/test_opa_scheduler.py
```

Se houver persistencia nova:

```text
backend/alembic/versions/YYYYMMDD_NNNN_opa_integration.py
```

Frontend, se houver tela no mesmo ciclo:

```text
frontend/components/support/opa-sync-settings-card.tsx
```

Arquivos a alterar:

```text
backend/app/core/config.py
backend/app/main.py
backend/app/modules/registry.py
frontend/lib/support-api.ts
.env.example
docker-compose.yml
```

## 8. Cliente HTTP OPA

Criar `backend/app/services/opa_client.py` com responsabilidades limitadas:

- montar URL base;
- autenticar com Bearer token;
- aplicar timeout;
- fazer paginação;
- aplicar filtros;
- normalizar erro de rede/autenticacao/formato;
- registrar logs de auditoria sem dados sensiveis.

Modelo sugerido:

```python
class OpaApiError(RuntimeError):
    pass

class OpaClient:
    def __init__(self, base_url: str, token: str, verify_ssl: bool = True, timeout: float = 30.0) -> None:
        ...

    def list_attendances(self, *, opened_after: str | None = None, opened_before: str | None = None, closed_after: str | None = None, closed_before: str | None = None, limit: int = 100, skip: int = 0) -> list[dict]:
        ...

    def iter_attendances(self, *, opened_after: str | None = None, opened_before: str | None = None, closed_after: str | None = None, closed_before: str | None = None) -> Iterator[dict]:
        ...

    def list_users(self) -> Iterator[dict]:
        ...

    def list_reasons(self) -> Iterator[dict]:
        ...
```

Seguir o estilo de `IxcClient`: client puro, sem regra de negocio.

## 9. Modelo normalizado

Modelo minimo para atendimento OPA:

```json
{
  "source": "opa",
  "source_id": "123",
  "protocol": "ABC123",
  "customer_id": "456",
  "customer_name": "Cliente Exemplo",
  "attendant_id": "789",
  "attendant_name": "Atendente Exemplo",
  "department_id": "10",
  "department_name": "Suporte",
  "reason_id": "20",
  "reason_name": "Sem conexao",
  "status": "finalizado",
  "opened_at": "2026-08-01T08:00:00-04:00",
  "closed_at": "2026-08-01T08:20:00-04:00",
  "first_response_at": "2026-08-01T08:03:00-04:00",
  "rating": 5,
  "tma_seconds": 1200,
  "tmr_seconds": 180,
  "raw_payload": {}
}
```

Campos criticos:

- `source_id`: usado para idempotencia;
- `opened_at` e `closed_at`: usados para periodo;
- `attendant_name`: usado em dashboards N1/N2;
- `reason_name`: usado em motivos/causas;
- `tma_seconds` e `tmr_seconds`: podem vir prontos ou precisar ser calculados;
- `raw_payload`: manter para auditoria e ajuste posterior de mapeamento.

## 10. Persistencia recomendada

Para o primeiro ciclo, usar tabelas proprias do modulo Suporte/SGP em vez de escrever direto em `service_orders` ou `operations_orders`.

Sugestao:

```text
support_opa_attendances_raw
- id
- source_id
- payload_json
- opened_at
- closed_at
- source_updated_at
- synced_at

support_opa_attendances
- id
- source_id
- protocol
- customer_id
- customer_name
- attendant_id
- attendant_name
- department_id
- department_name
- reason_id
- reason_name
- status
- opened_at
- closed_at
- first_response_at
- rating
- tma_seconds
- tmr_seconds
- raw_payload
- first_imported_at
- last_imported_at
```

Indices recomendados:

- `source_id` unico;
- `opened_at`;
- `closed_at`;
- `attendant_name`;
- `reason_name`;
- `status`.

Nao inserir em `operations_orders` neste modulo. Atendimentos OPA pertencem ao SGP/Suporte; se algum dado precisar alimentar outro modulo no futuro, criar contrato/projecao explicita.

## 11. Ingestion

Criar `backend/app/modules/support/opa_ingestion.py`.

Responsabilidades:

- receber periodo;
- adquirir lock consultivo Postgres para evitar importacoes concorrentes;
- buscar dados via `OpaClient`;
- normalizar registros;
- fazer upsert por `source_id`;
- registrar contadores: buscados, criados, atualizados, inalterados, rejeitados;
- registrar ate 50 erros resumidos;
- retornar resultado estruturado.

Seguir o desenho de `ixc_ingestion.import_current_month_period`, mas sem copiar logica IXC desnecessaria.

## 12. Scheduler

Criar `backend/app/services/opa_scheduler.py`.

Chaves em `AppSetting`:

```text
opa_sync_enabled
opa_sync_interval_minutes
opa_sync_lookback_days
opa_sync_last_success_at
opa_sync_last_attempt_at
opa_sync_next_allowed_at
opa_sync_last_error
opa_sync_last_error_at
opa_sync_consecutive_failures
```

Comportamento:

- loop roda somente se `OPA_API_BASE_URL` e `OPA_API_TOKEN` estiverem configurados;
- respeita `opa_sync_enabled`;
- relê intervalo do banco a cada ciclo;
- reimporta hoje e dias de lookback;
- em falha, grava erro resumido e nao derruba o backend;
- nao recalcula automaticamente pontuacao no primeiro MVP, a menos que o destino final ja esteja validado.

## 13. Rotas internas

Adicionar rotas sob `/api/support`.

```text
GET  /api/support/opa-sync-settings
PUT  /api/support/opa-sync-settings
POST /api/support/opa-imports
GET  /api/support/opa-sync-status
GET  /api/support/opa-metrics
```

Permissao sugerida:

```text
support:read
support:sync_opa
```

Nao reutilizar permissoes do modulo Operacao Analitica para a integracao OPA.

## 14. Frontend

Criar card simples seguindo o padrao visual do IXC:

- toggle "Sincronizacao OPA ativa";
- intervalo em minutos;
- lookback em dias;
- status da ultima tentativa;
- status do ultimo sucesso;
- ultimo erro, se houver;
- botao "Salvar";
- botao "Sincronizar agora" por periodo.

Base visual:

- `frontend/components/workspace/ixc-sync-settings-card.tsx`

Evitar:

- token no frontend;
- campo para exibir token;
- mensagens tecnicas cruas;
- componentes grandes demais.

## 15. Validacao em paralelo

Antes de tornar a OPA fonte oficial:

1. Rodar importacao OPA de um dia conhecido.
2. Comparar total de atendimentos com painel/relatorio OPA.
3. Validar 10 atendimentos manualmente: protocolo, atendente, cliente, motivo, status e horarios.
4. Rodar uma semana completa.
5. Comparar TMA, TMR, volume por atendente, motivos e avaliacoes.
6. Rodar um mes fechado em paralelo.
7. So depois conectar dashboards definitivos ou desativar obrigatoriedade de planilha.

## 16. Testes obrigatorios

Backend:

- `OpaClient` monta headers Bearer corretamente;
- pagina ate acabar registros;
- nao loga token;
- trata erro HTTP como `OpaApiError`;
- normalizador rejeita atendimento sem `source_id` ou data valida;
- ingestion e idempotente: mesmo registro nao duplica;
- update altera registro existente quando payload muda;
- scheduler grava falha sem derrubar loop.

Frontend, se houver tela:

- typecheck;
- renderizacao com settings nulos;
- validacao de intervalo;
- estado de saving;
- mensagem amigavel de erro.

## 17. Criterios de aceite

Implementacao pronta quando:

- `OPA_API_*` configurado no backend;
- import manual por periodo funciona;
- dados ficam persistidos com idempotencia;
- token nao aparece em resposta, log ou frontend;
- existe status de sincronizacao;
- existem testes relevantes;
- `.env.example` e `docker-compose.yml` atualizados;
- projeto passa nos testes/typecheck aplicaveis;
- documento foi atualizado com qualquer descoberta real da API OPA no ambiente da UNI.

## 18. Riscos e mitigacoes

| Risco | Mitigacao |
|---|---|
| Campo OPA diferente da documentacao | Fazer primeiro um endpoint de import manual e validar payload real |
| Duplicidade por reimportacao | Unique por `source_id` e upsert |
| Token exposto | Somente backend, nunca frontend |
| Carga excessiva na OPA | Janelas curtas, paginação, intervalo minimo e logs |
| Mistura indevida com IXC | Tabelas/normalizacao OPA separadas no MVP |
| Dashboard com numero errado | Validacao paralela antes do corte |
| Concorrencia entre sync manual e automatico | Lock consultivo Postgres |

## 19. Ordem de implementacao para Claude Code

Prompt sugerido:

```text
Implemente a integracao OPA Suite seguindo docs/plano-integracao-opa-suite.md.

Escopo do primeiro PR:
1. Criar OpaClient em backend/app/services/opa_client.py.
2. Adicionar settings OPA em backend/app/core/config.py, .env.example e docker-compose.yml.
3. Criar migration para opa_attendances_raw e opa_attendances.
4. Criar opa_ingestion.py com importacao manual por periodo e upsert idempotente.
5. Criar schemas e rotas protegidas para POST /api/support/opa-imports e GET/PUT /api/support/opa-sync-settings.
6. Criar testes unitarios do client e ingestion.

Regras:
- Nao chamar OPA pelo frontend.
- Nao expor token em logs ou respostas.
- Reaproveitar padroes tecnicos da integracao IXC sem acoplar OPA ao modulo Operacao.
- Manter mudanca pequena e revisavel.
- Nao remover importacao por planilha neste PR.
- Atualizar este documento se algum campo real da API OPA divergir do esperado.
```

## 20. Corte posterior

Depois do MVP:

1. Criar `opa_scheduler.py`.
2. Ligar loop em `backend/app/main.py`.
3. Criar card frontend de configuracao.
4. Criar comparativos por periodo contra planilha/relatorios atuais.
5. Conectar dashboards aos dados OPA normalizados.
6. Manter upload manual como contingencia ate um fechamento mensal validado.
