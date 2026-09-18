# Handoff — Equipe de Infraestrutura

Contexto: pacote de integração de leitura para o Cubo de Dados Corporativo / Portal Executivo,
em [docs/integracao-uni/](.). Documentação e contrato técnico já estão prontos; **cinco decisões
de infraestrutura bloqueiam a próxima etapa** (provisionamento da credencial e teste ponta a
ponta). Nenhuma delas foi decidida ou executada nesta análise.

## Decisões pedidas

### 1. Onde a credencial técnica do cubo vai ser armazenada?

Hoje o projeto **não tem secrets manager configurado** — só `.env`/Docker Compose
(`backend/app/core/config.py`, `.env.example`). A regra do próprio projeto
(`docs/manual_programacao_senior.md`) exige "secrets apenas em `.env` ou secret manager", mas
nenhum dos dois está pronto para uma credencial de terceiro. Precisamos de uma decisão: Vault, AWS
Secrets Manager, Azure Key Vault, ou outro já usado em produção pela UNI — antes de qualquer token
real ser gerado. Detalhe técnico completo: [acesso.md §5](acesso.md).

### 2. URLs reais de homologação e produção

`openapi.yaml` tem `servers:` com placeholders (`<HOST_HOMOLOGACAO>`, `<HOST_PRODUCAO>`) — não
encontrei essa informação no código-fonte. Precisamos das URLs reais para o time do cubo apontar o
cliente corretamente.

### 3. `APP_ENV` de cada ambiente

`backend/app/main.py:209-217` só desliga `/docs`/`/redoc`/`/openapi.json` quando
`APP_ENV=="production"` (comparação exata). Se algum ambiente de homologação acessível
publicamente estiver com `APP_ENV` diferente disso (ex.: vazio, `staging`, `development`), a
superfície completa da API (incluindo rotas de escrita) fica com contrato exposto sem login.
Pedido: confirmar o valor de `APP_ENV` em cada ambiente hoje.

### 4. CORS libera `localhost:3000` mesmo fora de desenvolvimento

`backend/app/main.py:219-225` inclui `http://localhost:3000` e `http://127.0.0.1:3000` na lista de
origens aceitas, sem condicional por ambiente. Não é um wildcard (`allow_origins` é uma lista
fechada), mas vale confirmar se isso é intencional em produção.

### 5. Janela de renovação/revogação da credencial

O padrão já existente no código (`AiApiToken`: `expires_at`, `revoked_at`, chave em hash) serve de
modelo técnico, mas a **política** (prazo de expiração, processo de renovação, quem aprova
revogação) não está definida em nenhum documento do projeto. Pedido: definir isso junto com a
decisão do item 1.

## O que NÃO precisamos de vocês agora

- Não pedimos aprovação de dado de negócio/PII (isso vai para RH/DPO separadamente).
- Não pedimos para vocês criarem a credencial ainda — só decidir onde ela vai morar (item 1) e
  confirmar os itens 2-4, que são fatos sobre o ambiente que só vocês têm.

## Depois que estas 5 decisões existirem

O procedimento de criação da credencial (perfil de acesso dedicado, usuário de serviço, token com
hash, nunca papel `admin`) já está escrito passo a passo em [acesso.md §5](acesso.md) — pode ser
executado por quem tiver acesso ao ambiente indicado, seguindo esse roteiro.
