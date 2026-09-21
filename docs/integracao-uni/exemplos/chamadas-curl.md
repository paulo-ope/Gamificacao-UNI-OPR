# Exemplos de chamada crua (curl)

Substitua `$UNI_API_BASE_URL` pela URL da API (ver [../.env.example](../.env.example)).
`$UNI_API_TOKEN` aqui **não é um segredo fixo** — é o `access_token` devolvido pelo login (passo
0 abaixo), que expira em `AUTH_TOKEN_EXPIRE_MINUTES` (720min/12h por padrão) e precisa ser obtido
de novo depois disso. Todos os exemplos deste arquivo já foram executados com sucesso contra
desenvolvimento local com a credencial real do cubo — ver [../validacao.md](../validacao.md) para
a evidência completa (401 sem token, 200 com token válido, 403 em escrita).

## 0. Login — obter o token (fazer isso primeiro, e de novo quando expirar)

```bash
UNI_API_TOKEN=$(curl -s -X POST "$UNI_API_BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$UNI_API_EMAIL\",\"password\":\"$UNI_API_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

## 1. Autenticação — cabeçalho esperado nas chamadas seguintes

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
