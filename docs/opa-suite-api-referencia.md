# OPA Suite — referência da API (extraída em 2026-10-08)

Resumo próprio, para consulta interna, do que a documentação oficial do OPA diz **e do que foi
confirmado ao vivo** na API da UNI. Onde a documentação e a prática divergem, **vale a prática** (e
isso está marcado). Complementa `docs/plano-integracao-opa-suite.md` e
`docs/auditoria-evolucao-opa-suite-2026-08-16.md`; o consumo no código está em
`backend/app/services/opa_client.py`.

Fontes:
- [API Opa! Suite — central de ajuda IXC](https://central-opasuite.ixcsoft.com.br/documentacao/api/api-opa!-suite.html)
  (única página de documentação que foi possível extrair por inteiro).
- [api.opasuite.com.br](https://api.opasuite.com.br/) — a referência de campos; é uma página carregada
  por JavaScript e **não pôde ser extraída**. Os campos abaixo vêm de sondagens reais.
- Sondagens somente-leitura na API da UNI (2026-10-08), sem registrar dado pessoal.

## 1. Acesso

- Base: `https://<instalação>/api/v1`. Cabeçalhos: `Authorization: Bearer <token>` e
  `Content-Type: application/json`.
- O token pertence a um **usuário com "acesso à API"** vinculado a um **grupo de permissões do tipo API**.
  Gerar um token novo invalida o anterior na hora.
- A chamada é recusada se: token antigo, usuário inativo, **IP fora das "Redes permitidas" do grupo**, ou
  grupo sem a permissão do recurso/operação.
- Toda chamada fica registrada (usuário, IP, caminho, método, parâmetros, código).
- Boa prática oficial: um usuário e um grupo de API por integração, só com as permissões usadas.

## 2. Formato das requisições

- **Listagem** = `GET` **com corpo JSON** (sem `:id`): `{"filter": {...}, "options": {"limit": N, "skip": M}}`.
- `filter` exige **pelo menos um filtro válido** do recurso. Campo não filtrável → `400 Field '<campo>' is not allowed`.
  (**Mudança observada em 2026-10-08**: antes aceitava `{}`; a sincronização de dimensões quebrou em silêncio —
  ver `OpaClient.list_collection_union`.)
- `options.limit`: 1 a 1000 (fora disso, devolve até 1000). Hoje o cliente usa 100 por página.
- `options.skip`: paginação. **Atenção:** em `/usuario` filtrado o OPA **ignora `skip`/`limit` e devolve tudo**
  a cada página — por isso `list_collection` para quando a página não traz `_id` novo.
- Resposta: `{status, code, data}`. Erro: `data.message` + `description`.
- Códigos: 400 argumento inválido/ausente · 401 token inválido · 403 sem permissão/rede não permitida ·
  404 não encontrado · 409 já existe · 500 erro no servidor.
- Não há, na documentação consultada, limite de taxa (rate limit) nem webhooks/eventos.

## 3. Recursos (caminho após `/api/v1`)

| Recurso | Caminho | Operações | Permissão do grupo de API |
|---|---|---|---|
| Atendimentos | `/atendimento` | GET lista · GET `/:id` | Atendimentos |
| Períodos (expediente) | `/atendimento/periodo` | GET · GET `/:id` | Períodos de atendimento |
| Mensagens | `/atendimento/mensagem` | GET · GET `/:id` · POST `/send` | Enviar mensagens |
| Etiqueta do atendimento | `/atendimento/:id/etiqueta` | POST · DELETE `/:id` | Etiqueta |
| Observação | `/atendimento/:id/observacao` | POST | Observação |
| Motivo do atendimento | `/atendimento/:id/motivo` | POST | Motivo |
| Transferir para fluxo | `/atendimento/:id/transfer/flow` | POST | (sem permissão própria) |
| Participantes | `/atendimento/:id/participant` | POST · DELETE `/:userId` | (sem permissão própria) |
| Modelos de mensagem | `/template` | GET · GET `/:id` · POST `/send` | Modelos / Enviar templates |
| Canais | `/canal-comunicacao`, `/canal-comunicacao/:id/template` | GET | Canais de comunicação |
| Clientes e fornecedores | `/cliente` | GET · GET `/:id` · POST · PUT · PATCH · DELETE | Clientes e fornecedores |
| Contatos | `/contato` | GET · GET `/:id` · POST · PUT · DELETE | Todos os contatos |
| Departamentos | `/departamento` | GET · GET `/:id` · POST · PUT | Departamentos |
| Usuários | `/usuario` | GET · GET `/:id` | Usuários |
| Etiquetas | `/etiqueta` | GET · POST | Etiquetas |
| Motivos | `/motivo` | GET · GET `/:id` | Motivos de atendimento |
| Feriados | `/feriado` | GET · GET `/:id` | Feriados |
| Página do cliente | `/dashboard/open-dashboard-cliente` | POST | Página do cliente |
| Notificações | `/notificacao/send` | POST | Enviar notificações |
| Looker Studio | `/connector/looker-studio` | GET `/schema` · POST `/data` | Acesso ao Looker Studio |

Enviar mensagem: `POST /atendimento/mensagem/send` com `customerServiceId` e `content` (`type` `text`
ou `media`; `text`, ou `media.url`/`media.base64`).

## 4. O que foi confirmado ao vivo (UNI, 2026-10-08)

**Usuário (`/usuario`)** — 277 registros (266 `tipo=user`, 11 `tipo=bot`). Campos: `_id`, `nome`, `email`,
`tipo`, `status`, `online`, `ultimo_status`, `conexoes[]`, `ramal_pabx`, `departamento`, `inatividade`,
`createdAt`, `updatedAt`, entre outros.
- `status` = **só ativo/inativo** do cadastro (`A`/`I`). **Não é presença.**
- `online` = **presença**: `on` online · `off` offline · `pause` em pausa · `au` ausente · `oc` ocupado ·
  `call` em ligação.
- **Não existe** campo de "ligação tocando", nem do instante em que o status mudou. `updatedAt` acompanha a
  troca de presença e serve de **aproximação** do tempo no status (pode andar por outras alterações).
- Filtros aceitos: `tipo` (o valor é ignorado), `status`, `nome`. `ativo` não é aceito.

**Atendimento (`/atendimento`)** — filtro `status` **respeitado**; status vistos: `AG` aguardando, `EA` em
atendimento, `PS` pausado, `F` finalizado. Campos: `_id`, `protocolo`, `date` (abertura), `status`,
`setor` (id do departamento, texto), `id_atendente`, `id_cliente`, `id_user`, `canal`, `motivos[]`,
`tags[]`, `evaluations[]`, `descricao`, `observacoes`. Responde em ~100–150 ms para 1000 registros.
- **Dado sujo:** dos `AG` na API, a grande maioria é do departamento "Agentes Virtuais" (conversas de bot
  paradas) e há `EA` abertos há meses. Qualquer indicador "ao vivo" precisa **recortar por departamento** e
  **limitar por idade**.

**Departamento (`/departamento`)** — filtros aceitos: `nome` (**exato**) e `recebeAtendimento` (booleano).
**Etiqueta (`/etiqueta`)** — só `nome` (exato): **não há como listar todas**.
**Cliente (`/cliente`)** — `nome`, `status` (`A`/`I`), `fantasia`, `cpf_cnpj`, `_id`.
**Motivo** — `/atendimento/motivo` virou rota de atendimento (`Invalid ID`); a rota nova `/motivo` responde
`403 Invalid permissions profile` até o perfil de API do token receber a permissão.

## 5. Lacunas (não documentado / não extraído)

- Webhooks e eventos: não aparecem na documentação consultada (a central tem uma página de Webhooks que não
  foi possível abrir).
- Campos de `/connector/looker-studio/schema` e do dashboard do cliente.
- Limite de taxa (rate limit).
- Estado de ligação tocando.
