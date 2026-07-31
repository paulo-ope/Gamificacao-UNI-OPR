# AGENTS.md - Padrao obrigatorio do projeto

## Objetivo
Este repositorio deve seguir programacao moderna, segura, limpa, responsiva e facil de manter. Evite codigo solto, regra de negocio pesada dentro de tela, duplicacao desnecessaria e alteracoes grandes sem arquitetura clara.

## Regra antes de escrever codigo
Antes de criar, editar ou remover arquivos em tarefas novas, apresente:

1. Diagnostico curto da solicitacao.
2. Arquivos que serao criados, alterados ou removidos.
3. Impacto em arquitetura, seguranca, layout, banco, testes e deploy.
4. Plano de implementacao em etapas.
5. Riscos e como serao evitados.

Depois disso, aguarde validacao do usuario antes de escrever codigo, salvo quando o usuario pedir explicitamente para implementar imediatamente ou quando a mudanca ja estiver em andamento no contexto atual.

Excecao: pode ler arquivos, listar estrutura, rodar diagnosticos e explicar o plano sem validacao previa.

## Fontes do projeto
Leia estes documentos quando a tarefa envolver a area correspondente:

- `docs/manual_programacao_senior.md`: arquitetura, seguranca, banco, Docker/VM, testes, CI/CD, backup e producao.
- `docs/manual_frontend_senior.md`: frontend, componentes, estado, roteamento, performance, formularios, acessibilidade e SEO.
- `docs/code_review.md`: checklist para revisao e validacao de qualidade.

## Stack deste projeto
- Backend: FastAPI, SQLAlchemy, SQLite/PostgreSQL.
- Frontend: Next.js, TypeScript, Tailwind CSS.
- Operacao: Docker e Docker Compose.

## Regras absolutas
- Nao use Base64 como seguranca.
- Nao salve senha em texto puro.
- Nao exponha secrets, tokens ou credenciais no frontend.
- Nao valide permissao apenas no frontend.
- Nao confie apenas na validacao visual da tela.
- Nao crie rota privada sem autenticacao e autorizacao.
- Nao misture regra de negocio pesada na UI.
- Nao crie arquivos gigantes sem necessidade.
- Nao duplique componentes ou logica.
- Nao altere banco sem migration quando houver mudanca estrutural.

## Arquitetura esperada
Fluxo preferido:

Tela -> API -> validacao -> autenticacao -> permissao -> service -> banco -> resposta tratada

## Layout esperado
Toda tela deve preservar o padrao visual existente, com:

- cabecalho e navegacao consistentes;
- cards e tabelas padronizadas;
- modais/drawers padronizados;
- loading, empty state e error state;
- responsividade desktop/tablet/mobile.
- textos em portugues pt-BR com ortografia e acentuacao corretas.

## Seguranca minima
- Validacao no servidor para entradas criticas.
- Permissao validada no backend.
- Sessao/token com expiracao.
- Hash seguro para senhas.
- Variaveis sensiveis em `.env`, nunca no Git.
- Logs sem dados sensiveis.
- Mensagens de erro amigaveis, sem stack trace em producao.

## Qualidade antes de concluir
Quando aplicavel, valide:

- typecheck;
- lint/build;
- testes relevantes;
- ortografia, acentuacao e ausencia de mojibake em textos visiveis e mensagens de API;
- responsividade;
- acessibilidade basica;
- Docker/VM quando a alteracao afetar operacao.

## Economia de contexto
- Trabalhe por modulo.
- Altere somente os arquivos necessarios.
- Nao reescreva o projeto inteiro sem necessidade.
- Nao repita codigo que nao mudou.
- Explique o essencial com objetividade.
