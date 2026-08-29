# Fase 2 do Portal do Colaborador — Ciclo de Vida da Conta

Documento de planejamento. Nenhuma linha de código, migration, schema ou dado real é
criada por este documento — ele define o que cada sub-fase (2A a 2E) precisa fazer, em
que ordem, com que modelo de dados e com que critérios de aceite, para que cada uma
possa depois ser implementada como uma tarefa pequena e independente.

Este documento complementa, sem substituir, `AGENTS.md`,
`docs/manual_desenvolvimento_senior.md`, `docs/manual_programacao_senior.md`,
`docs/manual_frontend_senior.md` e `docs/code_review.md`. Toda implementação futura de
qualquer sub-fase abaixo continua sujeita a essas regras, inclusive ao fluxo de
diagnóstico e plano antes de escrever código descrito em `AGENTS.md`.

## 1. Objetivo da fase

A Fase 1 (já implementada, ver `docs/STATUS.md`) resolveu o primeiro acesso
obrigatório: um usuário criado pelo admin já vinculado a um `collaborator_id` é forçado
a confirmar CPF/telefone/e-mail e trocar senha antes de ver qualquer dado
financeiro/operacional individual (ranking, O.S., fechamento).

O que a Fase 1 não cobre — e é o que esta Fase 2 estrutura — é o resto do ciclo de vida
da conta:

- o colaborador não tem como trocar a própria senha depois do primeiro acesso;
- um admin não tem tela nem endpoint para forçar reset de senha ou reabrir o primeiro
  acesso de alguém (hoje só existe o campo `must_change_password` no banco, sem
  nenhuma forma de acioná-lo manualmente — pendência já registrada duas vezes em
  `docs/STATUS.md`);
- não existe convite: hoje a única forma de alguém ganhar acesso é um admin criar o
  `User` diretamente escolhendo a senha inicial;
- não existe canal formal para alguém sem conta pedir acesso;
- não existe "esqueci minha senha" — perder a senha hoje depende de um admin
  intervir manualmente, o que nem sequer é possível ainda (depende da sub-fase 2B).

Esta Fase 2 fecha esse ciclo completo — do convite inicial à recuperação de senha —
preservando o princípio de segurança estabelecido logo abaixo, que é a regra mais
importante deste documento.

## 2. Princípio de segurança

- O colaborador PODE completar o próprio cadastro (Fase 1, já existe) e PODE trocar a
  própria senha (2A).
- O colaborador NÃO PODE escolher livremente a qual `collaborator_id` (vínculo
  financeiro/operacional) sua conta se associa. Esse vínculo decide quais O.S.,
  pontuação, ranking e fechamento aparecem para aquele login — é dado sensível e nunca
  pode ser autoatribuído.
- O vínculo `User.collaborator_id` só pode ser criado ou alterado por:
  - ação direta de um admin com a permissão `users:manage` (já existe hoje, em
    `create_user`/`update_user`, `backend/app/api/routes/users.py`);
  - um convite emitido por um admin (2C) — o admin decide o `collaborator_id` do
    convite; a pessoa convidada só define a própria senha;
  - a aprovação de uma solicitação de acesso (2D) — o pedido nasce sem vínculo; um
    admin decide, ou confirma um vínculo sugerido por correspondência automática,
    antes de liberar qualquer acesso.
- Nenhuma sub-fase desta Fase 2 pode contornar essa regra. Qualquer mecanismo futuro
  de correspondência automática de `collaborator_id` (por CPF, e-mail etc.) DEVE
  tratar o resultado como sugestão, nunca como vínculo automático sem confirmação
  humana.

## 3. Fase 2A — Troca de senha pelo próprio usuário

**Contexto**: hoje a única troca de senha existente acontece dentro do fluxo de
primeiro acesso (Fase 1, `complete_first_access` em
`backend/app/services/portal_first_access.py`). Um usuário que já passou por ali não
tem como trocar a senha por conta própria depois.

**Escopo**:

- Endpoint autenticado (nome e local exatos a definir na implementação — ex.:
  `POST /portal/profile/change-password`) que recebe senha atual, nova senha e
  confirmação.
- Regras: senha atual precisa bater via `verify_password` (`core/security.py`, já
  existe); nova senha segue a mesma política mínima de 8 caracteres já usada na Fase 1;
  nova senha diferente da atual é validação de UX, não é bloqueio crítico de
  segurança; grava `password_hash` (via `hash_password`, já existe) e
  `password_changed_at` (campo já existe desde a Fase 1, hoje só informativo).
- NÃO altera `must_change_password` nem `first_access_completed_at` — troca voluntária
  de senha não é primeiro acesso.
- Frontend: tela "Meu perfil" (ou local equivalente a definir), fora do fluxo de
  onboarding forçado da Fase 1.
- Auditoria via `record_audit_log` (`backend/app/services/audit_log.py`, já existe) —
  ex. `action="user.password_changed"`, `entity="user"` — nunca com a senha, nem hash,
  em `before_data`/`after_data`.

## 4. Fase 2B — Reset administrativo e forçar primeiro acesso

**Contexto**: `must_change_password` já existe no banco desde a Fase 1, mas não há
nenhuma tela nem endpoint para um admin acioná-lo manualmente.

**Escopo**:

- Endpoint autenticado, protegido pela mesma permissão de `create_user`/`update_user`
  (`users:manage`), que permite a um admin, para um usuário existente:
  - forçar `must_change_password = true` — o usuário volta a cair no fluxo de
    onboarding/troca obrigatória no próximo login, reaproveitando 100% o gate já
    existente da Fase 1 (`require_portal_access` / `portal_first_access_pending` em
    `core/security.py`) — nenhuma lógica de bloqueio nova é necessária, só a ação de
    ligar a flag;
  - opcionalmente, definir uma senha temporária — preferir geração aleatória pelo
    backend a digitação manual pelo admin; a senha temporária nunca deve ser retornada
    em texto puro fora do canal previsto nem persistida em log;
  - opcionalmente, zerar `first_access_completed_at`, quando o objetivo for reabrir a
    confirmação de CPF/contato e não só a senha — tratar como uma ação distinta de
    "forçar troca de senha", com rótulo próprio, para não confundir o admin sobre o
    que cada botão faz.
- Frontend: ação nova dentro da tela de administração de usuários já existente
  (`/admin`, `backend/app/modules/admin/router.py`) — não deveria exigir tela nova, só
  ação nova numa tela existente.
- Auditoria obrigatória (ex. `action="user.password_reset_forced"` /
  `"user.first_access_reset"`, `entity="user"`) registrando autor, alvo e horário —
  nunca a senha temporária em si.

## 5. Fase 2C — Convite seguro com token

**Contexto**: hoje o único jeito de um colaborador ganhar acesso é um admin criar o
`User` diretamente com senha inicial escolhida por quem cria (`create_user`). Isso não
deveria acontecer — um admin nunca deveria conhecer ou escolher a senha real de outra
pessoa.

**Escopo**:

- Admin cria um convite informando e-mail, `collaborator_id` e papel/role — o vínculo
  é decidido aqui, pelo admin, respeitando o princípio da seção 2.
- Backend gera um token de convite de uso único e guarda só o HASH do token — nunca o
  token em claro — reaproveitando o mesmo algoritmo de `hash_password` já usado hoje
  em `hash_api_key` (`core/security.py`). Expiração curta (sugestão: 72 horas,
  configurável).
- O link de convite é entregue à pessoa convidada. Até existir canal de e-mail (ver
  risco na seção 12), o admin pode copiar o link e enviar por um canal já em uso hoje
  (WhatsApp, Slack) — sem nunca digitar ou conhecer a senha da pessoa.
- A pessoa convidada abre o link; o backend valida hash do token, expiração e status
  ainda pendente; a pessoa define a própria senha (nunca vê nem herda um valor
  escolhido por outra pessoa); a conta resultante nasce (ou é ativada) com o
  `collaborator_id` exatamente igual ao definido no convite.
- Decisão a registrar explicitamente na implementação: se o convite também resolve
  CPF/telefone (dispensando a Fase 1 depois) ou se apenas resolve a senha inicial e o
  onboarding da Fase 1 roda normalmente em seguida. Qualquer uma das duas é aceitável;
  o que não pode acontecer é ficar ambíguo.
- Convite expirado ou já usado nunca pode ser reaproveitado; convite deve ser
  revogável pelo admin antes do uso.
- Auditoria de criação, aceite, expiração e revogação (`entity="portal_invite"`).

### 5.1 Extensão — convite inteligente por CPF integrado ao IXC

Implementada em 2026-08-29, depois da Fase 2C original acima já estar em produção. Resolve
o maior atrito do convite manual: o admin precisava saber de cor o `collaborator_id` certo e
digitar o e-mail à mão, sem nenhuma confirmação de que estava vinculando a pessoa certa.

**Fonte confirmada**: tabela `funcionarios` do IXC (webservice v1, mesmo `IxcClient` já usado
pela Operação Analítica) é o cadastro de RH/técnico de campo — **não** `cliente` (assinante de
contrato, entidade completamente diferente). ~864 registros na instalação real. Campos usados:
`id`, `funcionario`, `cpf_cnpj`, `email`, `fone_celular`, `ativo`, `id_departamento`,
`id_setor_padrao`. Filtro `funcionarios.cpf_cnpj = <CPF>` confirmado contra a API real - devolve
exatamente 1 funcionário para um CPF válido. **Achado real em 2026-08-29** (só depois da entrega
original, um CPF de teste real não era encontrado): o campo guarda o CPF **com máscara**
(`702.401.102-50`), não só dígitos - a busca tenta esse formato primeiro
(`format_cpf_with_mask`, `services/documents.py`) e cai pra dígitos puros só como resguardo, sem
nunca combinar os dois numa única chamada `IN` (o webservice desta instalação rejeita `IN` com
valor contendo pontuação).

**Fluxo**: `POST /invites/lookup-ixc-cpf` (admin, `users:manage`) recebe o CPF no corpo (nunca
na URL), valida o formato (`is_valid_cpf`, mesma função da Fase 1), consulta o IXC e devolve
nome/e-mail/telefone/status + `cpf_masked` — nunca o CPF completo. Tenta uma correspondência
local por `ixc_employee_id` → CPF → nome normalizado, nessa ordem de força (mesmo princípio de
"sugestão, nunca vínculo automático" da seção 2) - o resultado é só informativo, o admin sempre
confirma explicitamente o `collaborator_id` no passo seguinte. `POST /invites/from-ixc`
revalida o CPF contra o IXC de novo (nunca confia em dado ecoado pelo cliente), enriquece o
`Collaborator` (preenche `ixc_employee_id`/CPF/e-mail/telefone só quando estão vazios - nunca
sobrescreve um valor já cadastrado; diverge com o que já existe → bloqueia com 409, mesmo
princípio de "confirma, nunca sobrescreve" da Fase 1) e então chama `create_invite` (Fase 2C
original, sem duplicar a lógica de token).

**Sem `Collaborator` local correspondente**: o sistema NÃO cria um cadastro novo sozinho -
`role`/`regional` (campos obrigatórios do modelo) não vêm do IXC nesta busca, e inventar um
valor placeholder poluiria uma entidade usada por outros módulos (Gamificação, Operação
Analítica). Retorna a busca normalmente (nome/e-mail continuam úteis pro admin ver), mas exige
cadastro manual do colaborador antes de conseguir convidar.

**Segurança crítica corrigida junto**: `IxcClient.list` (`services/ixc_client.py`) logava o
valor bruto de qualquer filtro em nível INFO - inofensivo até então (só id/data/status), mas um
vazamento sério assim que passou a existir busca por `funcionarios.cpf_cnpj`. Corrigido para
mascarar CPF/CNPJ (`mask_document`, mesmo de `services/documents.py`), e-mail e telefone antes
de logar, preservando os logs úteis de tabela/página/rp/total/duração inalterados.

Auditoria própria (`entity="ixc_collaborator"`): toda consulta ao IXC é registrada (achada, não
achada, ambígua ou erro), sempre com CPF mascarado, commitada mesmo quando a consulta termina em
erro (a auditoria da tentativa não pode se perder). Enriquecimento do `Collaborator` audita
separadamente (`entity="collaborators"`, `action="collaborator.enriched_from_ixc"`) só quando
algo de fato muda.

## 6. Fase 2D — Solicitação de acesso

**Contexto**: hoje, se alguém não tem conta e não recebeu convite, não existe canal
formal — depende de pedido informal chegando até algum admin por fora do sistema.

**Escopo**:

- Tela pública, não autenticada, fora do Portal logado, onde a pessoa informa nome,
  CPF, telefone e e-mail — os mesmos dados que a Fase 1 já valida
  (`is_valid_cpf`/`normalize_document` em `services/documents.py`), reaproveitando a
  validação existente em vez de recriá-la.
- O backend registra a solicitação — nunca cria `User` nem `collaborator_id` sozinho —
  e PODE tentar uma correspondência automática contra `Collaborator` existente (por
  CPF, quando o campo já estiver preenchido no cadastro). O resultado dessa
  correspondência é sempre uma SUGESTÃO anexada à solicitação, nunca um vínculo
  automático (princípio da seção 2, sem exceção).
- Fila de aprovação para admin: aprovar (o que deve gerar um convite, reaproveitando a
  Fase 2C, nunca duplicando o mecanismo de criação de conta) ou rejeitar com motivo
  registrado.
- Rota pública e não autenticada: rate limiting é obrigatório (ver
  `docs/manual_programacao_senior.md` seção 6 e `AGENTS.md`) — sem isso, a rota vira
  superfície de enumeração de CPF ou de spam da fila de aprovação.
- Auditoria da criação da solicitação e da decisão do admin
  (`entity="portal_access_request"`).

## 7. Fase 2E — Esqueci minha senha

**Contexto**: hoje não existe nenhum jeito de recuperar acesso perdido sem um admin
intervir manualmente — o que, por sua vez, só passa a ser possível depois de existir a
Fase 2B.

**Escopo**:

- Tela pública "Esqueci minha senha": a pessoa informa o e-mail.
- O backend SEMPRE responde com a mesma mensagem genérica, exista ou não o e-mail
  cadastrado — evita enumeração de contas, é requisito de segurança, não só de UX.
- Quando o e-mail existe, o backend gera um token de reset de uso único (mesmo
  mecanismo de hash + expiração curta da Fase 2C — ver modelo de dados compartilhado
  na seção 8) e o entrega por e-mail (mesma dependência de canal de envio da seção 12).
- A pessoa abre o link, define a nova senha, o token é invalidado após o uso (ou ao
  expirar), e `password_changed_at` é atualizado.
- O reset de senha, por si só, NÃO deve forçar um novo primeiro acesso
  (`first_access_completed_at` permanece inalterado) — é recuperação de senha, não
  reconfirmação de identidade.
- Auditoria da solicitação de reset e da conclusão — nunca com o token em claro nem
  com a senha.

## 8. Modelo de dados sugerido

Duas tabelas novas cobrem as três sub-fases que precisam de persistência própria
(2C, 2D, 2E). Convite (2C) e esqueci-minha-senha (2E) reaproveitam o mesmo mecanismo de
token — mesma expiração, mesmo uso único, mesmo hash — para não duplicar lógica
(`AGENTS.md`: "Não duplique componentes ou lógica").

### `account_action_tokens` — convite (2C) e reset de senha (2E)

| Campo | Tipo | Observação |
|---|---|---|
| `id` | int, PK | |
| `purpose` | enum (`invite`, `password_reset`) | distingue os dois usos do mesmo mecanismo |
| `user_id` | FK `users.id`, nullable | sempre preenchido em `password_reset`; em `invite`, só quando já existe um `User` pré-criado sem senha |
| `email` | string | destino do convite antes de existir `User` (2C) |
| `collaborator_id` | FK `collaborators.id`, nullable | só em `purpose="invite"` — é aqui que o admin fixa o vínculo, nunca a pessoa convidada |
| `role` | string, nullable | só em `purpose="invite"` |
| `token_hash` | string | hash do token (mesmo algoritmo de `hash_password`/`hash_api_key`), nunca o token em claro |
| `status` | enum (`pending`, `accepted`, `expired`, `revoked`) | |
| `created_by_user_id` | FK `users.id`, nullable | admin que criou o convite; nulo em reset autoatendido |
| `expires_at` | datetime | |
| `accepted_at` | datetime, nullable | |
| `created_at` | datetime | |

### `portal_access_requests` — solicitação de acesso (2D)

| Campo | Tipo | Observação |
|---|---|---|
| `id` | int, PK | |
| `name` | string | |
| `cpf` | string | mesmo tratamento de `Collaborator.cpf`/`services/documents.py` — normalizado, nunca exibido completo fora do backend |
| `phone` | string | |
| `email` | string | |
| `suggested_collaborator_id` | FK `collaborators.id`, nullable | resultado da correspondência automática — só sugestão |
| `status` | enum (`pending`, `approved`, `rejected`) | |
| `reviewed_by_user_id` | FK `users.id`, nullable | |
| `reviewed_at` | datetime, nullable | |
| `decision_reason` | string, nullable | |
| `created_at` | datetime | |

Ambas as tabelas exigem migration própria no momento em que forem implementadas —
nenhuma migration é criada nesta entrega, só o desenho.

## 9. Regras de segurança (valem para todas as sub-fases)

- CPF nunca aparece completo fora do backend — reaproveitar `mask_document`,
  `is_valid_cpf` e `normalize_document` de `backend/app/services/documents.py` (já
  existem; não recriar).
- Todo token (convite, reset de senha) é armazenado só como hash — nunca em claro no
  banco, nunca em log. Reaproveitar o mesmo algoritmo de `hash_password`
  (`core/security.py`), do mesmo jeito que `hash_api_key` já faz hoje.
- Todo token tem expiração curta e é de uso único; token expirado ou já usado é sempre
  rejeitado, nunca "quase aceito".
- Toda ação sensível (convite criado/aceito, reset forçado, solicitação
  aprovada/rejeitada, senha trocada) grava `AuditLog` via `record_audit_log`
  (`backend/app/services/audit_log.py`, já existe) — nunca com senha ou CPF completo em
  `before_data`/`after_data`, mesmo padrão já testado em
  `test_audit_log_never_stores_full_cpf_or_password` na Fase 1.
- Toda validação crítica (força de senha, unicidade de e-mail, formato de CPF,
  expiração de token, permissão de quem aprova/reseta) ocorre no backend — o frontend
  só dá feedback imediato, nunca decide.
- Rotas públicas não autenticadas (solicitação de acesso, esqueci minha senha) exigem
  rate limiting e resposta genérica que não revele se um e-mail ou CPF já existe no
  sistema.
- Nenhuma senha, token em claro ou CPF completo pode aparecer em log, em resposta de
  erro ou em mensagem de e-mail além do link de ação em si.

## 10. Ordem recomendada de implementação

1. **2A — troca de senha pelo próprio usuário.** Menor risco, nenhuma tabela nova,
   reaproveita 100% do que a Fase 1 já criou (`verify_password`, `hash_password`,
   `password_changed_at`). Prepara a tela "Meu perfil" que a 2B também vai usar.
2. **2B — reset administrativo e forçar primeiro acesso.** Também sem tabela nova, só
   endpoint e ação na tela de admin já existente. Resolve a pendência já registrada
   duas vezes em `docs/STATUS.md`.
3. **2C — convite seguro com token.** Primeira sub-fase que precisa de tabela nova e
   migration. Só faz sentido depois de 2A/2B validarem o padrão de troca de senha que
   a pessoa convidada vai usar para definir a senha inicial.
4. **2D — solicitação de acesso.** Depende de 2C já existir, porque aprovar uma
   solicitação deve gerar um convite, não duplicar a lógica de criação de conta.
5. **2E — esqueci minha senha.** Reaproveita a mesma tabela de token da 2C; fica por
   último porque o mecanismo de token e o fluxo de "definir nova senha a partir de um
   link" já terão sido validados em produção pela 2C.

Cada sub-fase é uma tarefa independente e pequena — nenhuma exige refazer a anterior.

## 11. Critérios de aceite por fase

**2A**: usuário autenticado troca a própria senha informando a senha atual; senha
atual incorreta é rejeitada; nova senha segue a política mínima; login subsequente usa
a senha nova; `password_changed_at` atualizado; `must_change_password` e
`first_access_completed_at` permanecem inalterados; auditoria sem a senha em nenhuma
forma; typecheck, testes e build limpos.

**2B**: admin com `users:manage` força `must_change_password=true` num usuário-alvo;
o usuário afetado cai no onboarding no próximo login, reaproveitando o gate da Fase 1
sem lógica nova de bloqueio; usuário sem a permissão recebe 403; ação registrada em
auditoria com autor e alvo; nenhuma senha temporária aparece em log ou em resposta em
texto puro fora do canal previsto.

**2C**: admin cria convite com e-mail e `collaborator_id`; o token só existe como hash
no banco; o link de convite expira no prazo definido; a pessoa convidada define a
própria senha, nunca uma escolhida por outra pessoa; token usado ou expirado não pode
ser reaproveitado; a conta resultante tem o `collaborator_id` exatamente igual ao
definido pelo admin no convite; auditoria de criação e aceite registrada.

**2D**: pessoa sem conta registra solicitação com CPF válido (mesma validação da
Fase 1); a correspondência automática, quando existir, aparece só como sugestão para o
admin; a aprovação gera um convite (2C), nunca cria `User`/vínculo diretamente;
rejeição registra motivo; a rota pública tem rate limiting; a resposta não revela se o
CPF/e-mail já existe no sistema.

**2E**: usuário sem acesso solicita reset por e-mail; resposta idêntica exista ou não
o e-mail (sem enumeração); token expira e é de uso único; a nova senha definida
permite login imediato; `first_access_completed_at` não é afetado; auditoria da
solicitação e da conclusão sem token em claro nem senha.

## 12. Riscos e mitigação

- **Não existe infraestrutura de envio de e-mail no projeto hoje** (verificado:
  nenhuma integração de SMTP ou serviço de e-mail em `backend/app`). Isso bloqueia a
  entrega automática do link de convite (2C) e de reset de senha (2E). Mitigação:
  tratar a criação de um serviço mínimo de envio (ou webhook para um canal já
  existente) como pré-requisito de infraestrutura antes de 2C/2E entrarem em
  implementação — ou, como paliativo explícito e temporário, o admin copia o link
  gerado e envia manualmente por um canal já em uso (WhatsApp, Slack), documentando
  que essa etapa é transitória.
- **Enumeração de contas ou de CPF** nas rotas públicas (2D, 2E), caso as respostas
  diferenciem "existe" de "não existe". Mitigação: resposta sempre genérica, timing de
  resposta consistente quando viável, rate limiting.
- **Convite ou reset usado por outra pessoa que não a destinatária**, caso o link
  vaze (e-mail comprometido, encaminhamento indevido). Mitigação: expiração curta,
  token de uso único, revogação manual disponível para o admin e — melhoria futura,
  fora do escopo desta fase — uma confirmação adicional (ex.: últimos dígitos do CPF)
  antes de liberar a troca de senha pelo link.
- **Correspondência automática de CPF (2D) sugerindo o `collaborator_id` errado**,
  por dado desatualizado em `Collaborator.cpf`. Mitigação: tratar sempre como
  sugestão visível ao admin, nunca como vínculo automático — princípio da seção 2, sem
  exceção nesta fase.
- **Admin definindo senha temporária fraca ou previsível (2B)**, se a implementação
  permitir digitar a senha em vez de gerar. Mitigação: preferir geração aleatória pelo
  backend; se permitir digitação, aplicar a mesma política mínima da Fase 1.
- **Ambiguidade entre "forçar troca de senha" e "forçar primeiro acesso completo" em
  2B**, confundindo o admin sobre o efeito de cada ação. Mitigação: nomear e
  documentar as duas ações separadamente na tela, nunca como uma ação única ambígua.
- **Duplicar o mecanismo de token entre 2C e 2E**, caso sejam implementadas em
  momentos diferentes sem reler este documento. Mitigação: este documento já define a
  tabela compartilhada (`account_action_tokens`, seção 8) como modelo sugerido — a
  implementação da 2E DEVE reaproveitar essa tabela, não recriar o mecanismo.

---

Nenhuma implementação de código, migration, dado real, commit ou push ocorreu na
produção deste documento.
