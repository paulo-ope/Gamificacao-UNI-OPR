# Manual Frontend Senior

## Objetivo
Padronizar frontend com Next.js, TypeScript, Tailwind CSS, acessibilidade, performance e responsividade, preservando o desenho visual existente do produto.

## 1. Componentes
Use composicao controlada:

- atoms: Button, Input, Icon, Badge, Label.
- molecules: SearchField, MetricCard, FormField, FilterGroup.
- organisms: Header, Sidebar, DataTable, ComplexForm, DashboardGrid.
- templates: estrutura de pagina sem dados reais.
- pages: rotas dentro de `app/`.

Crie componente reutilizavel quando um bloco visual for usado em dois ou mais lugares. Evite grandes blocos de `div` com classes repetidas.

## 2. Estado
Antes de escolher onde guardar estado, responda:

1. O estado e compartilhado entre componentes distantes?
2. E atualizado com frequencia?
3. Vem do servidor ou e local?
4. Precisa de cache, refetch ou invalidacao?

Use estado local para UI isolada. Use cache/refetch para dados de servidor quando houver biblioteca adequada no projeto. Evite duplicar dado remoto em estado global sem justificativa.

## 3. Roteamento Next.js
- `app/layout.tsx`: layout raiz e providers.
- rotas privadas devem ter protecao de acesso.
- `loading.tsx`: skeleton por rota quando aplicavel.
- `error.tsx`: tratamento de erro local.
- `not-found.tsx`: pagina 404.
- `route.ts`: API route quando necessario.

Evite `window.location` quando recursos do Next.js resolverem o fluxo.

## 4. Estilos e responsividade
- Preserve variaveis, cores e padroes do projeto.
- Breakpoints: `sm 640`, `md 768`, `lg 1024`, `xl 1280`.
- Tabelas grandes devem ter scroll horizontal ou alternativa adequada no mobile.
- Formularios devem funcionar em uma coluna no mobile.
- Evite valores arbitrarios sem necessidade.
- Texto nao pode cortar, sobrepor ou estourar o container.

## 5. Performance
- Evite re-render causado por estado amplo demais.
- Derive dados diretamente ou com `useMemo` quando houver custo real.
- Componentes pesados podem usar carregamento dinamico.
- Listas muito grandes devem considerar virtualizacao.
- Meça com Lighthouse/Web Vitals quando a tela for critica.

## 6. Formularios
- Padronize label, ajuda e erro.
- Botao de submit deve ter loading e bloquear duplo envio.
- Mascara visual nao deve ser salva no banco.
- Validacao assincrona deve ter debounce quando fizer sentido.

## 7. Erros e feedback
- Mensagens devem ser amigaveis.
- Nao mostrar `TypeError`, stack trace ou erro bruto ao usuario.
- Acoes destrutivas exigem confirmacao.
- Estados de vazio devem orientar a proxima acao.

## 8. API e cache
- Dados dinamicos devem tratar loading, erro e vazio.
- Mutations devem atualizar ou recarregar o dado afetado.
- Nao confie em feature flag como seguranca.

## 9. Acessibilidade
- Inputs com label associado ou `aria-label`.
- Icone sozinho com `aria-label`.
- Foco visivel.
- Modal/drawer deve prender foco quando o componente base oferecer suporte.
- Contraste minimo adequado para texto.
- Paginas em portugues devem usar `lang="pt-BR"`.

## 10. Padronizacao
- Componentes: PascalCase.
- Hooks: useCamelCase.
- Pastas: kebab-case.
- Props booleanas: `isLoading`, `hasError`, `isDisabled`.
- Handlers: `onClick`, `onSubmit`, `onChange`.
- Imports: React/Next, bibliotecas, componentes, hooks, tipos, constantes e CSS.
