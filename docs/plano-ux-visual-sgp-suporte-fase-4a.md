# Plano UX/Visual — SGP Suporte Fase 4A

Data: 2026-08-25

Este documento registra a próxima fase visual do módulo **SGP Suporte** para ser
executada depois dos ajustes de dados em andamento no OPA Suite. O objetivo é
evoluir a experiência da tela `/suporte` sem alterar regra de negócio de TMR,
importação ou cálculo operacional.

## Contexto atual validado

- `docs/STATUS.md` confirma que as Fases 1, 2, 3A, 3B e 3C da OPA Suite já
  foram concluídas.
- A tela `/suporte` já possui visão geral expandida, painel individual por
  atendente e timeline de atendimento.
- Existe uma auditoria de divergência com o painel oficial em
  `docs/auditoria-divergencia-opa-suite-2026-08-25.md`.
- Os ajustes de dados pendentes são responsabilidade de uma próxima tarefa
  separada: volume/importação automática, definição exata de TMR oficial e
  sincronização completa de nomes de clientes.

## Diagnóstico visual

A tela está funcional e rica em informação, mas ainda parece construída por
camadas de fases sucessivas. O problema principal não é falta de dados, e sim
hierarquia visual e leitura operacional.

Pontos observados:

- Muitos cards e blocos competem pela atenção.
- O usuário ainda não entende em poucos segundos o estado atual da operação.
- Estados de erro podem aparecer crus, como `Not Found`, em vez de mensagens
  amigáveis em pt-BR.
- Códigos internos de cliente aparecem com peso visual maior do que deveriam.
- A tabela de atendimentos recentes precisa priorizar nome, status e ação.
- O painel individual por atendente ainda pode parecer uma seção anexada, não
  uma área analítica bem organizada.
- A timeline precisa ganhar leitura mais investigativa, com eventos claros,
  badges por tipo de ator e aviso discreto sobre privacidade.

## Objetivo da Fase 4A

Refinar o layout e a experiência do SGP Suporte para transformar a tela em um
painel operacional maduro, escaneável e consistente com o padrão visual do UNI
Workspace.

Esta fase deve:

- reorganizar a hierarquia da visão geral;
- melhorar cards, tabelas e estados de feedback;
- reduzir ruído visual;
- priorizar nomes amigáveis no lugar de códigos internos;
- preservar todos os contratos de API existentes;
- manter regra de negócio fora da UI;
- respeitar responsividade desktop/tablet/mobile;
- manter textos em português pt-BR correto.

## Fora do escopo

- Alterar cálculo de TMR.
- Alterar política de importação/sincronização automática.
- Fazer backfill de dados históricos.
- Implementar texto completo de conversa.
- Implementar análise por IA.
- Criar rota nova.
- Reescrever o módulo inteiro.

## Direção de layout

### 1. Topo da visão geral

Criar uma leitura mais executiva:

- filtros no topo, com aparência consistente e sem excesso de altura;
- indicação discreta do recorte atual;
- estado da base/importação quando houver dado disponível;
- cards principais com mesma estrutura visual.

KPIs sugeridos:

- Volume;
- Encerrados;
- Taxa de encerramento;
- TMA;
- TMR humano;
- 1ª resposta humana;
- Avaliação média.

### 2. Organização analítica

Separar os blocos por intenção:

- **Operação**: volume, encerrados, em andamento, taxa de encerramento.
- **Tempo**: TMA, TMR humano, primeira resposta.
- **Clientes**: clientes únicos, recorrentes e ranking.
- **Automação**: bot, humano, handoff e não classificados.
- **Distribuição**: status, motivos e canais.

Evitar cards dentro de cards. Usar seções de página ou grids simples.

### 3. Atendimentos recentes

Melhorar escaneabilidade da tabela:

- nome do cliente como texto principal;
- código do cliente como metadado secundário e menor;
- fallback amigável quando o nome não existir;
- status como badge;
- ação de detalhe com ícone e texto curto;
- loading, vazio e erro padronizados.

Texto recomendado quando a API retornar erro:

> Não foi possível carregar os dados deste painel agora.

Evitar mostrar mensagens técnicas cruas como `Not Found`, `TypeError` ou stack
trace.

### 4. Painel individual por atendente

Transformar o painel individual em área de análise clara:

- cabeçalho com nome do atendente e tipo (`Bot` ou `Humano`) quando conhecido;
- resumo com volume, encerrados, taxa de encerramento e avaliação;
- bloco de tempos com TMA, TMR humano e 1ª resposta humana;
- bloco de clientes com únicos, recorrentes e principais reincidentes;
- distribuições por status, motivo e canal;
- automação/handoff com denominador explícito de classificados e não
  classificados.

### 5. Timeline do atendimento

Melhorar leitura investigativa:

- linha vertical com eventos em ordem temporal;
- badges para cliente, bot, humano, sistema e não identificado;
- horário destacado;
- fonte dos eventos indicada discretamente;
- aviso de privacidade quando o texto da mensagem não estiver disponível;
- erro externo tratado sem quebrar a timeline estrutural.

## Arquivos prováveis de alteração futura

- `frontend/app/suporte/page.tsx`
- `frontend/app/suporte/_components/opa-module-components.tsx`
- `frontend/lib/types.ts` somente se for necessário tipar algum estado visual novo
- `docs/STATUS.md`

Não deve haver alteração de banco, migration ou backend nesta fase, salvo se a
implementação encontrar erro contratual real.

## Validações esperadas

Antes de concluir a fase:

- rodar typecheck/build do frontend;
- validar `/suporte` em desktop, tablet e mobile;
- validar estados loading, empty e error;
- revisar textos visíveis em pt-BR;
- confirmar ausência de mojibake;
- confirmar que códigos internos ficaram secundários;
- atualizar `docs/STATUS.md`.

## Riscos e cuidados

- **Misturar correção visual com regra de dado**: evitar. TMR/importação devem
  ficar em tarefa separada.
- **Duplicar componentes**: reaproveitar os componentes já existentes sempre que
  possível.
- **Aumentar complexidade da tela**: preferir reorganização e padronização, não
  adicionar mais blocos.
- **Quebrar contrato da API**: manter consumo dos endpoints atuais.
- **Melhorar só desktop**: validar responsividade antes de encerrar.

## Prompt base para Claude Code

Use este prompt quando for executar a fase:

```text
Leia obrigatoriamente `docs/STATUS.md`, `docs/00-TRILHA-0.md`,
`docs/manual_frontend_senior.md`, `docs/code_review.md` e
`docs/plano-ux-visual-sgp-suporte-fase-4a.md`.

Contexto: as Fases 1, 2, 3A, 3B e 3C do SGP Suporte / OPA Suite já estão
implementadas. Agora a tarefa é somente UX/layout visual da tela `/suporte`.
Não altere cálculo de TMR, importação, banco, migrations, endpoints ou regra de
negócio, salvo se encontrar bug contratual indispensável e documentar antes.

Objetivo: executar a Fase 4A descrita no documento, melhorando a hierarquia
visual, cards, tabela de atendimentos recentes, painel individual por atendente,
timeline e estados loading/empty/error. Priorize nome do cliente sobre código
interno e evite mensagens técnicas cruas como `Not Found`.

Arquivos prováveis:
- `frontend/app/suporte/page.tsx`
- `frontend/app/suporte/_components/opa-module-components.tsx`
- `frontend/lib/types.ts` somente se necessário
- `docs/STATUS.md`

Regras:
- preservar contratos de API existentes;
- manter regra de negócio pesada fora da UI;
- reaproveitar componentes existentes;
- manter textos em português pt-BR correto;
- validar responsividade;
- rodar typecheck/build do frontend;
- atualizar `docs/STATUS.md` ao final com o resultado, testes e pendências.

Antes de editar, apresente diagnóstico, arquivos, impactos, plano e riscos.
Depois implemente somente após validação do usuário.
```

