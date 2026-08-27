# Padrão Oficial de Engenharia do UNI Workspace

## 1. Objetivo

Este manual estabelece o contrato operacional de engenharia para criar, corrigir,
manter e evoluir o UNI Workspace.

Toda implementação DEVE priorizar, nesta ordem:

1. segurança;
2. integridade dos dados;
3. preservação das regras de negócio;
4. estabilidade;
5. clareza arquitetural;
6. desempenho;
7. experiência do usuário;
8. facilidade de manutenção.

Uma tarefa NÃO está concluída apenas porque aparenta funcionar visualmente. Ela
somente pode ser concluída depois da validação dos critérios aplicáveis deste
manual.

Este documento complementa `AGENTS.md` e NÃO substitui, flexibiliza ou sobrescreve
as regras obrigatórias definidas nele. Os detalhes técnicos ficam nos manuais
especializados indicados ao final deste documento.

### 1.1 Linguagem normativa

Neste manual:

- **DEVE**: requisito obrigatório.
- **NÃO DEVE**: comportamento proibido.
- **PODE**: comportamento permitido.
- **PREFIRA**: recomendação quando houver mais de uma solução tecnicamente válida.

O descumprimento de uma regra marcada como DEVE ou NÃO DEVE precisa ser
explicitamente justificado na implementação ou revisão, acompanhado do risco e da
medida compensatória. A expressão "quando aplicável" NÃO elimina uma verificação:
ela exige registrar por que o item não se aplica à mudança.

## 2. Ordem de leitura e prioridade

Antes de implementar uma tarefa, o responsável DEVE seguir esta ordem:

1. Leia `docs/00-TRILHA-0.md` para entender a estrutura e as fontes de verdade.
2. Leia `AGENTS.md` para conhecer as regras obrigatórias de trabalho.
3. Leia este manual para definir o padrão geral da solução.
4. Leia os documentos específicos do módulo e da funcionalidade afetada.
5. Consulte `docs/manual_programacao_senior.md`,
   `docs/manual_frontend_senior.md` e `docs/code_review.md` conforme a área.

Em caso de conflito, DEVEM valer primeiro as regras de segurança e acesso, depois os
contratos e regras de negócio vigentes, a arquitetura documentada e, por fim, as
preferências de implementação.

## 3. Princípios obrigatórios

Toda implementação DEVE:

- compreender o fluxo existente antes de modificar código;
- preservar contratos e regras de negócio fora do escopo;
- limitar alterações ao menor conjunto coerente de arquivos;
- ser testável, rastreável e reversível proporcionalmente ao risco;
- separar apresentação, integração, domínio e persistência;
- reutilizar soluções existentes quando forem tecnicamente adequadas;
- manter uma única fonte de verdade para cada regra de negócio;
- validar dados, autenticação e autorização no backend;
- tratar loading, vazio, erro, sucesso e falta de permissão;
- preservar compatibilidade sempre que possível;
- medir antes de introduzir otimizações complexas;
- validar o comportamento afetado antes de concluir.

Toda implementação NÃO DEVE:

- realizar refatoração ampla sem relação com a tarefa;
- duplicar lógica para acelerar a entrega;
- esconder falhas com `try/catch` genérico ou fallback silencioso;
- confiar em validações feitas apenas no frontend;
- introduzir dependência sem necessidade técnica clara;
- aumentar a complexidade sem benefício verificável;
- repetir um padrão existente reconhecidamente inseguro ou inadequado apenas por
  consistência.

### 3.1 Causa raiz e preservação semântica

- O responsável NÃO DEVE corrigir apenas o efeito visível de um defeito quando
  houver evidência de causa raiz identificável no mesmo escopo.
- Antes de adicionar workaround, fallback ou exceção, DEVE investigar a origem do
  comportamento e registrar por que a correção definitiva não é viável.
- Uma alteração NÃO DEVE modificar silenciosamente filtros, fórmulas, regras de
  SLA, permissões, ordenação, paginação, timezone, unidades, interpretação de
  status ou critérios de inclusão e exclusão de registros.
- Quando qualquer comportamento operacional precisar mudar, a alteração DEVE
  fazer parte explicitamente dos critérios de aceite, da validação e da entrega.
- Melhoria arquitetural NÃO justifica regressão funcional. Quando uma solução
  tecnicamente melhor exigir alteração de contrato, comportamento ou dados
  existentes, o responsável DEVE preservar compatibilidade ou apresentar plano
  explícito de migração.

## 4. Layout moderno e profissional

Um layout moderno não é apenas visualmente novo. Ele deve facilitar leitura,
navegação, comparação de dados e execução das tarefas diárias.

### 4.1 Consistência visual

- Preserve o design system, as cores, a tipografia e os componentes do projeto.
- Mantenha cabeçalho, navegação, tabelas, filtros, formulários, modais e drawers
  consistentes entre os módulos.
- Use ícones conhecidos em ações recorrentes e inclua nome acessível em botões que
  exibem apenas ícone.
- Evite excesso de efeitos, cores, sombras, bordas, cartões e elementos decorativos.
- Organize informações por importância, frequência de uso e relação entre dados.
- Não use tamanho de título de página dentro de painéis, tabelas ou componentes
  compactos.

### 4.2 Responsividade

- Toda tela deve funcionar em desktop, tablet e celular.
- O conteúdo não pode sobrepor, cortar ou ultrapassar seu contêiner.
- Formulários devem se adaptar a uma coluna em telas estreitas.
- Tabelas devem oferecer rolagem horizontal ou uma apresentação móvel adequada.
- Controles importantes devem permanecer alcançáveis sem depender de hover.
- Dimensões de grids, toolbars, botões e indicadores devem ser estáveis para evitar
  deslocamentos durante carregamento ou atualização.

### 4.3 Experiência de uso

- A ação principal de cada tela deve ser fácil de identificar.
- Filtros devem ter comportamento previsível e indicar claramente o estado ativo.
- Ações destrutivas exigem confirmação e informação sobre o impacto.
- Envios devem impedir duplo clique enquanto estiverem em processamento.
- Mensagens devem explicar o problema e, quando possível, a próxima ação.
- Textos visíveis devem estar em português pt-BR, com ortografia e acentuação
  corretas e sem mojibake.

### 4.4 Acessibilidade

- A interface DEVE usar HTML semântico e labels associados aos campos.
- A navegação por teclado e o foco visível DEVEM ser preservados.
- A interface NÃO DEVE comunicar significado apenas por cor.
- Textos, ícones e estados de interação DEVEM ter contraste adequado.
- Modais e drawers DEVEM controlar o foco e permitir fechamento previsível.
- Imagens informativas DEVEM ter texto alternativo adequado.
- Telas novas ou substancialmente alteradas DEVEM buscar conformidade com WCAG 2.2
  nível AA, com verificação automatizada e avaliação manual dos fluxos principais.

### 4.5 Estados obrigatórios da interface

Toda tela dependente de dados DEVE prever, quando aplicável:

- loading inicial;
- sucesso;
- ausência de dados;
- erro recuperável;
- falta de permissão;
- atualização ou revalidação;
- envio em andamento.

A interface NÃO DEVE apresentar área vazia sem explicação. Operações assíncronas
que possam ser acionadas mais de uma vez NÃO DEVEM permitir envios duplicados
acidentais.

## 5. Backend estável e rápido

O backend deve produzir respostas previsíveis, proteger os dados e manter bom
desempenho à medida que o volume e o número de usuários crescerem.

### 5.1 Arquitetura e responsabilidades

O fluxo padrão é:

`Cliente -> Router -> autenticação -> autorização -> validação -> Service -> Persistência -> Schema de resposta -> Cliente`

**Router**

O router DEVE receber a requisição, resolver dependências, acionar autenticação e
autorização, chamar o service e retornar o schema adequado. O router NÃO DEVE conter
regra de negócio complexa, agregação extensa, cálculo de domínio, SQL complexo ou
loops de processamento de negócio.

**Schema/DTO**

Schemas DEVEM definir contratos explícitos e tipados de entrada e saída. Modelos de
persistência NÃO DEVEM ser enviados diretamente ao cliente quando isso puder expor
campos internos, sensíveis ou fora do contrato.

**Service**

O service DEVE concentrar regras de negócio, decisões de domínio, validações que
dependem do estado da aplicação, orquestração e processamento de dados. Cálculos
críticos DEVEM possuir uma única fonte de verdade no backend.

**Persistência**

A camada de persistência DEVE encapsular consultas e gravações sem vazar detalhes
do banco para a interface. Um repository PODE ser usado quando reduzir duplicação
ou complexidade; ele NÃO DEVE ser criado apenas para adicionar uma camada sem valor.

**Integrações externas**

Integrações DEVEM ficar isoladas atrás de clientes ou services próprios, com
timeout, tratamento de erro e contratos conhecidos.

### 5.2 Estabilidade

- Entradas DEVEM ser validadas no servidor, inclusive tipos, limites, formatos e
  combinações.
- Integrações externas DEVEM possuir timeout e tratamento explícito de
  indisponibilidade.
- Retentativas DEVEM ocorrer somente em operações seguras, com limite e espera
  progressiva quando adequada.
- Operações mutáveis suscetíveis a repetição DEVEM considerar idempotência.
- Transações DEVEM impedir gravações parciais em operações atômicas.
- Erros esperados DEVEM retornar status HTTP e mensagens coerentes.
- Stack trace, SQL, credenciais ou detalhes internos NÃO DEVEM ser expostos.
- Jobs e importações DEVEM registrar início, término, resultado e falha.

### 5.3 Desempenho

- Consultas DEVEM evitar N+1 e carregamento de colunas ou relações desnecessárias.
- Listas cujo volume possa crescer DEVEM possuir paginação e limite máximo.
- Filtros, ordenações e agregações devem ocorrer no banco quando isso reduzir
  tráfego e uso de memória com segurança.
- Campos usados frequentemente em busca, relacionamento e ordenação devem ter
  índices avaliados com base nas consultas reais.
- Defina limites para upload, payload, exportação e intervalos de consulta.
- Cache somente PODE ser usado com estratégia clara de expiração e invalidação.
- Operações demoradas devem considerar processamento assíncrono, sem ocultar o
  estado ou a falha do trabalho.
- Otimizações relevantes DEVEM ser verificadas com medição reproduzível e cenário
  comparável. Endpoints críticos novos ou alterados DEVEM ter volume esperado e
  impacto de latência avaliados; metas numéricas DEVEM ser definidas pelo contexto
  real, não por um número universal sem medição.

### 5.4 Contratos de API

- Entradas e saídas devem usar schemas explícitos e tipados.
- Campos, unidades, fusos, paginação e filtros devem ser documentados.
- Alterações incompatíveis exigem planejamento de migração ou versionamento.
- Respostas de erro devem seguir formato consistente.
- Dados sensíveis ou sem permissão nunca devem ser serializados.
- O frontend deve consumir o contrato da API, sem recriar regras do backend.

### 5.5 Métricas e cálculos

- Toda métrica operacional DEVE possuir definição única, rastreável e testável.
- A definição DEVE identificar, quando aplicável, universo considerado, filtros,
  numerador, denominador, período, timezone, regras de exclusão, regra de
  arredondamento e fonte dos dados.
- O frontend NÃO DEVE reinterpretar ou recalcular métricas oficiais quando o
  backend já possuir a regra de negócio correspondente.
- Dashboards e relatórios NÃO DEVEM apresentar números plausíveis sem validação da
  regra que os produziu.
- Mudança em métrica, fórmula, filtro ou arredondamento DEVE ser tratada como
  mudança de regra de negócio.

## 6. Código organizado e limpo

### 6.1 Estrutura

- O código DEVE ser organizado por domínio e respeitar os limites de cada módulo.
- Nomes DEVEM expressar intenção e NÃO DEVEM usar abreviações ambíguas.
- Uma função DEVE executar uma responsabilidade coerente.
- Funções ou componentes DEVEM ser extraídos quando isso reduzir complexidade real ou
  duplicação relevante.
- Dependências circulares e importações entre módulos sem contrato definido NÃO
  DEVEM ser introduzidas.
- Código morto somente PODE ser removido depois de confirmar que não possui
  consumidores.

### 6.2 Clareza

- PREFIRA código direto a construções engenhosas difíceis de explicar.
- Tipos DEVEM ser explícitos nos limites entre módulos, API e banco.
- Comentários DEVEM explicar decisões, restrições ou motivos e NÃO DEVEM apenas
  repetir o código.
- Constantes importantes DEVEM ter nomes e unidades claros.
- Datas, moedas, percentuais, durações e fusos DEVEM ser tratados de forma
  consistente em todo o fluxo.
- Refatoração não relacionada NÃO DEVE ser misturada com correção funcional.

### 6.3 Frontend

- Componentes de página DEVEM coordenar a experiência; componentes reutilizáveis cuidam
  de partes visuais bem definidas.
- Regra de negócio pesada e cálculo de KPI NÃO DEVEM ficar na tela.
- Estado local DEVE permanecer local; dados remotos DEVEM ter estratégia de
  carregamento, atualização e invalidação.
- O mesmo dado NÃO DEVE ser duplicado em estados diferentes sem justificativa.
- Toda tela dinâmica DEVE cumprir os estados definidos na seção 4.5.
- Props, retornos de hooks e dados de API DEVEM ser tipados.

### 6.4 Next.js e entrega de JavaScript

- No App Router, Server Components DEVEM ser o padrão; `"use client"` somente DEVE
  ser usado onde houver interatividade, estado ou API exclusiva do navegador.
- Chamadas de dados independentes DEVEM ser paralelizadas quando isso evitar
  waterfalls sem prejudicar limites do backend.
- Cache e revalidação DEVEM ser escolhas explícitas; dado sensível ou específico do
  usuário NÃO DEVE receber cache público.
- Navegação, imagens, fontes e scripts DEVEM usar os recursos do Next.js quando eles
  oferecerem acessibilidade, otimização e prevenção de layout shift adequadas.
- Dependências enviadas ao navegador DEVEM ter custo e necessidade avaliados.

## 7. Banco de dados e integridade

- Toda mudança estrutural DEVE usar migration versionada, revisável e reproduzível.
- Migration gerada automaticamente DEVE ser revisada manualmente; autogenerate NÃO
  DEVE ser tratado como prova de correção ou completude.
- A migration DEVE considerar dados existentes, execução em produção e rollback ou
  estratégia documentada de recuperação.
- Alterações destrutivas DEVEM ter dependências, consumidores, backup, tempo de
  bloqueio e plano de implantação avaliados explicitamente.
- Constraints, chaves estrangeiras e unicidade DEVEM ser usadas quando representarem regras
  verdadeiras do domínio.
- A integridade NÃO DEVE depender apenas do frontend.
- Transações DEVEM cobrir operações que precisam ser atômicas.
- Cada thread ou tarefa concorrente DEVE usar sua própria `Session` ou
  `AsyncSession`; uma mesma sessão NÃO DEVE ser compartilhada concorrentemente.
- Exclusões devem respeitar histórico, auditoria e regras de retenção.
- Antes de operações arriscadas em produção, confirme backup e procedimento de
  restauração.
- Consultas novas ou alteradas devem ser avaliadas quanto a volume, índices e
  impacto de bloqueio.

## 8. Segurança obrigatória

- Dados vindos do cliente DEVEM ser considerados não confiáveis.
- O backend DEVE validar identidade, permissão, escopo ou ownership, formato,
  limites e existência dos recursos envolvidos.
- Senhas NÃO DEVEM ser salvas em texto puro e DEVEM usar algoritmo de hash adequado.
- Base64 NÃO DEVE ser usado como proteção ou criptografia.
- Secrets, tokens ou credenciais NÃO DEVEM aparecer no frontend ou no Git.
- Toda rota privada DEVE validar autenticação e autorização no backend.
- O acesso DEVE seguir o menor privilégio e o escopo do usuário.
- Conteúdo do usuário NÃO DEVE ser renderizado como HTML sem sanitização.
- Cookies de sessão DEVEM usar configurações seguras adequadas ao ambiente.
- Endpoints sensíveis DEVEM considerar rate limiting e auditoria conforme o risco.
- Logs NÃO DEVEM conter senhas, tokens, documentos completos ou dados sensíveis
  desnecessários.
- Stack trace, SQL, variáveis de ambiente e informações internas de infraestrutura
  NÃO DEVEM ser expostos ao cliente.
- A coleta e a retenção de dados DEVEM respeitar finalidade e necessidade.
- Controles de segurança novos ou alterados DEVEM ser verificados com base no OWASP
  ASVS 5.0 no nível proporcional ao risco da funcionalidade.

## 9. Tratamento de erros e observabilidade

- Erros previstos DEVEM ter resposta controlada e mensagem útil.
- Erros inesperados DEVEM ser registrados com contexto técnico suficiente para
  investigação, sem vazar informação sensível.
- Identificador de correlação DEVE ser usado quando um fluxo atravessar serviços ou
  jobs e sempre que a rastreabilidade operacional exigir.
- Eventos importantes de autenticação, permissão, importação e alteração crítica
  DEVEM ser registrados conforme o risco.
- Logs estruturados DEVEM informar, quando disponíveis, operação, módulo,
  identificador da requisição, identificador do recurso, resultado e tipo do erro.
- `console.log`, `print` ou equivalente NÃO DEVE permanecer como solução de
  observabilidade em código de produção.
- Métricas operacionais DEVEM permitir acompanhar latência, taxa de erro,
  disponibilidade e execução de jobs críticos.
- PREFIRA correlação entre logs, métricas e traces conforme os padrões do
  OpenTelemetry.
- Alertas DEVEM ser acionáveis e evitar ruído sem contexto.

## 10. Testes e validação

O nível de teste DEVE acompanhar o risco e o alcance da mudança.

- Regra de negócio DEVE testar cenários normais, limites e falhas.
- API DEVE testar contrato, autenticação, permissão, validação e status HTTP.
- Banco DEVE testar migrations e consultas críticas quando aplicável.
- Integração externa DEVE usar respostas controladas para sucesso, timeout e erro.
- Frontend DEVE validar interação, estados e permissões importantes.
- Fluxo crítico DEVE ter teste integrado ou ponta a ponta quando o custo do erro for
  alto.
- Correção de defeito DEVE incluir teste que reproduza a regressão quando viável.

Antes de concluir, execute os comandos aplicáveis de lint, typecheck, testes e
build. Quando algum comando não puder ser executado, registre claramente o motivo e
o risco restante.

## 11. Produção, Docker e deploy

- Desenvolvimento, homologação e produção DEVEM ter configurações separadas.
- Secrets DEVEM vir de variáveis de ambiente ou gerenciador apropriado.
- Imagens e dependências DEVEM ter versões controladas e atualizações de segurança
  acompanhadas.
- Imagens Docker DEVEM usar origem confiável, contexto reduzido por `.dockerignore`
  e somente os pacotes necessários. PREFIRA builds em múltiplos estágios e usuário
  não privilegiado quando compatível com o serviço.
- Health checks DEVEM refletir se o serviço realmente pode atender requisições.
- Migrations DEVEM fazer parte de um procedimento controlado de implantação.
- Mudanças críticas DEVEM ter plano de rollback.
- Backups automáticos somente PODEM ser considerados confiáveis quando o restore for
  testado.
- O pipeline DEVE impedir deploy quando verificações obrigatórias falharem.
- Mudanças em infraestrutura, banco ou configuração DEVEM atualizar a documentação
  operacional correspondente.

## 12. Processo de implementação

### Antes de alterar

1. Defina o resultado esperado e os critérios de aceite.
2. Identifique módulos, arquivos, contratos, dados e usuários afetados.
3. Leia a documentação específica e confirme as regras de negócio.
4. Avalie impactos em segurança, desempenho, banco, layout, testes e deploy.
5. Apresente diagnóstico, arquivos envolvidos, plano e riscos conforme `AGENTS.md`.

### Durante a alteração

1. Trabalhe somente no escopo aprovado.
2. Preserve padrões existentes que continuam corretos.
3. Implemente em etapas pequenas e verificáveis.
4. Atualize testes junto com o comportamento.
5. Registre decisões que não sejam evidentes pelo código.

### Antes de entregar

1. Revise o diff e remova mudanças acidentais.
2. Execute as verificações proporcionais ao risco.
3. Confirme segurança, permissões, responsividade e estados da interface.
4. Verifique compatibilidade de contratos e migrations.
5. Atualize documentação e `docs/STATUS.md` quando houver decisão ou evolução
   relevante do projeto.

## 13. Definição de pronto

Uma tarefa somente PODE ser marcada como concluída quando os itens aplicáveis forem
verdadeiros:

- [ ] O comportamento atende aos critérios de aceite.
- [ ] O fluxo principal solicitado foi validado.
- [ ] O comportamento anterior não relacionado foi preservado.
- [ ] Filtros, fórmulas, SLA, permissões, ordenação, paginação, timezone, unidades
      e status foram preservados ou alterados explicitamente nos critérios de
      aceite.
- [ ] A alteração respeita os limites dos módulos.
- [ ] A regra de negócio possui uma fonte de verdade clara.
- [ ] Métricas e cálculos afetados foram validados contra sua fonte de verdade.
- [ ] Entradas, autenticação e permissões são validadas no backend.
- [ ] Não há credenciais ou dados sensíveis expostos.
- [ ] O layout segue o padrão visual e funciona em desktop, tablet e celular.
- [ ] Loading, vazio, erro, sucesso e falta de permissão foram considerados.
- [ ] Atualização e envio em andamento foram validados quando existentes.
- [ ] O código está tipado, legível e sem duplicação relevante.
- [ ] Consultas e endpoints possuem limites e desempenho compatível com o uso.
- [ ] Mudanças estruturais de banco possuem migration.
- [ ] Testes relevantes foram criados ou atualizados e executados.
- [ ] Lint foi executado sem erro.
- [ ] Typecheck foi executado sem erro.
- [ ] Build foi executado sem erro.
- [ ] Não existe regressão conhecida no escopo validado.
- [ ] Não existem logs, flags ou código de debug temporário.
- [ ] Logs e mensagens não expõem detalhes internos ou dados sensíveis.
- [ ] Documentação e operação foram atualizadas quando necessário.
- [ ] Riscos restantes e validações não executadas foram informados.

## 14. Proibições

- NÃO criar endpoint duplicado sem verificar os existentes.
- NÃO copiar regra de negócio para dois lugares.
- NÃO colocar regra de negócio crítica apenas no frontend.
- NÃO criar rota privada sem autenticação e autorização no servidor.
- NÃO fazer mudança estrutural no banco sem migration.
- NÃO expor stack trace ou erro bruto ao usuário.
- NÃO retornar ou carregar listas potencialmente ilimitadas.
- NÃO duplicar cálculo de KPI em telas ou módulos.
- NÃO alterar contrato de API sem identificar e avaliar seus consumidores.
- NÃO trocar arquitetura, framework ou contrato sem necessidade e aprovação.
- NÃO refatorar arquivos fora do escopo sem necessidade técnica demonstrável.
- NÃO mascarar erro com fallback silencioso ou dado potencialmente incorreto.
- NÃO corrigir sintoma ignorando causa raiz identificável no mesmo escopo.
- NÃO alterar filtro, fórmula, SLA, status, timezone, permissão ou métrica sem
  declarar a mudança como regra de negócio.
- NÃO declarar a tarefa concluída sem informar verificações não executadas.

## 15. Regras para agentes de desenvolvimento

Antes de alterar código, o agente DEVE:

1. localizar os arquivos relacionados;
2. identificar o fluxo atual de ponta a ponta;
3. procurar padrões e implementações equivalentes no repositório;
4. identificar contratos, regras e dados que não podem mudar;
5. identificar filtros, métricas, permissões, status, fusos e fórmulas afetadas;
6. verificar documentação e estado atual do módulo;
7. implementar a menor alteração coerente possível;
8. revisar o próprio diff e executar a definição de pronto aplicável.

O agente NÃO DEVE assumir arquitetura, nomes de arquivos, endpoints, schemas,
modelos de dados ou permissões sem verificar o repositório. Quando houver dúvida
entre criar uma solução e reutilizar uma existente, DEVE primeiro procurar a
implementação equivalente e avaliar sua adequação.

## 16. Documentos complementares

- `AGENTS.md`: regras obrigatórias e fluxo de validação antes de editar.
- `docs/manual_programacao_senior.md`: backend, arquitetura, banco, segurança,
  Docker, observabilidade e CI/CD.
- `docs/manual_frontend_senior.md`: componentes, estado, Next.js, responsividade,
  formulários, acessibilidade e padrão visual.
- `docs/code_review.md`: checklist de revisão técnica.
- `docs/normas-qualidade-dados-metricas.md`: métricas, filtros, importações e
  dashboards.
- `docs/STATUS.md`: estado atual, decisões recentes e próximos passos.

## 17. Referências técnicas

Estas fontes fundamentam o padrão e DEVEM ser revisitadas quando o projeto atualizar
suas versões principais. Referências verificadas em 26 de agosto de 2026:

- [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/):
  requisitos verificáveis de segurança para aplicações web.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/): acessibilidade testável e independente
  de tecnologia.
- [Next.js — Production Checklist](https://nextjs.org/docs/app/guides/production-checklist):
  produção, renderização, dados, acessibilidade, segurança, tipagem e desempenho.
- [FastAPI — Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/):
  organização modular e uso de `APIRouter` e dependências.
- [SQLAlchemy — Session Basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html):
  transações, ciclo de vida e concorrência de sessões.
- [Alembic — Autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html):
  geração e revisão de migrations.
- [OpenTelemetry — Signals](https://opentelemetry.io/docs/concepts/signals/): logs,
  métricas e traces correlacionáveis.
- [Docker — Building Best Practices](https://docs.docker.com/build/building/best-practices/):
  imagens mínimas, builds em estágios, cache, versões e CI.

## Regra final

Uma solução de nível sênior não é a que possui mais código ou mais tecnologia. É a
que resolve o problema com clareza, protege o sistema, responde bem sob uso real,
pode ser testada e permite que outra pessoa a mantenha com confiança.
