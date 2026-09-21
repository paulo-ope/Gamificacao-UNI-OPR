# Manual — Commit, Push, PR e Deploy

Manual prático e operacional: os comandos reais usados neste projeto para levar uma
mudança de "editada no checkout local" até "rodando em produção". Complementa (não
substitui) as regras obrigatórias de `AGENTS.md` e o contrato de
`docs/manual_desenvolvimento_senior.md` — aqui é só o "como", passo a passo.

Sempre peça confirmação do usuário antes de `commit`, `push`, abrir/mesclar PR ou
rodar o deploy — nenhuma dessas ações é automática, mesmo seguindo este manual.

## 0. Contexto que muda os passos abaixo

- **O checkout é compartilhado por várias sessões em paralelo.** `git status` pode
  mostrar dezenas de arquivos modificados/novos que não são seus (WIP de outra
  sessão). **Nunca** rode `git add -A`/`git add .` nem `git checkout .`/`git clean` —
  sempre `git add <arquivo1> <arquivo2>` só com os arquivos que você de fato mudou
  nesta tarefa, e confira `git status`/`git diff --stat` depois do `add` antes de
  commitar.
- **Branch real de produção é `master`, não `main`.** `main` neste repositório está
  vazio/desatualizado (histórico desencontrado) — todo PR é aberto contra `master`,
  e é `master` que a VM de produção segue. Confirme com
  `gh repo view --json defaultBranchRef` e `git log --oneline origin/master -1` se
  tiver dúvida antes de abrir um PR.
- **Não há CI configurado neste repositório.** A validação de cada PR é manual,
  dentro da própria sessão (lint/typecheck/testes relevantes rodados e descritos na
  PR) — não espere um check automático travar o merge.
- **A VM de produção não é acessível por esta sessão.** Só quem tem acesso SSH em
  `noc.souuni.com` (`/opt/opr-gamificacao`) roda os comandos da seção 4. O máximo que
  a sessão faz é deixar o código pronto em `master` e entregar os comandos exatos.

## 1. Commit

```bash
git status --short                        # confirme o que é seu antes de tudo
git diff -- <arquivo1> <arquivo2>          # revise o diff real do que vai commitar
git add <arquivo1> <arquivo2>              # nunca -A/. num checkout compartilhado
git commit -m "$(cat <<'EOF'
tipo(escopo): resumo curto no imperativo, em português

Corpo opcional: o quê e por quê, não linha a linha do diff. Cite o achado
real/causa raiz quando for correção de bug.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- **Tipo** segue Conventional Commits, como já usado no `git log` deste projeto:
  `fix`, `feat`, `docs`, `refactor`, `test`, `chore`.
- **Escopo** entre parênteses é o módulo/área afetada (`operacao`, `mcp`, `status`,
  `admin`, `gamificacao` etc.), não o nome do arquivo.
- Prefira **um commit por preocupação lógica** (ex.: o fix de código num commit, a
  atualização do `docs/STATUS.md` sobre esse fix em outro) — mais fácil de revisar e
  reverter isoladamente.
- A linha `Co-Authored-By` só entra quando a sessão que commita é o Claude Code (ver
  `CLAUDE.md`/instruções da sessão) — não adicione se o usuário pedir explicitamente
  para não incluir.

## 2. Push

```bash
git push origin <nome-da-branch>
```

- Nunca `--force` sem o usuário pedir explicitamente para aquele push específico —
  branch compartilhada, força pode apagar commit de outra sessão.
- Se o push for rejeitado (branch remota avançou), **não** faça `push --force` para
  "resolver" — puxe (`git fetch` + `git log origin/<branch>..HEAD`) e entenda o que
  mudou antes de decidir.

## 3. Pull Request

```bash
# Criar
gh pr create --base master --head <nome-da-branch> \
  --title "tipo(escopo): resumo curto" \
  --body "$(cat <<'EOF'
## Summary
- O que mudou e por quê (achado real, não só "o quê").

## Test plan
- [x] O que foi verificado e como (comando, print, endpoint testado).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

# Conferir se pode mesclar antes de mesclar
gh pr view <numero> --json state,mergeable,mergeStateStatus

# Mesclar (merge commit, sem apagar a branch — ela continua em uso por outras sessões)
gh pr merge <numero> --merge --delete-branch=false
```

- `--base master`: **não** use `main` (ver seção 0).
- Sempre confira `mergeable`/`mergeStateStatus` antes de mesclar; se vier
  `CONFLICTING` ou `DIRTY`, resolva o conflito com o usuário antes de forçar.
- `--delete-branch=false`: a branch de trabalho deste projeto é reaproveitada por
  várias sessões/PRs seguidos (ver histórico de PRs mesclados na mesma branch) — não
  apague.

## 4. Deploy em produção (só quem tem acesso SSH na VM)

A sessão do Claude Code **não tem acesso à VM**. Esta seção é para o dono do sistema
rodar manualmente depois que o PR foi mesclado em `master`.

```bash
cd /opt/opr-gamificacao
git fetch origin
git checkout master
git merge --ff-only origin/master

# Rebuilda só o que mudou nesse deploy (mais rápido, menos risco):
docker compose build backend     # se o PR mexeu em backend/
docker compose build frontend    # se o PR mexeu em frontend/
docker compose up -d             # sobe os dois containers com a imagem nova
```

- O backend roda `alembic upgrade head` automaticamente no entrypoint — migration
  nova sobe sozinha junto do `docker compose up -d`, não precisa de passo manual
  extra (a menos que a migration em questão exija algo especial — isso fica
  documentado na própria migration ou no PR).
- **Nunca** rode `docker compose down -v` (apaga volumes, inclusive o do Postgres) —
  só `up -d` para aplicar uma imagem nova.

### Verificação pós-deploy

```bash
# 1. Migration aplicada (se o PR trouxe migration)
docker compose exec backend python -m alembic current

# 2. Backend saudável
curl -s -o /dev/null -w "%{http_code}\n" https://operacao.souuni.com/api/health
# esperado: 200

# 3. Frontend respondendo
curl -s -o /dev/null -w "%{http_code}\n" https://operacao.souuni.com
# esperado: 200
```

Depois disso, **confirme visualmente no navegador** a tela específica que o PR
mudou — o `curl` só prova que o serviço subiu, não que a mudança está correta (ver
`docs/normas-qualidade-dados-metricas.md` sobre nunca declarar "corrigido" sem
verificação real).

### Rollback

```bash
cd /opt/opr-gamificacao
git log --oneline -5              # ache o commit de merge anterior
git checkout <commit-anterior>
docker compose build backend frontend
docker compose up -d
```

Sem migration de downgrade automática — se o PR trouxe migration de schema,
verifique se ela tem `alembic downgrade -1` testado antes de reverter o código sem
reverter o banco junto.

## 5. Exemplo completo de ponta a ponta (o que esta sessão fez para o fix da Matriz)

```bash
git add frontend/components/operations/operations-sla-matrix-table.tsx
git commit -m "fix(operacao): corrige desalinhamento de colunas na Matriz de indicadores"

git add docs/STATUS.md
git commit -m "docs(status): registra fix de desalinhamento de colunas na Matriz de indicadores"

git push origin claude/suporte-sync-backfill-madrugada

gh pr create --base master --head claude/suporte-sync-backfill-madrugada \
  --title "fix(operacao): corrige desalinhamento de colunas na Matriz de indicadores"

gh pr merge 37 --merge --delete-branch=false

# (dono do sistema, na VM)
cd /opt/opr-gamificacao && git fetch origin && git checkout master && \
  git merge --ff-only origin/master && docker compose build frontend && \
  docker compose up -d frontend
```

## Ver também

- `docs/integracao-uni/deploy.md` — registro específico do que já foi publicado e
  deployado no pacote de integração externa (histórico, não procedimento genérico).
- `docs/STATUS.md` — estado atual do checkout compartilhado; leia antes de commitar
  para não colidir com WIP de outra sessão.
- `AGENTS.md` / `docs/manual_desenvolvimento_senior.md` — regras obrigatórias que
  este manual não substitui.
