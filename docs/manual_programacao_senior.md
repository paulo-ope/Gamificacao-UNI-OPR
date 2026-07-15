# Manual de Programacao Senior

## Objetivo
Criar, revisar e manter projetos limpos, seguros, responsivos e preparados para execucao em ambiente local, Docker/VM e producao.

## 1. Como usar este manual
Este projeto usa tres camadas de orientacao:

- `AGENTS.md`: regras obrigatorias e indice rapido.
- `docs/manual_programacao_senior.md`: arquitetura, seguranca, banco, operacao e qualidade.
- `docs/manual_frontend_senior.md` e `docs/code_review.md`: padroes especificos e checklist.

Para tarefas grandes, leia `AGENTS.md` e os documentos relacionados antes de planejar a implementacao.

## 2. Principios obrigatorios
- Criar estrutura antes de criar funcionalidade.
- Nao misturar regra de negocio pesada dentro da tela.
- Nao usar Base64 como seguranca.
- Nao salvar senha em texto puro.
- Nao expor secrets no frontend.
- Validar entrada no frontend quando ajudar UX e no backend para seguranca.
- Validar permissoes no servidor.
- Usar componentes reutilizaveis.
- Alterar somente o necessario.
- Manter o projeto preparado para Docker/VM.

## 3. Arquitetura modular
Fluxo recomendado:

Tela -> API -> validacao -> autenticacao -> permissao -> service -> banco -> resposta tratada

Organize por dominio sempre que possivel. Regra de negocio deve viver em service/backend, nao presa a componente visual.

## 4. Backend
- Rotas devem ser pequenas e delegar calculo a services.
- Services devem concentrar regra de negocio.
- Validacoes criticas precisam ocorrer no servidor.
- Permissoes devem ser checadas antes de retornar ou alterar dados protegidos.
- Respostas devem ser estruturadas e amigaveis para o frontend.

## 5. Banco de dados
- Mudancas estruturais exigem migration.
- Campos usados em filtros e buscas devem considerar indice.
- Dados historicos e auditoria devem ser preservados quando a regra exigir rastreabilidade.
- Evite nomes genericos como `data1`, `info`, `valor2`.
- Planeje backup e restore antes de producao real.

## 6. Seguranca
- CSRF quando houver cookies/sessao e metodos mutaveis.
- Protecao contra XSS: nao renderizar HTML do usuario sem sanitizacao.
- Rate limiting em login e endpoints sensiveis quando aplicavel.
- Sessao/token com expiracao.
- Logs sem dados sensiveis.
- Secrets apenas em `.env` ou secret manager.
- LGPD: coletar somente dados necessarios e controlar acesso.

## 7. Docker, VM e operacao
Arquivos esperados quando aplicavel:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `.dockerignore`
- `README.md`

Regras:

- Nao colocar secrets no Dockerfile.
- `.env` real nao entra no Git.
- Usar volumes persistentes para banco.
- Usar `restart: unless-stopped` em servicos de producao.
- Aplicar migrations na subida ou no pipeline.
- Proxy reverso com HTTPS em producao.

## 8. Observabilidade e CI/CD
- Pipeline deve rodar lint, typecheck, testes e build antes do deploy.
- Logs devem registrar acoes importantes e erros inesperados.
- Monitoramento de erros deve ser considerado em producao.
- Backup automatico e teste de restore sao parte da operacao.
- Ambientes separados: desenvolvimento, homologacao e producao.

## 9. Checklist final
- [ ] Arquitetura modular seguida.
- [ ] Tela sem regra de negocio pesada.
- [ ] Validacao no servidor.
- [ ] Permissao no servidor.
- [ ] Sem Base64 como seguranca.
- [ ] Sem senha pura.
- [ ] Sem secrets no frontend.
- [ ] Layout padrao aplicado.
- [ ] Responsivo em desktop/tablet/mobile.
- [ ] Estados loading/empty/error.
- [ ] Acessibilidade basica verificada.
- [ ] Testes definidos ou implementados.
- [ ] Banco com migration quando necessario.
- [ ] Docker/VM considerado quando afetado.
- [ ] README e `.env.example` atualizados quando necessario.
- [ ] Alteracao minima e segura.
