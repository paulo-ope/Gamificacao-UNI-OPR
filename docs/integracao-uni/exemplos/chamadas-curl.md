# Exemplos de chamada crua (curl)

Substitua `$UNI_API_BASE_URL` e `$UNI_API_TOKEN` pelas variáveis do seu `.env` local
(ver [../.env.example](../.env.example)). Nenhum comando abaixo foi executado com uma
credencial real nesta análise — foram validados apenas a forma da URL/parâmetros contra
`openapi.yaml` e o retorno 401 esperado sem token (ver [../validacao.md](../validacao.md)).

## Autenticação — cabeçalho esperado

```bash
curl -s "$UNI_API_BASE_URL/operations/overview?date_from=2026-09-01&date_to=2026-09-16" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Sem token (deve retornar 401)

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$UNI_API_BASE_URL/operations/overview"
# 401
```

## Consulta filtrada — SGP Suporte, atendimentos OPA por período e status

```bash
curl -s "$UNI_API_BASE_URL/support/opa/attendances?date_from=2026-09-01&date_to=2026-09-16&status=closed&page=1&page_size=100" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Paginação — próxima página

```bash
curl -s "$UNI_API_BASE_URL/support/opa/attendances?date_from=2026-09-01&date_to=2026-09-16&page=2&page_size=100" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Consulta de indicador — SLA da Operação Analítica por regional

```bash
curl -s "$UNI_API_BASE_URL/operations/sla?date_from=2026-09-01&date_to=2026-09-16" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Consulta de indicador — TMA/TMR do SGP Suporte

```bash
curl -s "$UNI_API_BASE_URL/support/opa-metrics?date_from=2026-09-01&date_to=2026-09-16" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Detalhe de um registro individual (cuidado com campos sensíveis — ver acesso.md)

```bash
curl -s "$UNI_API_BASE_URL/operations/orders/12345" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
```

## Erro esperado — parâmetro obrigatório ausente (422)

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$UNI_API_BASE_URL/support/opa/overview" \
  -H "Authorization: Bearer $UNI_API_TOKEN"
# 422 esperado (date_from/date_to são obrigatórios nesta rota, conforme router.py:1076) —
# não verificado nesta análise com credencial real; com token INVÁLIDO ou ausente, espere 401
# antes mesmo da validação de parâmetros (a dependency de autenticação roda primeiro).
```
