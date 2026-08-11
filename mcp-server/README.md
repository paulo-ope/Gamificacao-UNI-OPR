# opr_analitica_mcp

Servidor MCP local que expõe as ferramentas de IA da Operação Analítica (`/api/ai/*` do backend)
para o Claude Code e o Claude Desktop. Não reimplementa nenhuma lógica de análise — só chama a API
que já existe em produção, usando a mesma chave de API que já protege essas rotas.

Rodei este servidor de ponta a ponta (handshake MCP real via stdio, `list_tools`, `call_tool`)
contra o backend local antes de entregar — funcionou com dado real.

## 1. Gerar uma chave de API

O backend já tem um comando pronto pra isso (ver `backend/app/modules/ai/cli.py`):

```bash
docker exec opr-gamification-backend python -m app.modules.ai.cli create-service-user --name "Claude Code MCP"
```

Copie a chave impressa — ela não é mostrada de novo (só o hash fica salvo). Se perder, rode o
comando de novo com um nome diferente para gerar outra (a antiga continua válida até ser revogada
manualmente no banco).

## 2. Instalar as dependências

```bash
cd mcp-server
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\pip install -r requirements.txt
```

Linux/Mac:
```bash
.venv/bin/pip install -r requirements.txt
```

## 3. Configurar

Duas variáveis de ambiente:

- `OPR_API_BASE_URL` — base da API. Local: `http://localhost:8000/api`. Produção (se você quiser
  consultar dados de produção direto, sem estar com o backend local rodando):
  `https://sistema.souuni.com/api` (ajuste para o domínio real).
- `OPR_API_KEY` — a chave gerada no passo 1.

### Claude Code

```bash
claude mcp add opr-analitica \
  -e OPR_API_BASE_URL=http://localhost:8000/api \
  -e OPR_API_KEY=SUA_CHAVE_AQUI \
  -- /caminho/completo/para/mcp-server/.venv/Scripts/python.exe /caminho/completo/para/mcp-server/opr_analitica_mcp.py
```

(No Windows, use os caminhos completos com `\` ou `/`, ambos funcionam no `python.exe`.)

### Claude Desktop

Edite `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`) e
adicione:

```json
{
  "mcpServers": {
    "opr-analitica": {
      "command": "C:\\caminho\\completo\\para\\mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\caminho\\completo\\para\\mcp-server\\opr_analitica_mcp.py"],
      "env": {
        "OPR_API_BASE_URL": "http://localhost:8000/api",
        "OPR_API_KEY": "SUA_CHAVE_AQUI"
      }
    }
  }
}
```

Reinicie o Claude Desktop depois de salvar.

## Ferramentas disponíveis

| Tool | O que faz |
|---|---|
| `opr_aggregate_orders` | Agrupa O.S. por dimensão (regional, bairro, assunto, cluster geográfico, etapa de SLA...) e calcula uma métrica por grupo |
| `opr_orders_timeseries` | Série temporal (dia/semana/mês) de abertas/fechadas/saldo, opcionalmente quebrada por dimensão |
| `opr_search_orders` | Busca paginada de O.S. individuais, com texto (descrição de abertura, relato técnico) e todos os campos de SLA/tempo já calculados; suporta filtro geográfico por raio |
| `opr_backlog_aging` | Idade do backlog (O.S. em aberto) por dimensão |
| `opr_backlog_history` | Série histórica diária de backlog/backlog atrasado (regional/team_model/sector/city) |
| `opr_filter_options` | Lista valores realmente cadastrados no período, para montar filtros exatos com a grafia certa |
| `opr_warranty_analytics` | Análise de garantia de ativação (mesma conta da aba Garantias) |
| `opr_team_targets` | Metas de equipe vigentes numa data (histórico, não a configuração atual) |
| `opr_team_target_performance` | Produção realizada x meta prevista, por modelo de equipe |
| `opr_list_fields` | Lista campos da O.S. e quais já estão expostos à IA — útil pra descobrir se um filtro que você quer já existe |

## Sobre o parâmetro `filters`

Os filtros de O.S. (regional, cidade, bairro, assunto, responsável, indicadores de etapa de SLA,
filtro geográfico de raio, texto livre) são passados como um dicionário livre (`filters: {...}`),
documentado no docstring de cada tool — não como um campo Pydantic por filtro. Isso foi uma escolha
deliberada: o backend já valida tudo (`extra="forbid"`, rejeita chave desconhecida) e o schema de
filtros tem ~25 campos que mudam com frequência (veja o histórico deste projeto: bairro,
coordenadas e indicadores de SLA foram todos adicionados nas últimas semanas). Replicar cada campo
aqui como Pydantic estrito criaria manutenção duplicada — sempre que o backend ganhar um filtro
novo, esse arquivo ficaria defasado até alguém lembrar de atualizá-lo. Se um filtro parecer não
fazer efeito, chame `opr_list_fields` para conferir contra o backend "ao vivo", ou leia
`backend/app/modules/ai/schemas.py:AiOrderFilters` diretamente.

## Segurança

- A chave de API dá acesso de LEITURA a dados analíticos de O.S. (nenhuma tool aqui escreve nada -
  todas são só leitura, `readOnlyHint: true`). Ainda assim, trate a chave como segredo: não
  comite `OPR_API_KEY` em nenhum arquivo versionado.
- `.venv/` está no `.gitignore` deste diretório - não deve ser commitado.
