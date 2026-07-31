# code_review.md - Checklist de revisao senior

Use este arquivo para revisao manual, revisao antes de merge ou quando o usuario pedir review.

## 1. Arquitetura
- [ ] A funcionalidade respeita a organizacao por dominio?
- [ ] A tela nao contem regra de negocio pesada?
- [ ] Services, rotas, validacoes e permissoes estao separados?
- [ ] A alteracao foi minima e segura?
- [ ] Nao houve duplicacao desnecessaria?

## 2. Seguranca
- [ ] Nao usa Base64 como seguranca?
- [ ] Nao salva senha em texto puro?
- [ ] Nao expoe token, secret ou credencial no frontend?
- [ ] Entrada critica e validada no servidor?
- [ ] Permissao e validada no servidor?
- [ ] Erros tecnicos nao aparecem ao usuario final?
- [ ] Logs nao registram dados sensiveis?
- [ ] Rotas privadas estao protegidas?

## 3. Frontend
- [ ] Layout segue o padrao do sistema?
- [ ] Componentes reutilizaveis foram usados quando adequado?
- [ ] Existem estados loading, empty e error?
- [ ] A tela e responsiva em desktop, tablet e mobile?
- [ ] Acessibilidade basica foi validada?
- [ ] Dados de servidor tratam carregamento, erro e atualizacao?
- [ ] Estado global foi usado somente quando necessario?
- [ ] Textos visiveis, labels, botoes, menus, mensagens e estados estao com ortografia, acentuacao e portugues pt-BR corretos?
- [ ] Nao ha mojibake em textos exibidos ao usuario, como `GestÃ£o`, `PermissÃµes`, `UsuÃ¡rios` ou similares?

## 4. Banco de dados
- [ ] Mudanca estrutural tem migration?
- [ ] Indices foram considerados para filtros e buscas?
- [ ] Campos de auditoria foram considerados?
- [ ] Nao ha alteracao manual perigosa no banco?
- [ ] A mudanca preserva compatibilidade com dados existentes?

## 5. Testes e producao
- [ ] Typecheck executa sem erro?
- [ ] Lint/build executa sem erro quando aplicavel?
- [ ] Testes relevantes foram criados ou atualizados?
- [ ] Docker/VM continuam funcionando quando afetados?
- [ ] README ou `.env.example` foram atualizados quando necessario?
- [ ] Foi feita varredura em textos alterados para evitar falta de acento, erro ortografico ou texto tecnico cru para usuario final?

## 6. Decisao final
Resultado da revisao:

- [ ] Aprovado
- [ ] Aprovado com observacoes
- [ ] Reprovado - precisa corrigir riscos antes de seguir
