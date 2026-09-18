# Integração UNI — Cubo de Dados Corporativo / Portal Executivo

Pacote de integração **somente-leitura** para outro time (Cubo de Dados Corporativo / Portal
Executivo) consultar os dados de negócio do UNI Workspace com segurança, entendendo significado,
origem, regras e relacionamentos.

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data da análise: 2026-09-17 ·
Autor: análise assistida por Claude Code, leitura direta do código-fonte (não documentação
genérica) — ver [validacao.md](validacao.md) para o que foi de fato executado/verificado.

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
| Desenvolvimento local | `http://localhost:8000/api` (via `docker-compose.yml`, backend na porta 8000) | Confirmado nesta análise — é de onde `openapi.yaml` foi extraído |
| Homologação | não confirmado | Preencher com a equipe de infraestrutura antes de apontar qualquer cliente para lá |
| **Produção** | **`https://operacao.souuni.com/api`** | **Confirmada pelo usuário em 2026-09-17** (dono do sistema, com acesso real ao ambiente). `APP_ENV=production` ainda não foi confirmado diretamente no servidor — assumir que `/docs`/`/redoc`/`/openapi.json` estão desligados lá (comportamento esperado) e usar este `openapi.yaml` versionado como contrato de referência, não uma extração ao vivo de produção. |

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
| [openapi.yaml](openapi.yaml) | Contrato HTTP completo (330 rotas / 392 operações), gerado do schema real do FastAPI |
| [catalogo.json](catalogo.json) | Catálogo estruturado (datasets, métricas, relacionamentos, lacunas) — consumível por máquina |
| [catalogo.md](catalogo.md) | Mesmo catálogo, versão legível — gerado programaticamente a partir do `.json` para garantir consistência |
| [cobertura.md](cobertura.md) | Matriz módulo → dataset → interface → documentação → testes → pendências |
| [acesso.md](acesso.md) | Autenticação, permissões da identidade técnica, classificação de dados pessoais, procedimento de provisionamento |
| [exemplos/consumidor.py](exemplos/consumidor.py) | Script Python executável (auth, filtro, paginação, indicador, erro) |
| [exemplos/chamadas-curl.md](exemplos/chamadas-curl.md) | Chamadas HTTP cruas de exemplo |
| [.env.example](.env.example) | Variáveis necessárias ao consumidor de exemplo, sem segredos |
| [validacao.md](validacao.md) | O que foi de fato testado nesta análise, divergências encontradas, pendências |

## Não há endpoint genérico de SQL nem exposição indiscriminada de tabelas

Cada operação de `openapi.yaml` reflete uma consulta de negócio que já existe nas telas do
sistema, com seus próprios filtros/paginação/regras — não uma tabela crua. Onde havia lacuna real,
este pacote **propõe** adaptações mínimas reaproveitando serviços existentes (ver
[cobertura.md](cobertura.md) → gaps), não implementa nada sem aprovação.

## Como atualizar este pacote quando a API mudar

1. Subir o backend local (`docker compose up -d db backend`, `APP_ENV` diferente de `production`).
2. `curl http://localhost:8000/openapi.json` para obter o schema atual.
3. Reexecutar o processo descrito em `catalogo.json.system.how_to_refresh` para regenerar
   `openapi.yaml` com os metadados deste pacote (servers/tags/descrição) por cima.
4. Revisar `catalogo.json`/`catalogo.md` campo a campo contra os módulos que mudaram desde o
   commit acima (ver `docs/STATUS.md` do repositório principal).
5. Regenerar `catalogo.md` a partir do `catalogo.json` atualizado (não editar os dois em paralelo).
6. Rerodar `exemplos/consumidor.py` contra homologação e atualizar `validacao.md`.

## Resumo objetivo

- **Já pode ser integrado hoje**: a leitura do contrato (`openapi.yaml`) e do catálogo
  (`catalogo.md`/`.json`) — o time consumidor já pode desenhar o modelo do cubo em cima disso.
  Chamadas HTTP reais **não** podem ocorrer ainda, porque não há credencial.
- **Existe, mas ainda não está acessível**: dados de Gamificação/Administração/UNI Localiza via
  conector MCP (o MCP cobre só Operação/Suporte/Agendamento/Gestão/Cockpit); campos sensíveis como
  `raw_payload` (só no detalhe, nunca em lote); telefone/e-mail de colaborador (nenhuma rota expõe
  hoje).
- **O que não pôde ser verificado**: qualquer indicador com número validado contra o sistema de
  origem (nenhum item está marcado como validado pela área nesta análise); comportamento em
  runtime dos caminhos de importação sob falha real (só análise estática do código); URLs reais de
  homologação/produção.
- **O que depende de aprovação**: qualquer mudança de endpoint (mesmo mínima), a criação da
  credencial técnica real, a decisão de onde armazenar o segredo (não há secrets manager
  configurado hoje), e a liberação de qualquer campo hoje classificado como sensível/PII.
- **Status da credencial**: **não criada**. Tentativa de criar um usuário de teste local foi
  bloqueada pelo controle de segurança da sessão (comportamento esperado — credenciais exigem
  aprovação humana explícita). Procedimento completo em [acesso.md §5](acesso.md).
- **Comando para executar a demonstração** (depois que a credencial existir):
  ```bash
  cd docs/integracao-uni
  cp .env.example .env   # preencher UNI_API_BASE_URL e UNI_API_TOKEN
  pip install requests
  python exemplos/consumidor.py
  ```

**Este pacote não está "pronto para integração" em produção** — está pronto para o time
consumidor desenhar o modelo do cubo e para a equipe do UNI Workspace decidir/executar o
provisionamento da credencial. Ver [validacao.md](validacao.md) para a lista completa de
bloqueios.
