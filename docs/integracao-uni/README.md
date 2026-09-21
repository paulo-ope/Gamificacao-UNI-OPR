# Integração UNI — Cubo de Dados Corporativo / Portal Executivo

Pacote de integração **somente-leitura** para outro time (Cubo de Dados Corporativo / Portal
Executivo) consultar os dados de negócio do UNI Workspace com segurança, entendendo significado,
origem, regras e relacionamentos.

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data da análise original: 2026-09-17
· **Atualizado em 2026-09-21** com o mecanismo de acesso implementado, testado e mesclado em
`master` (Swagger de integração dedicado, cobrindo os 9 módulos) — ver [deploy.md](deploy.md) para
o status exato do deploy em produção. Autor: análise/implementação assistida por Claude Code,
leitura direta do código-fonte (não documentação genérica) — ver [validacao.md](validacao.md) para
o que foi de fato executado/verificado.

## O que este pacote é (e não é)

- **É**: mapeamento factual do que existe no código hoje, com evidência `arquivo:linha`, mais um
  contrato técnico (`openapi.yaml`) extraído do schema real do FastAPI em execução — não escrito à
  mão.
- **Não é**: um portal novo, uma réplica do banco, uma reescrita do sistema, nem uma declaração de
  que a integração já está pronta para produção. Ver [validacao.md](validacao.md) para as
  pendências reais.
- **Não criou** nenhuma credencial, endpoint novo ou alteração de código — só documentação e um
  script de exemplo somente-leitura. Ver [acesso.md](acesso.md) para o procedimento pendente.

## Ambientes

| Ambiente | URL da API | Status |
|---|---|---|
| Desenvolvimento local | `http://localhost:8000/api` (via `docker-compose.yml`, backend na porta 8000) | Confirmado — é de onde `openapi.yaml` foi extraído (schema real e filtrado, não escrito à mão) |
| Homologação | não existe um ambiente de homologação separado identificado | N/A |
| **Produção** | **`https://operacao.souuni.com/api`** | Confirmada pelo dono do sistema, acesso real via SSH. Doc de integração publicada em `https://operacao.souuni.com/api/admin/docs/integracao-uni` (Scalar) — **pendente o deploy físico do último código mesclado**, ver [deploy.md](deploy.md) para o status exato no momento em que você lê isto. Diferente do `/docs` padrão do FastAPI (esse sim desligado em produção): esta rota fica **sempre ligada**, mas exige autenticação (login ou token) em toda chamada. |

## Responsáveis conhecidos

Não identificados nesta análise (não há um `CODEOWNERS` nem uma seção de responsáveis por módulo
nos documentos lidos). Preencher com a liderança do UNI Workspace antes de publicar este pacote
para o outro time.

## Primeiros passos para o time consumidor

1. Ler [catalogo.md](catalogo.md) para entender os datasets e indicadores disponíveis, com suas
   ressalvas (nulos, histórico, granularidade de regional).
2. Ler [cobertura.md](cobertura.md) para saber o que já está testado/validado e o que não está —
   **documentação completa não é o mesmo que acesso completo ou validação de negócio**.
3. Ler [acesso.md](acesso.md) para entender autenticação, permissões da identidade técnica e o
   procedimento (ainda pendente) de provisionamento da credencial real.
4. Importar [openapi.yaml](openapi.yaml) num cliente HTTP (Postman/Insomnia) ou gerador de SDK,
   usando só as operações **GET**.
5. Rodar [exemplos/consumidor.py](exemplos/consumidor.py) (requer `UNI_API_TOKEN` — ainda não
   provisionado, ver `acesso.md`) ou os exemplos crus em
   [exemplos/chamadas-curl.md](exemplos/chamadas-curl.md).
6. Antes de publicar qualquer número derivado, conferir contra `validacao.md` se aquele indicador
   já foi validado pela área — a maioria ainda não foi.

## Estrutura do pacote

| Arquivo | Conteúdo |
|---|---|
| [openapi.yaml](openapi.yaml) | Contrato HTTP **já filtrado para leitura corporativa** (182 operações GET, os 9 módulos de negócio, zero escrita) — extraído direto de `GET /api/admin/docs/integracao-uni/openapi.json`, o mesmo schema que o Swagger publicado serve, não um dump bruto da API inteira |
| [catalogo.json](catalogo.json) | Catálogo estruturado (datasets, métricas, relacionamentos, lacunas) — consumível por máquina |
| [catalogo.md](catalogo.md) | Mesmo catálogo, versão legível — gerado programaticamente a partir do `.json` para garantir consistência |
| [cobertura.md](cobertura.md) | Matriz módulo → dataset → interface → documentação → testes → pendências |
| [acesso.md](acesso.md) | Autenticação, permissões da identidade técnica, classificação de dados pessoais, provisionamento (feito e testado, ver seção 5) |
| [deploy.md](deploy.md) | O que foi publicado, versão, comandos de deploy usados, verificação pós-deploy |
| [exemplos/consumidor.py](exemplos/consumidor.py) | Script Python executável (login com renovação automática, filtro, paginação, indicador, erro) — **rodado de verdade contra o ambiente local, evidência em validacao.md** |
| [exemplos/chamadas-curl.md](exemplos/chamadas-curl.md) | Chamadas HTTP cruas de exemplo |
| [.env.example](.env.example) | Variáveis necessárias ao consumidor de exemplo, sem segredos |
| [validacao.md](validacao.md) | O que foi de fato testado, divergências encontradas, pendências |

## Não há endpoint genérico de SQL nem exposição indiscriminada de tabelas

Cada operação de `openapi.yaml` reflete uma consulta de negócio que já existe nas telas do
sistema, com seus próprios filtros/paginação/regras — não uma tabela crua. Onde havia lacuna real,
este pacote **propõe** adaptações mínimas reaproveitando serviços existentes (ver
[cobertura.md](cobertura.md) → gaps), não implementa nada sem aprovação.

## Como atualizar este pacote quando a API mudar

1. Subir o backend local (`docker compose up -d db backend`).
2. Autenticar como alguém com `admin:integrations:read` (ou usar a própria conta do cubo) e buscar
   `GET /api/admin/docs/integracao-uni/openapi.json` — **já é o schema filtrado e enriquecido**
   (GET-only, 9 módulos, permissão por operação, descrição por módulo); não precisa mais filtrar
   nada por fora, só converter JSON → YAML e acrescentar `servers:` por cima.
3. Revisar `catalogo.json`/`catalogo.md` campo a campo contra os módulos que mudaram desde o
   commit acima (ver `docs/STATUS.md` do repositório principal).
4. Regenerar `catalogo.md` a partir do `catalogo.json` atualizado (não editar os dois em paralelo).
5. Rerodar `exemplos/consumidor.py` contra produção e atualizar `validacao.md`.

## Resumo objetivo (atualizado 2026-09-21)

- **Já pode ser integrado**: leitura do contrato (`openapi.yaml`, já filtrado GET-only) e do
  catálogo (`catalogo.md`/`.json`) — o time consumidor já pode desenhar o modelo do cubo em cima
  disso. **Chamadas HTTP reais já foram executadas com sucesso** contra o ambiente local com a
  credencial de leitura de verdade (login + consulta filtrada + paginação de 39.183 registros +
  bloqueio de escrita confirmado com 403) — ver [validacao.md](validacao.md) para a evidência
  completa. Contra **produção**, pendente o deploy (ver [deploy.md](deploy.md)).
- **Cobertura de módulo**: os 9 módulos de negócio, sem exceção (decisão do dono do sistema) — não
  há mais a limitação de escopo do conector MCP que a análise de 2026-09-17 registrava como gap.
  Continuam de fora, por design: campos sensíveis como `raw_payload` (só no detalhe, nunca em
  lote); telefone/e-mail de colaborador (nenhuma rota expõe hoje); qualquer operação de escrita
  (garantido na estrutura do schema, não só pela permissão da conta).
- **O que não pôde ser verificado**: qualquer indicador com número validado contra o sistema de
  origem (nenhum item está marcado como validado pela área); URLs de homologação (não existe
  ambiente separado identificado).
- **Status da credencial**: **criada e testada em desenvolvimento local** — perfil
  "Cubo de Dados Corporativo - Leitura" (28 permissões, zero escrita), usuário de serviço
  `cubo-uni@internal.souuni.com`. **Em produção: ver [deploy.md](deploy.md)** para o status exato
  no momento em que você lê isto — pode já ter sido replicada ou ainda estar pendente.
  Procedimento completo em [acesso.md §5](acesso.md).
- **Comando para executar a demonstração** (já funciona localmente; troque a URL/credencial para
  produção quando disponível):
  ```bash
  cd docs/integracao-uni
  cp .env.example .env   # preencher UNI_API_BASE_URL, UNI_API_EMAIL, UNI_API_PASSWORD
  pip install requests
  python exemplos/consumidor.py
  ```

**Este pacote já está "pronto para integração" em desenvolvimento local, verificado ponta a
ponta.** Falta só a réplica em produção (mecanismo já pronto, é reexecutar o mesmo procedimento
contra a VM real) — ver [deploy.md](deploy.md) para o que já foi feito e o que falta.
