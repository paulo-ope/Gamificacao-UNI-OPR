# Deploy — o que foi publicado, versão e verificação pós-deploy

Registro de propósito único: separar claramente "código mesclado" de "código rodando em
produção" — são coisas diferentes, e este pacote nunca declara a segunda sem verificar de fato
(ver `AGENTS.md` e o pedido original do dono do sistema, que exige isso explicitamente).

## O que foi publicado (mesclado em `master`, GitHub)

| PR | Commit de merge | Conteúdo |
|---|---|---|
| [#29](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/29) | `f569260` | Filtros padronizados, matriz de SLA, Swagger de integração externa (versão inicial, só módulo `operations`) |
| [#30](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/30) | `d02138f` | Migration dos grupos de SLA extras (Alteração de Endereço/Tecnologia, Remoção de Equipamentos, Viabilidades) + docstrings nos 64 endpoints de Operação Analítica |
| [#31](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/31) | `423d0d7` | Swagger ampliado para os 9 módulos de negócio (antes só `operations`), com trava estrutural GET-only |
| [#32](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/32) | `8434a89` | Descrição geral + por módulo no schema OpenAPI |
| [#33](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/33) | `dc2d7b8` | Permissão exigida (extraída por introspecção real do código) + erros padrão (401/403/422) em cada operação |
| [#34](https://github.com/paulo-ope/Gamificacao-UNI-OPR/pull/34) | `5e949e6` | Interface Scalar (moderna) como padrão, Swagger clássico como fallback em `/swagger` |

Todos sem CI configurado neste repositório — validação de cada PR foi manual, dentro da sessão
(import limpo, suíte de testes alvo, verificação ao vivo no navegador), descrita na própria
descrição de cada PR no GitHub.

## Status do deploy físico na VM de produção

**No momento em que este arquivo foi escrito pela última vez: PENDENTE.** `master` no GitHub tem
todo o código acima; a VM (`/opt/opr-gamificacao` em `noc.souuni.com`) ainda não rodou
`git merge` + rebuild para trazer essas mudanças — só o dono do sistema tem acesso a essa VM (ver
`docs/STATUS.md` do repositório principal e o histórico desta sessão para o motivo: acesso SSH
exige senha/decisão do dono, não algo que o assistente de IA executa sozinho).

### Procedimento de deploy (o que precisa rodar na VM, por quem tem acesso)

```bash
cd /opt/opr-gamificacao
git fetch origin
git checkout master
git merge --ff-only origin/master
docker compose build backend
docker compose up -d
```

O backend já roda `alembic upgrade head` automaticamente no entrypoint do container — a migration
dos grupos de SLA extras (PR #30) sobe sozinha, e é idempotente (pula grupo/assunto que já existe
pelo nome único, então não duplica o que já havia sido inserido manualmente antes desta migration
existir).

### Verificação pós-deploy (rodar depois do `docker compose up -d`)

```bash
# 1. Migration aplicada
docker compose exec backend python -m alembic current
# esperado: revisão head mais recente, sem erro

# 2. Backend saudável
curl -s -o /dev/null -w "%{http_code}\n" https://operacao.souuni.com/api/health
# esperado: 200

# 3. Doc de integração acessível (com um token válido)
curl -s -o /dev/null -w "%{http_code}\n" "https://operacao.souuni.com/api/admin/docs/integracao-uni/openapi.json?token=<token>"
# esperado: 200, e o schema deve ter 182 paths (só GET)
```

### Provisionamento da credencial em produção (depois do deploy de código)

O perfil `"Cubo de Dados Corporativo - Leitura"` e o usuário `cubo-uni@internal.souuni.com` foram
criados e testados em **desenvolvimento local** (ver [acesso.md §5](acesso.md) e
[validacao.md](validacao.md)). A réplica em produção usa o mesmo script (ORM direto via
`docker compose exec backend python`), roteirizado, mas **ainda não executado contra produção** —
precisa do deploy de código acima primeiro (o modelo `OperationSlaGroup`/permissões novas como
`admin:integrations:read` só existem depois do merge). Quando executado, atualizar esta seção com:

- [ ] Perfil criado em produção (confirmar `id`)
- [ ] Usuário de serviço criado em produção (confirmar `id`, **nunca** registrar a senha aqui)
- [ ] Login real testado em produção (`POST https://operacao.souuni.com/api/auth/login`)
- [ ] Leitura confirmada (`200`) e escrita confirmada como bloqueada (`403`) contra produção
- [ ] `exemplos/consumidor.py` rodado com sucesso apontando para
      `UNI_API_BASE_URL=https://operacao.souuni.com/api`

## Versão

`app.version` do backend (`backend/app/main.py`) hoje é `0.1.0` — o projeto não usa versionamento
semântico por release ainda; a referência de "versão publicada" real é o **commit de merge mais
recente da tabela acima**, não um número de versão.

## Reversão

Não há uma migration de downgrade específica para as mudanças desta rodada além do padrão já
existente (`alembic downgrade -1` por migration, testado localmente para a migration dos grupos de
SLA extras — ver commit `d6ec085`). Reverter o código é um `git checkout` do commit anterior +
rebuild; como as mudanças desta rodada são só documentação/schema/leitura (nenhuma rota de negócio
alterada), o risco de reversão é baixo.
