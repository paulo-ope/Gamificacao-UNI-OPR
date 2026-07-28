# Plano técnico — Substituir importação por planilha UpValue por integração direta com a API do IXC

Status: log de auditoria de requisições ao IXC + cache de tabelas de apoio · Autor: Claude (Cowork) · Data: 2026-07-17

## 0.17 Log de auditoria de requisições ao IXC + cache de tabelas de apoio (reduz carga)

O dono do produto pediu comprovação concreta de que a integração não está sobrecarregando o IXC.
Não existia nenhum log de requisição individual até então - `IxcClient.list()` (`ixc_client.py`)
só propagava erros, nunca registrava o que era enviado com sucesso.

**Log de auditoria adicionado**: todo `IxcClient.list()` agora loga (nível INFO, logger `ixc_client`)
tabela, página, tamanho de página, filtros, registros recebidos, total no filtro e duração em ms -
tanto em sucesso quanto em falha. Isso dá rastro concreto de cada requisição, sem custo (é só log,
não afeta o comportamento).

**Medição real feita com esse log**: um ciclo de sincronização incremental típico (`sync_ixc_service_orders`,
o mesmo que roda automaticamente a cada `ixc_sync_interval_minutes`) fazia **18 requisições HTTP**, das
quais **15 eram para recarregar por INTEIRO as tabelas de apoio** (`su_oss_assunto`, `su_diagnostico`,
`funcionarios`, `empresa_setor` - juntas, ~1.266 registros), mesmo quando só havia 1 O.S nova a
processar. Essas tabelas mudam raramente (um funcionário novo, um assunto novo cadastrado no IXC -
não a cada poucos minutos).

**Corrigido**: `build_lookup_cache` (`ixc_importer.py`) agora cacheia essas 4 tabelas em memória do
processo por até `_LOOKUP_TABLES_CACHE_TTL_SECONDS` (1 hora), em vez de rebuscar tudo a cada
importação. Seguro sem lock próprio porque toda importação (backfill manual ou sync periódica) já
roda dentro de `_ixc_import_lock` (lock consultivo do Postgres) - nunca há duas escritas concorrentes
nessa variável de módulo. Os dicionários são compartilhados (não copiados) entre chamadas porque nada
os modifica depois de montados (só leitura durante o mapeamento das O.S).

**Validado ao vivo**: rodando `sync_ixc_service_orders` duas vezes seguidas no mesmo processo, a
segunda chamada fez só 3 requisições (a busca de O.S novas + 2 lookups pontuais de cliente/login já
necessários por O.S encontrada) - as 15 requisições de tabelas de apoio foram completamente
eliminadas, reaproveitando o cache da primeira chamada.

## 0.16 Período "encerrado" agora é definido pelo mês corrente (fuso de Porto Velho), não só por "pago"

Contexto: no achado 0.15, vimos que a reincidência olha até 30 dias pra frente, e que isso deixava o
rascunho de um mês recém-fechado instável até alguém lembrar de marcar como pago. O dono do produto
trouxe um cenário concreto: se o fechamento de um mês só é marcado como "pago" no dia 5 do mês seguinte
(por processo administrativo), qualquer reincidência descoberta entre a virada do mês e esse dia 5 ainda
mudava o total do mês anterior - o que ele considera inaceitável. Pedido: assim que o mês virar, o total
já deveria estar congelado, e qualquer reincidência encontrada depois disso deveria cair no saldo de
pontos do próximo fechamento, informando o motivo - igual ao mecanismo `detect_post_payment_warranty_debits`
que já existia, só que até então só disparava para período **pago**, não para período **encerrado por
calendário mas ainda em rascunho**.

**Implementado**:
- `calculation_closure.py`: novo `PORTO_VELHO_TZ`/`now_porto_velho()`/`current_reference_period()`/
  `is_period_in_the_past()` - toda decisão de "qual é o mês corrente" no sistema passa a usar o fuso de
  Rondônia (`America/Porto_Velho`, sem horário de verão), não o relógio UTC do container. Isso importa
  porque o próprio IXC grava as datas de O.S em horário local (achado da seção 6) - usar UTC pra decidir
  a virada do mês erraria a fronteira em até 4h.
- `ensure_period_not_paid` renomeado para `ensure_period_not_closed`: além de bloquear um período já
  pago (comportamento antigo, preservado), agora também bloqueia recalcular um período cujo mês/ano já
  não é mais o corrente - mesmo que ainda esteja em rascunho. Em ambos os casos, uma revisão explícita
  (`create_revision`, o mesmo campo que a tela já usava pra período pago) passa por cima da trava.
- `point_balance.detect_post_payment_warranty_debits`: o gatilho para lançar um débito no saldo de
  pontos (em vez de deixar o `recurrence_penalties` normal mexer no rascunho do período original) agora
  é "período pago OU mês já virou" - não só "período pago". Quando não há fechamento pago pra referenciar
  (mês fechou mas ninguém pagou ainda), usa a apuração mais recente daquele período (`find_run_for_period`,
  novo, sem filtro de status) só para herdar a régua congelada e compor o motivo do lançamento; se nunca
  houve nenhuma apuração daquele mês, cai no fallback de régua atual (mesmo comportamento que já existia
  para fechamento pago sem `config_snapshot`).
- `ixc_scheduler._recalculate_current_period`: passou a usar `now_porto_velho()` em vez de
  `datetime.now(timezone.utc)` pra decidir qual mês é o "corrente" a recalcular automaticamente.
- Frontend (`app/gamificacao/page.tsx`): os botões "Recalcular pontuação" e "Recalcular período" tentam
  primeiro sem revisão; se o backend recusar (409, período pago OU encerrado por calendário), perguntam
  ao usuário se quer criar uma revisão em rascunho, reaproveitando o mesmo fluxo que já existia só para
  período pago. Corrigido em conjunto um bug pré-existente em `lib/api.ts` (`requestRaw`/`requestBlob`/
  upload): o `throw` de erro ficava dentro do mesmo `try` que fazia o parse do JSON, então era sempre
  capturado pelo próprio `catch` e mostrava o corpo cru (`{"detail":"..."}`) em vez do texto extraído -
  apareceu ao vivo na primeira tentativa de testar o novo diálogo de confirmação.

**Testes**: 1 teste em `test_calculation_closure.py` tinha mês/ano fixos (06/2026) presumindo implicitamente
que seria sempre "o mês corrente" - ajustado para passar `create_revision: true`, já que o foco daquele
teste é proteção contra pagamento duplicado, não a trava de período passado. Suíte completa (17 testes)
verde após o ajuste.

## 0.15 Divergência de valor entre extrato da planilha (pago) e extrato do IXC (rascunho) — causa raiz e correção

O dono do produto comparou dois extratos de pagamento do mesmo colaborador (THIAGO MATHEUS RODRIGUES
NASCIMENTO, Junho/2026) — um gerado com a planilha UpValue (pago, 94 O.S., 1.368,0 pts brutos, R$ 528,22) e
outro com o IXC integrado (rascunho, 90 O.S., 1.312,0 pts brutos, R$ 514,08) — e pediu pra identificar por
que os valores diferiam.

**Achado 1 — 4 O.S. ausentes do lado IXC (56 pts de bruto).** As O.S. `1161967`, `1162223`, `1162483`,
`1162273` abriram no fim de maio/2026 (30-31/05) e só fecharam em 01/06. Confirmado direto na API do IXC
que o setor (8/9, dentro do filtro técnico) e o status (`F`, finalizada) estavam corretos — não foram
excluídas por nenhum filtro de conteúdo. A causa real: `backfill_ixc_service_orders` (via
`fetch_service_orders`) filtrava por **data de abertura** (`data_abertura`) dentro do mês pedido. Como a
apuração agrupa O.S. pelo mês em que **fecharam** (`period_orders` em `scoring_detail.py`), qualquer O.S.
aberta no fim de um mês e fechada no início do seguinte nunca era buscada por nenhum dos dois backfills
mensais (nem o do mês de abertura, porque o filtro de abertura pegaria ela mas ela pertence ao período de
fechamento seguinte; nem o do mês de fechamento, porque o filtro olhava só pra abertura).

**Correção aplicada**: adicionados `closed_after`/`closed_before` (filtro por `su_oss_chamado.data_fechamento`)
em `fetch_service_orders` (`ixc_client.py`) e `import_ixc_service_orders`/`_import_ixc_service_orders_body`
(`ixc_importer.py`); `backfill_ixc_service_orders` agora usa esses filtros em vez de `opened_after`/
`opened_before` pra decidir o que pertence ao mês pedido — consistente com o critério real de apuração.
Re-rodado backfill de maio/2026 (9.395 O.S. novas) e re-rodado backfill de junho/2026 com o filtro corrigido
(366 O.S. novas, incluindo as 4 que faltavam). Após recálculo, os pontos brutos de Thiago em Junho/2026
bateram **exatamente** com o extrato pago da planilha: 1.368,0 pts.

**Achado 2 — bug real e isolado: coluna SLA em branco no PDF do extrato.** `statement_pdf.py` lia
`order["sla_status"]` (campo cru do IXC, sempre vazio pra O.S. importadas via IXC) em vez de
`order["sla_status_normalized"]` (o fallback por horas já corrigido em `scoring_detail.py` pra tela de
auditoria, mas que não tinha sido propagado pro gerador de PDF). Corrigido trocando a chave usada.

**Diferença que sobra (esperada, não é bug)**: mesmo com os pontos brutos batendo, "Pontos anulados"
(reincidência) ficou em -88 pts no IXC (recálculo com dado completo) contra -62 pts no extrato antigo da
planilha — o motor de reincidência encontrou 8 pares dentro do próprio mês de junho somando 88 pts, contra
o que a planilha (curada manualmente) tinha identificado. Sem o dado granular da apuração antiga (apagada
do banco a pedido do dono do produto, junto com o resto do histórico não-IXC), não dá pra reconstruir por
que a planilha achou menos pares — mas o mecanismo é o mesmo, só o dado de entrada mudou. Além disso, a
seção "Desconto de garantia" (que na planilha descontava -58 pts de um fechamento **já pago** de maio) não
aparece no lado IXC porque **nenhum período está marcado como pago no sistema novo ainda** (esse mecanismo
só dispara contra um período já pago) — não é bug, é consequência de o histórico pago ainda não existir
no IXC. O extrato recalculado ficou em R$ 537,60 (contra R$ 528,22 da planilha) — a diferença de R$ 9,38
se explica inteiramente por essas duas forças (penalidade de reincidência maior, garantia ausente),
que devem convergir conforme mais meses forem migrados e formalmente pagos no sistema novo.

## 0.14 SLA/saúde regional não deve contar O.S de colaborador não cadastrado

O dono do produto trouxe um caso real: um colaborador do back office às vezes fecha uma O.S externa sem
o técnico de campo ter feito o atendimento (confirmado: nesses casos, o técnico "por algum motivo não
precisou realizar o serviço" - não é perda de crédito, é ausência real de trabalho técnico). Tentei
resolver filtrando por departamento do funcionário no IXC, mas **os dados de departamento são praticamente
inexistentes** (de 842 funcionários, só 4 têm "Departamento Operacional Externo" marcado - filtrar por
isso zeraria a pontuação de quase todo mundo). Abordagem descartada.

**Pedido reformulado, mais preciso**: o SLA/saúde da regional não deveria ser influenciado por O.S de
colaboradores **não cadastrados** (`Collaborator.is_registered = false`) - o mesmo status que já existe
para qualquer nome auto-criado pela importação (`get_or_create_collaborator`, tanto via IXC quanto via
planilha) que nunca foi formalmente registrado como participante da gamificação. Esse conceito já existia
no sistema, só não era usado nessa conta.

**Corrigido**: `calculate_regional_health()`/`calculate_regional_health_from_details()`
(`scoring_detail.py`) agora ignoram O.S cujo colaborador não está cadastrado, tanto no cálculo direto
(sobre `ServiceOrder`) quanto no recálculo em cima dos detalhes já processados (adicionado
`collaborator_is_registered` ao dicionário de detalhe). Não muda a pontuação individual de ninguém - só
o cálculo agregado de SLA/saúde por regional, que afeta o multiplicador aplicado a todos os colaboradores
cadastrados daquela regional.

**Validado com dado real**: encontrados vários colaboradores não cadastrados com volume alto de O.S (ex.:
145 O.S de uma pessoa em Ouro Preto do Oeste - não é caso isolado, várias regionais têm isso). Comparação
antes/depois pra Ouro Preto do Oeste: 1.166 O.S/79,33% de SLA (antes) → 946 O.S/81,08% de SLA (depois).

**Pendente, registrado à parte**: o dono do produto também pediu uma ferramenta de filtro dinâmico
(regional, departamento, assunto, diagnóstico, colaborador) parecida com Power BI - é uma funcionalidade
maior de análise/dashboard, não uma correção pontual. Fica para discussão/planejamento futuro, fora do
escopo desta integração.

## 0.13 Extrato de auditoria mostrava "SLA não identificado" contradizendo o próprio texto ao lado

O dono do produto trouxe o extrato da O.S `IXC-1245969` (reincidência funcionando corretamente) e pediu
melhorias. Achado: o campo de destaque **"SLA normalizado"** mostrava sempre `NAO_IDENTIFICADO` para
qualquer O.S vinda do IXC - porque esse campo só lê o texto `order.sla_status`, que é **sempre vazio**
nessas O.S (decisão de projeto, seção 6). Só que, logo abaixo, o texto explicativo dizia
**"SLA fora do prazo configurado sem penalidade"** - vindo de um cálculo **diferente e correto**, que usa
horas (`sla_hours`/`closing_time_hours`, a meta do assunto vs. tempo real de fechamento) e é o que
realmente decide a penalidade. Ou seja, o extrato contradizia a si mesmo: um campo dizia "não sei", o
texto ao lado já tinha identificado "fora do prazo".

**Correção**: nova função `sla_display_label()` (`scoring_detail.py`) - usa o texto se disponível, e cai
pro mesmo cálculo por horas que `sla_inside()` já usa pra decidir a penalidade, em vez de ficar preso no
texto vazio. Aplicada nos dois lugares que tinham essa duplicação (o campo de exibição no extrato e o
filtro de busca por SLA na lista de auditoria, que também estava quebrado do mesmo jeito para O.S do IXC).
Também corrigido o rótulo "SLA original **da planilha**" para "SLA original **importado**" (não fazia mais
sentido mencionar planilha para dado vindo da API). Nenhuma regra de pontuação/penalidade foi alterada -
só a exibição passou a refletir o que o sistema já calculava internamente.

Validado com a mesma O.S reportada: `sla_status_normalized` agora mostra `FORA_DO_PRAZO`, consistente com
o texto "SLA fora do prazo configurado sem penalidade".

## 0.12 Mudança de comportamento: só importar O.S finalizadas

Motivo: uma O.S "Em andamento" pode trocar de colaborador (`id_tecnico`) até fechar no IXC. Importar
enquanto ainda em andamento significava que, por um tempo, ela aparecia associada a um colaborador que
podia não ser o responsável final (o sistema se autocorrigia no fechamento via sincronização, mas a
janela de ambiguidade existia). Decisão do dono do produto: só trazer a O.S para dentro do sistema quando
já estiver finalizada no IXC.

**Implementado:**
- `fetch_service_orders(..., only_finalized=True)` (`ixc_client.py`) - filtra na origem por
  `su_oss_chamado.status = 'F'`, aplicado por padrão em `import_ixc_service_orders`.
- Trava defensiva em `build_service_order_payload_from_ixc`: rejeita (`ImportRowValidationError`) qualquer
  registro sem `data_fechamento` preenchida, mesmo que o filtro de status tenha deixado passar por algum
  motivo - nunca cria uma O.S "Concluída" sem data de fechamento real.
- **Consequência para o "Total de O.S" do período**: agora reflete só trabalho já concluído, não mais
  O.S em andamento (era essa a intenção - ver seção anterior sobre a diferença entre "Total de O.S" e
  "O.S na base").

**Limpeza feita**: apagadas 651 O.S "Em andamento" que já tinham sido importadas sob a regra antiga (sem
dependências em `point_balance_entries` - seguro remover). Confirmado com dado real: uma busca na API
filtrada retorna só `status='F'`.

## 0.11 Revisão de código: achados e correções

Pedido do dono do produto: revisão completa procurando falhas que não existiam com a planilha (manual, uma
pessoa por vez) e que poderiam existir com importação automática/contínua. Achados por gravidade, os 2
primeiros corrigidos e validados:

**1. [Corrigido] Colaborador duplicado por corrida de concorrência.** `Collaborator.name` não tem
restrição de unicidade. Sincronização automática e backfill manual rodando ao mesmo tempo podiam cada um
criar um `Collaborator` novo pro mesmo nome, dividindo o histórico de pontuação dessa pessoa em dois IDs -
sem erro nenhum. **Correção**: lock consultivo do Postgres (`pg_try_advisory_lock`,
`_ixc_import_lock`/`IXC_IMPORT_LOCK_KEY` em `ixc_importer.py`) serializa qualquer importação do IXC -
`import_ixc_service_orders` (usado por sincronização e backfill) espera até 60s pela vez, e lança
`IxcImportLockTimeoutError` (HTTP 409) se não conseguir. Testado com duas importações reais rodando ao
mesmo tempo pro mesmo intervalo: as duas terminaram sem erro, uma esperou a outra.

**2. [Corrigido] Nenhum alerta quando a sincronização para de funcionar.** Falhas só eram logadas
localmente - ninguém seria avisado (já vivemos isso: julho ficou 5 mil O.S. atrasado sem ninguém notar até
comparar manualmente). **Correção**: `ixc_scheduler.py` grava estado de saúde em `AppSetting`
(`ixc_sync_last_success_at`, `ixc_sync_last_error`, `ixc_sync_consecutive_failures`), exposto via
`GET /imports/ixc-sync-status`. Não existe infra de e-mail/webhook neste projeto para alertar ativamente -
isso fica disponível pra checagem manual ou, futuramente, virar um indicador visual na tela de Período.

**3. [Não corrigido, registrado]** `KNOWN_OS_TYPE_BY_SUBJECT`/`IXC_TECHNICAL_SETOR_IDS` são fotografias
fixas da configuração da produção - vão ficar desatualizadas silenciosamente se o IXC criar um assunto ou
setor genuinamente novo. Sem solução aplicada ainda; precisaria de um jeito de detectar "assunto novo, não
reconhecido" e sinalizar (não é óbvio como fazer isso sem falsos positivos toda vez que aparece um assunto
administrativo fora do escopo).

**4-8. [Não corrigidos, menor prioridade]**: recarga completa das tabelas de apoio a cada ciclo (ineficiente,
não incorreto); erro de parsing de resposta não vem claro no log; falha de rede no meio de uma paginação
grande descarta o lote inteiro; `has_pending` sempre `False`; `is_priority` não recalcula em atualização
(quirk pré-existente do importador UpValue, não introduzido por esta integração).

## 0.10 Regressão séria: `os_type` voltou a quebrar, derrubando a reincidência

O dono do produto notou que nenhuma O.S. estava gerando reincidência. Investigando: a correção de `os_type`
da seção 0.5 dependia de **aprender com o histórico da planilha** (`load_historical_os_type_mapping`, só
olhava O.S. com `os_code NOT LIKE 'IXC-%'`). Quando limpamos "todos os períodos" (seção 0.6, a pedido do
dono do produto), apagamos justamente essas ~35 mil O.S. da planilha - a única fonte desse aprendizado.
Sem isso, toda importação desde então (incluindo os backfills de junho/julho, seção 0.9) voltou
silenciosamente a usar `setor` (errado) como `os_type`. As regras de reincidência
(`recurrence_classification_rules`) exigem `os_type` = "Manutenção"/"Ativação"/etc. exatamente - com
`os_type` = "Suporte Externo Fibra" (nome de departamento), nunca bateu com nenhuma regra.

**Correção definitiva:** substituí o aprendizado dinâmico por um mapa fixo no código
(`KNOWN_OS_TYPE_BY_SUBJECT` em `ixc_importer.py`), gravado permanentemente a partir do documento oficial
de produção - não depende mais de nenhum dado que possa ser apagado no futuro. `load_historical_os_type_mapping`
continua existindo só como fallback secundário.

**Erro de transcrição encontrado e corrigido durante essa correção:** ao montar esse mapa fixo na seção
0.8, usei por engano o **grupo de pontuação** (ex. "Manutencao Urbana Simples") em vez da **categoria**
real (o cabeçalho de seção do documento, ex. "Informação"/"Outros") para 3 assuntos - `Viabilidade`
(correto: `Informação`, não `Manutenção`), `Instalação Evento/Permuta Fibra Rural` e
`Retorno de Instalação Evento/Permuta Fibra Urbana` (correto: `Outros`, não `Ativação`). Validei as 41
entradas do mapa contra as regras que já existiam originalmente na produção (antes de qualquer mudança
minha) - zero divergências depois da correção.

**Também corrigido:** as 41 `ScoringSubjectRule` criadas na seção 0.8 tinham sido gravadas com a chave
errada (`os_type` = setor, não categoria) - algumas colidiam com regras que já existiam corretamente desde
antes. Apaguei as 41 e recriei a resolução via o mapa fixo; `os_type` de todas as ~15 mil O.S. já
importadas foi corrigido em lote.

**Validado com dado real**: o cliente `alessandra.subtil_UNI` (8 O.S. em ~1 mês, mesmo tipo de serviço
repetido) agora mostra 5 das 8 O.S. corretamente classificadas como `reincidencia_tecnica`
("Anulada por reincidência"). Taxa de pontuação com regra: 99,8% (15.207 de 15.236 O.S.).

**Lição registrada:** qualquer lógica que "aprende" de dado importado é frágil se esse dado puder ser
apagado depois (aconteceu aqui). Preferir mapas fixos/documentados no código para regras de negócio
estáveis, reservando o aprendizado dinâmico só pra casos onde não existe fonte de referência fixa.

## 0.9 Achado importante: sincronização incremental sozinha não cobre o mês corrente inteiro

O dono do produto notou que o mês 7 (julho) mostrava só 730 O.S. na gamificação (contagem real, via
`period_orders`), quando deveria ter muito mais. Comparando com a API do IXC direto: **5.575 O.S. reais**
existiam pra julho nos setores técnicos - só uma fração pequena tinha sido importada.

**Causa:** a sincronização automática (a cada 20 min) só pega O.S. cujo `ultima_atualizacao` está **depois**
da marca d'água - ou seja, só O.S. criadas ou alteradas recentemente. Uma O.S. aberta no início de julho e
que nunca mais mudou de status (ainda "Em andamento", sem nenhuma atualização) tem `ultima_atualizacao`
igual à data de abertura - assim que a marca d'água avança pra depois dessa data, essa O.S. nunca mais é
vista pela sincronização incremental. **Diferente de junho** (que foi explicitamente importado via
`backfill_ixc_service_orders`), **julho nunca tinha passado por uma importação retroativa** - só recebeu o
que a sincronização incremental pegou de tabela, o que deixa de fora exatamente esse tipo de O.S. "parada".

**Implicação para operação contínua:** isso não é só um problema do mês em que a integração começou -
é estrutural: **o mês corrente sempre vai ficar incompleto só com a sincronização incremental**, porque
sempre vai ter O.S. abertas recentemente que ainda não tiveram nenhuma atualização. Recomendação: rodar
`backfill_ixc_service_orders` para o mês corrente periodicamente (ex.: uma vez por semana, ou perto do
fechamento do período) além do polling automático, não só nos meses já fechados. Ainda não automatizado -
hoje é uma chamada manual/API (`POST /imports/ixc-backfill`).

**Corrigido**: rodei o backfill de julho/2026 (5.577 processadas, 5.401 criadas, 51 atualizadas, ~3,5min).
Contagem real do mês 7 agora: **6.134 O.S.** (era 730 antes).

## 0.8 Regras de pontuação restauradas no banco de dev (usando a tela "Assuntos não mapeados")

O dono do produto encontrou, pela própria tela de gestão do app (`unmapped-subjects-panel.tsx`,
`/scoring-matrix/unmapped-subjects`), assuntos sem regra vinculada. Isso é exatamente o achado da seção
0.5: o banco de **desenvolvimento** só tinha 51 regras (`scoring_subject_rules`), incompleto frente à
produção.

Cruzei as 44 combinações (tipo, assunto) sem regra com `REGRAS_CONFIGURADAS_GAMIFICACAO.md` (extração real
da produção, 2026-05-29) - **41 delas (9.785 de 9.822 O.S., 99,8%) já estavam documentadas** com grupo e
pontuação certos. Criei essas 41 `ScoringSubjectRule` no banco de dev usando exatamente essa configuração
documentada (mesmo grupo, `use_group_default=True`) - nenhuma pontuação nova inventada.

**Restam 3 combinações não documentadas** (18 O.S. no total, casos raros):
- `Suporte Externo` / `Reativação de Suspensão Temporária - Externo` (9 O.S.)
- `Suporte Externo Rádio` / `Instalação Evento/Permuta Rádio` (8 O.S.)
- `Suporte Externo Fibra` / `Retorno de Instalação Evento/Permuta Fibra Rural` (1 O.S.)

Essas ficam pendentes de decisão do dono do produto (grupo/pontuação) - dá pra resolver pela própria tela
"Assuntos não mapeados" quando ele decidir.

## 0.7 Filtro por setor: só trabalho técnico de campo

Decisão do dono do produto: a integração deve trazer só O.S. dos setores de campo, não administrativo/
comercial (que nunca pontuam mesmo, ver seção 0.5). Setores do IXC identificados via `empresa_setor`:
`7` = Suporte Externo, `8` = Suporte Externo Rádio, `9` = Suporte Externo Fibra.

Implementado como filtro **na origem** (na própria consulta à API do IXC, via `su_oss_chamado.setor IN
(7,8,9)`), aplicado automaticamente em `import_ixc_service_orders` (e por consequência em
`sync_ixc_service_orders` e `backfill_ixc_service_orders`, que chamam essa função por baixo) -
`IXC_TECHNICAL_SETOR_IDS` em `ixc_importer.py`. Não precisa ligar/desligar em nenhuma configuração -
é o comportamento padrão de tudo agora.

**Validado com dado real**: junho/2026 tem 36.077 O.S. no total, mas só **9.647** (27%) nos 3 setores
técnicos - reduz bastante o volume (e o tempo de importação retroativa junto). Confirmado que o filtro
aplicado no código retorna só registros com `setor` em `{7, 8, 9}`.

**Limpeza necessária:** o agendador automático rodou **sem** esse filtro por boa parte desta sessão (antes
do filtro existir), então já tinha importado O.S. administrativas/comerciais de vários meses. Rodei a
importação retroativa de junho/2026 com o filtro novo (9.647 processadas, 87 atualizadas, 0 criadas - a
maioria já tinha entrado via sincronização incremental antes do filtro). Depois, identifiquei e apaguei
**28.983 O.S.** que tinham entrado no banco de dev fora dos 3 setores técnicos (de todos os meses, não só
junho). Estado final do banco de dev: **9.783 O.S., todas** em `Suporte Externo`/`Suporte Externo Rádio`/
`Suporte Externo Fibra` - nada administrativo restante.

## 0.6 Banco de dev limpo (só IXC) + importação retroativa por mês

A pedido do dono do produto, o banco de **desenvolvimento** foi limpo por completo: apagados 35.601 O.S.
da planilha UpValue, 146 fechamentos (`CalculationRun`), 15.047 pontuações de colaborador, 506 lançamentos
de saldo, 2.352 resultados de bônus de liderança, 62 snapshots de projeção, 24 importações da planilha
(saldos de ponto zerados, não deletados). Ficaram só as ~2.561 O.S. já importadas via IXC. **Isso foi só
no ambiente de desenvolvimento, confirmado explicitamente antes de executar - produção não foi tocada.**

**Nova funcionalidade: importação retroativa por mês, sob demanda.**
- `backend/app/services/ixc_importer.py`: `backfill_ixc_service_orders(db, client, year, month, ...)` -
  importa um mês específico do passado direto da API do IXC, usando `opened_after`/`opened_before` (novo
  parâmetro em `fetch_service_orders`/`import_ixc_service_orders`). Uma vez importado, fica salvo em
  `service_orders` para sempre - a sincronização periódica (que só olha pra frente a partir da marca
  d'água) nunca mais precisa buscar essas O.S. antigas de novo.
- Rota nova: `POST /api/imports/ixc-backfill` (`{"year": 2026, "month": 6}`), mesma permissão
  `orders:import` da importação por planilha. Ainda sem UI no frontend - só a API por enquanto.

**Achado de performance real:** um mês inteiro tem ~36 mil O.S. (só junho/2026). O pipeline de importação
(compartilhado com o importador UpValue) faz várias consultas ao banco por O.S. processada
(`find_existing_service_order`, `get_or_create_collaborator`, auditoria por campo) - em lotes de dezenas de
milhares isso é lento. Primeira tentativa de importar o mês inteiro não terminou em 10+ minutos.

**Otimização aplicada (seguro, sem mudar nenhuma regra de negócio):** `get_or_create_collaborator`
(`upvalue_importer.py`) buscava **todos** os colaboradores do banco a cada O.S. processada. Adicionado um
parâmetro opcional `collaborators_cache` - quando informado, busca uma vez só por rodada de importação em
vez de uma vez por O.S. Comportamento idêntico, só mais rápido; quem chama sem esse parâmetro (o
importador UpValue) continua exatamente como estava, sem risco de regressão. Depois da otimização: 1639
O.S. de um dia em 42,8s - extrapolando, um mês inteiro (~36 mil) fica em torno de 15-16 minutos.

**Achado de concorrência (não resolvido, risco baixo):** rodar uma importação retroativa manual **ao
mesmo tempo** que a sincronização automática (a cada 20 min) pode gerar uma corrida - as duas tentam
processar a mesma O.S. concorrentemente, uma delas pode falhar com erro de chave duplicada
(`UniqueViolation` em `os_code`). Não corrigido (precisaria de lock/retry) porque é uma janela de
sobreposição rara e a falha é segura (a transação inteira faz rollback, sem corromper dado) - só precisa
rodar de novo. Vale ter em mente ao rodar backfills manuais: idealmente evitar rodar bem no momento em que
o polling periódico dispara.

## 0.5 Bug crítico encontrado e corrigido: `os_type` errado impedia a pontuação de quase tudo

Depois de ligar a sincronização automática (`IXC_SYNC_ENABLED=true`), o dono do produto reportou que O.S.
com assunto já cadastrado no IXC não estavam sendo "identificadas". Investigando a O.S. `IXC-1273437`
(assunto "Sem Conexão Fibra Urbana"), o assunto em si estava certo - o problema era outro: **não existe
regra de pontuação pra esse `os_type`**, porque o `os_type` das O.S. vindas da API estava sendo resolvido
errado desde o início.

**Causa raiz:** a pontuação (`matching_scoring_rule`, `scoring_detail.py:172`) exige que `os_type` **e**
`os_subject` batam ao mesmo tempo - não só o assunto. A decisão original desta integração (seção 7) de
usar `su_oss_chamado.setor` (resolvido via `empresa_setor`) para `os_type` estava errada: `setor` é o
**departamento/equipe interna** do IXC (ex. "Suporte Externo Fibra"), não a **categoria de serviço** que a
matriz de pontuação espera (ex. "Manutenção"). Confirmado com dado real: para o mesmo assunto "Suporte
Externo Fibra Urbana", a planilha sempre usou `os_type = "Manutenção"` (7552 O.S. históricas), enquanto a
API gerava `os_type = "Suporte Externo Fibra"` - nenhuma das ~2300 O.S. importadas nessa leva conseguia
casar com regra nenhuma por causa disso, mesmo o assunto estando 100% certo.

Não existe campo no IXC (nem em `su_oss_assunto`, nem em `su_oss_chamado`) que carregue essa categoria de
serviço - é uma classificação que só existia no processo de montagem da planilha UpValue.

**Correção, sem precisar recadastrar nada manualmente:** confirmado que a relação assunto → categoria é
1:1 e determinística em 100% do histórico já importado (nenhum assunto tem mais de uma categoria
diferente). `ixc_importer.py` agora aprende esse mapeamento a partir do próprio histórico
(`load_historical_os_type_mapping`, consulta os `service_orders` que **não** vieram da API) e usa isso
como fonte primária de `os_type` - só cai para o nome do `setor` quando o assunto é realmente novo (nunca
apareceu via planilha). De 62 assuntos distintos vistos na API, 54 já tinham mapeamento histórico; os 28
sem mapeamento são majoritariamente administrativos/comerciais (Faturamento, Comercial, Cobrança,
Retenção), que nunca fizeram parte do escopo técnico da gamificação - não é uma lacuna a preencher.

**Dado de teste (2295 O.S. com o bug) foi apagado e reimportado do zero** já com a correção. Confirmado
manualmente: a O.S. original reportada (`Sem Conexão Fibra Urbana`) agora casa com a regra "Manutenção"
e pontua 6 pontos, como esperado.

**Nota lateral (achado ao investigar):** durante a investigação eu consultei por engano a tabela legada
`scoring_rules` (11 linhas neste banco de dev) em vez da tabela realmente usada pelo motor de pontuação,
`scoring_subject_rules` (51 linhas) - `seed.py` tem uma função `migrate_legacy_scoring_rules` sugerindo que
`scoring_rules` é mesmo legado. Vale confirmar se ainda há algo dependendo da tabela antiga.

## 0.4 Sincronização automática (Fase C/D, parte 1): construída e validada

Decisão do dono do produto: não criar usuário de webservice dedicado, manter o token atual (o mesmo já
exposto no chat) — aceito, é uma decisão de risco dele. Sobre o achado do SLA (seção 0.3): decisão do dono
do produto é garantir que `meta_horas_abertura` esteja configurado nos assuntos que importam, em vez de
mudar o código agora.

Construído:
- `backend/app/services/ixc_importer.py` — `sync_ixc_service_orders()`: sincronização incremental via
  marca d'água (`AppSetting`, chave `ixc_sync_last_updated_at`), filtrando por `ultima_atualizacao` do IXC
  (pega O.S. novas E já existentes que mudaram, ex: uma que fechou).
- `backend/app/services/ixc_scheduler.py` (novo) + `main.py`: loop periódico opcional, via
  `IXC_SYNC_ENABLED`/`IXC_SYNC_INTERVAL_MINUTES` (desligado por padrão — precisa ligar explicitamente).

**Bug real encontrado e corrigido**: o servidor do IXC grava `ultima_atualizacao` em horário local
(confirmado: ~4h atrás do relógio UTC do nosso container, bate com o fuso de Rondônia). Calcular a janela
inicial da marca d'água usando `datetime.now()` do nosso lado dava sempre zero resultados (perguntava por
uma janela que, do ponto de vista do relógio do IXC, ainda não tinha acontecido). Corrigido: a primeira
sincronização agora busca a O.S. mais recente do próprio IXC primeiro, e calcula a janela inicial a partir
do relógio dele, não do nosso.

**Nota de design importante**: não apliquei essa mesma correção de fuso horário na conversão de
`opened_at`/`closed_at` de cada O.S. (isso continua tratando o horário do IXC como se already fosse UTC,
igual o importador UpValue sempre fez) - fazer isso diferente entre os dois importadores criaria uma
divergência de ~4h nos horários entre O.S. importadas por planilha vs. por API, o que atrapalharia
exatamente a comparação que a Fase C pretende fazer. Fica registrado como outro achado do tipo "já existia,
não é specific da integração IXC" (mesma categoria do achado de SLA da seção 0.3).

**Validado com dados reais** (banco de desenvolvimento, autorizado pelo dono do produto):
- Primeira sincronização (janela de 2h): 564 processadas, 419 criadas, **96 atualizadas** (confirma que
  O.S. já importadas que mudaram de status são pegas certo), 7 bloqueadas por período pago (funcionando).
- Segunda sincronização (chamada logo em seguida, sem parâmetro de janela): só 2 registros processados —
  confirma que a marca d'água evita reprocessar tudo de novo.

**Ainda não ligado**: `IXC_SYNC_ENABLED` continua `false` por padrão - o polling automático de verdade
(a cada 15-30 min, resolvendo com o backend rodando) só começa quando isso for ligado explicitamente.

## 0.3 Achado importante (não é do escopo desta integração, mas afeta os dois importadores)

Rodando um teste real de importação (138 O.S. de hoje, autorizado pelo dono do produto, gravado no banco
de **desenvolvimento**), notei que `sla_hours`/`closing_time_hours` nunca ficam `NULL` no banco mesmo
quando não temos essa informação (ex: assunto sem `meta_horas_abertura` configurado) — viram `24`/`0`
(os valores de `default=` da coluna em `models.py`). Confirmado isoladamente: o SQLAlchemy substitui
`None` explícito pelo `default=` da coluna quando ela tem um, em vez de gravar `NULL`.

**Isso não é um bug introduzido pela integração IXC** — `upvalue_importer.py` monta o payload exatamente
da mesma forma (pode passar `None` pra esses campos quando a planilha não traz a coluna), então esse
comportamento já existe hoje, silenciosamente, pro caminho UpValue também.

**Por que importa:** em `sla_inside()` (`scoring_detail.py:773`), a linha
`if order.sla_hours is None or order.closing_time_hours is None: return False` nunca é alcançada, porque
esses campos nunca chegam `NULL` de verdade — sempre chegam `24`/`0`. Na prática, `0 <= 24` é `True`, ou
seja, **qualquer O.S. com SLA desconhecido é silenciosamente tratada como "dentro do prazo"**, em vez de
ficar de fora do cálculo como o código parece pretender.

**Decisão:** não mexi nisso agora — corrigir mudaria comportamento histórico do sistema inteiro (não só da
integração IXC), e isso merece uma decisão deliberada seguida de uma checagem do impacto nos números já
fechados, não uma correção de passagem. Registrado aqui para decidirmos separadamente.

## 0.2 401 investigado e resolvido — não era bloqueio de rede, era o `.env`

Ao testar o `ixc_client.py` pela primeira vez, toda chamada retornava `401 Authorization Required` vindo
do nginx. Investiguei bastante em cima da hipótese de bloqueio por "assinatura" de cliente HTTP
(Python vs PowerShell/Node) — IP idêntico, DNS idêntico, `httpx` e `urllib` falhando igual, chegou a
parecer uma proteção de rede específica contra clientes de script.

**Causa real, bem mais simples:** o valor de `IXC_API_TOKEN` no `.env` estava salvo com colchetes
angulares literais em volta (`<929:...>`), que não fazem parte do token de verdade — isso sozinho já
invalidava a autenticação, independente de qualquer biblioteca ou linguagem. Corrigido o `.env` (removidos
os colchetes), o cliente Python passou a funcionar imediatamente, sem precisar de nenhum intermediário
Node.js. Registro para não repetir: deveria ter conferido o valor literal salvo antes de investigar teorias
de rede mais complexas.

**Nota de segurança à parte:** o token usado para esse teste (`929:f11b85...`) é o mesmo token de teste que
já tinha sido colado no chat no início desta conversa — não é o usuário de webservice dedicado que
havíamos combinado criar. Funciona para testes, mas antes de qualquer uso em produção, ainda recomendo
criar o usuário dedicado e usar o token dele aqui.

**Validado com dados reais:** `fetch_service_orders` com filtro de data (`opened_after`) buscou 679 O.S.
abertas em 2026-07-16 corretamente, com paginação funcionando.

## 0. Progresso

- **Fase A (cliente de API isolado): iniciada.** `backend/app/services/ixc_client.py` criado — autenticação
  Basic (usuário + token), paginação defensiva (`list_all`, não confia em `rp` ser respeitado pelo
  servidor), e funções de busca para `su_oss_chamado`, `su_oss_assunto`, `su_diagnostico`, `funcionarios`,
  `cidade` e `cliente` (por lista de IDs). Configuração nova em `backend/app/core/config.py`
  (`ixc_api_base_url`, `ixc_api_token`, `ixc_api_verify_ssl`) e `.env.example`. Ainda não usado por
  nenhuma rota nem pelo pipeline de importação — só o cliente HTTP existe até aqui.
- **As 6 perguntas originais da seção 9 estão todas respondidas.** Regional/filial resolvida (seção 4),
  reincidência é calculada pela regra parametrizada (seção 5), SLA será calculado a partir da meta do
  assunto porque `status_sla`/`data_prazo_limite` não são usados nessa instância do IXC (seção 6), `os_type`
  vem de `setor`, usuário de webservice dedicado, polling a cada 15-30 min.
- **Os 2 gaps que restavam também foram fechados**: `os_code` = `id` do IXC, prefixado `IXC-` (reserva:
  `protocolo`, decisão do dono do produto — prioriza estabilidade da chave sobre o número que a operação
  reconhece); `customer_login`/`contract_id` resolvidos via `id_login` → tabela `radusuarios` (`login`,
  `id_contrato`).
- **Mapeamento de campos 100% fechado. Fase B (adaptador) escrita**: `backend/app/services/ixc_importer.py`
  criado — reaproveita as mesmas funções de matching/auditoria/bloqueio de período pago/detecção de
  garantia do `upvalue_importer.py` (via import direto, sem duplicar nem modificar o importador existente).
  Ainda não tem controle de sincronização incremental (watermark) - fica para Fase C/D.
- **Validado**: módulo importa sem erro dentro do container, suíte de testes existente inteira passa
  (17/17) depois da mudança em `regional.py` (filial `"5"` marcada como código inválido). Backend segue
  saudável. Nenhuma rota ou scheduler chama esse código ainda — é só o adaptador em si, isolado, sem
  nenhum efeito em produção até aqui.
- **Gaps conhecidos e não resolvidos, deixados explícitos no código** (comentário `TODO` em
  `ixc_importer.py`): `has_pending` sempre `False` (não achamos campo correspondente em `su_oss_chamado`
  ainda); `has_reschedule` inferido de `data_reagendar` estar preenchido (não confirmado com dado real).
- **Fase B testada ponta a ponta com dado real, autorizado pelo dono do produto**: rodei
  `import_ixc_service_orders` de verdade (94→138 O.S. abertas hoje, entre a checagem e a execução mais
  algumas foram abertas) contra o **banco de desenvolvimento** (não produção). Resultado: 138 criadas, 0
  erros, 0 rejeitadas, 23 colaboradores novos criados por nome. Conferido manualmente no banco: `regional`,
  `os_type` (via `setor`) e `os_subject` (via `assunto`) todos resolvendo pra nomes reais corretos.
- **Bug real encontrado e corrigido em `ixc_client.py`**: quando uma busca não tem nenhum resultado, o IXC
  não devolve a chave `registros` (só `page`/`total`) — meu código tratava isso como resposta inesperada/
  erro. Corrigido para tratar ausência de `registros` como lista vazia.
- **Achado importante fora do escopo desta integração**: ver seção 0.3 — `sla_hours`/`closing_time_hours`
  nunca ficam `NULL` no banco (viram os valores `default=` da coluna), afetando também o importador
  UpValue já existente. Não corrigido agora, decisão fica pra depois.

## 0.1 Achados de dados reais (3 amostras puxadas até agora)

1. **`id_filial` bate com `REGIONAL_CODE_MAP`** para os códigos vistos (6, 7, 10, 13, 14, 16, 17).
   `id_filial = 5` também apareceu, mas você confirmou que é a "geral de cadastro" (filial administrativa,
   não uma unidade de atendimento) — vira código inválido, não regional nomeada (seção 4).
2. **`tipo` é sempre `"C"`** — confirma que não serve pra diferenciar tipo de O.S. (é praticamente constante).
3. **`setor` não é texto, é um código numérico** que aponta pra uma tabela própria (`empresa_setor`, com
   `id`/`setor`/`id_depto`) — já encontrei o endpoint, só falta resolver o nome de cada código.
4. **`status_sla` e `data_prazo_limite` vieram vazios em todas as amostras até agora**, inclusive em O.S.
   fechadas — tanto nas de hoje quanto nas 15 primeiras O.S. do sistema inteiro (que acabaram sendo tickets
   de teste/cadastro da filial 5, não representativas). Ainda falta uma amostra de um período "normal" de
   atendimento real pra confirmar se esses campos existem de fato — comando pronto na seção 9, pergunta 4.

## 1. Objetivo

Hoje o único jeito de a gamificação receber ordens de serviço é `backend/app/services/upvalue_importer.py`:
alguém exporta uma planilha do UpValue e sobe no sistema. A intenção é que, no futuro, essa entrada
venha direto da API do IXC (o próprio ERP da UNI), sem depender de planilha manual.

Este documento é só o plano — nenhuma linha de código foi escrita ainda, conforme combinado. O objetivo
é decidir, com calma, como isso vai funcionar antes de mexer em qualquer coisa que afete o pagamento de
colaboradores.

## 2. Por que isso é sensível

`upvalue_importer.py` não é só "ler uma planilha e criar linhas". Ele carrega lógica de negócio que
precisa continuar existindo **independente da fonte de dados**:

- **Detecção de duplicidade por hash de arquivo** (`has_duplicate_successful_import`) — não se aplica a
  uma API (não existe "arquivo"), então essa camada de proteção precisa de um equivalente novo.
- **Matching de identidade da O.S.** (`find_existing_service_order`): primeiro por `os_code` exato,
  senão por `(customer_login ou contract_id) + os_subject + opened_at`. Isso decide se uma O.S. é nova
  ou uma atualização de uma já existente.
- **Bloqueio de período pago** (`find_paid_run_for_service_order_context` + `paid_period_blocked_count`):
  se a O.S. cai num mês já com `CalculationRun` pago, ela não é criada/alterada — fica registrada como
  bloqueada, exigindo uma revisão pós-pagamento explícita.
- **Detecção de débito de garantia pós-pagamento** (`detect_post_payment_warranty_debits`), disparada
  sobre as O.S. tocadas em cada importação.
- **Resolução de colaborador por nome** (`get_or_create_collaborator`): compara nome normalizado
  (acento/caixa-insensível) contra colaboradores existentes; só cria um novo se não achar match.
- **Normalização de regional** (`normalize_regional`/`is_valid_regional`, em
  `backend/app/services/regional.py`) e **auditoria por campo** (`ImportServiceOrderAudit`, uma linha por
  campo alterado, com valor antigo/novo).
- **Diffing por "campo fornecido"**: a importação só sobrescreve um campo do banco se a fonte atual
  realmente trouxe aquele campo (`provided_fields`) — evita apagar dado bom com célula vazia.

Nada disso muda com a troca de fonte. O que muda é só a etapa de "ler o dado bruto e montar o payload"
(`build_service_order_payload`). A ideia é que o cliente novo da API do IXC alimente o **mesmo pipeline**
de matching/auditoria/bloqueio que já existe, e não um caminho paralelo com lógica duplicada.

## 3. Mapeamento de campos: `su_oss_chamado` (IXC) → `ServiceOrder`

Confirmado direto na documentação oficial do webservice (wiki do provedor) e no teste real que você já
rodou contra `sistema.souuni.com`:

| Campo `ServiceOrder` | Origem no IXC | Observação |
|---|---|---|
| `os_code` | `id` (prefixado `IXC-`), com `protocolo` como reserva | Decisão do dono do produto: usar `id`, não `protocolo` |
| `regional` | `id_filial` (direto na O.S.) | **Ver seção 4** — provável match com `REGIONAL_CODE_MAP` já existente |
| `customer_name` | `id_cliente` → `cliente.razao`/`fantasia`/`nome_social` | Precisa de 1 chamada extra por cliente (ou cache) |
| `customer_login` | `id_login` → `radusuarios.login` | Resolvido — ver tabela de apoio abaixo |
| `contract_id` | `id_login` → `radusuarios.id_contrato` | Resolvido — mesma chamada que resolve `customer_login` |
| `collaborator_name` | `id_tecnico` → `funcionarios.funcionario` | 1 chamada extra por técnico (ou cache) |
| `os_subject` | `id_assunto` → `su_oss_assunto.assunto` | |
| `diagnosis` | `id_su_diagnostico` → `su_diagnostico.descricao` | |
| `os_type` | sem campo óbvio 1:1 | **Decisão pendente** — ver seção 5 |
| `status` | `status` (código de 1-2 letras, ex. `A`) | Precisa de tabela código → texto (`Aberta`/`Finalizada`/etc), a validar contra a amostra real que você já puxou |
| `sla_status` | `status_sla`, a validar | **Ver seção 6** — pode não vir pronto, talvez precise ser calculado |
| `sla_hours` / `closing_time_hours` | não existem direto | **Ver seção 6** — calculável a partir de `data_abertura`/`data_prazo_limite`/`data_fechamento` |
| `opened_at` | `data_abertura` | |
| `closed_at` | `data_fechamento` | |
| `scheduled_at` | `data_agenda` | |
| `deadline_at` | `data_prazo_limite` | |
| `is_warranty`, `is_recurrence` | **não existem em `su_oss_chamado`** | **Ver seção 5 — é o achado mais importante deste estudo** |

Tabelas de apoio já confirmadas (endpoint + campos-chave):

| Entidade | Endpoint | Campos-chave |
|---|---|---|
| Cliente | `cliente` | `id`, `razao`, `nome_social`, `fantasia`, `filial_id` |
| Assunto | `su_oss_assunto` | `id`, `assunto` |
| Diagnóstico | `su_diagnostico` | `id`, `descricao`, `id_setor` |
| Técnico | `funcionarios` | `id`, `funcionario`, `filial_id`, `usuario_id` |
| Cidade | `cidade` | `id`, `nome`, `uf`, `regiao` |
| Setor | `empresa_setor` | `id`, `setor` (nome), `id_depto` |
| Login/Contrato | `radusuarios` | `id`, `login`, `id_contrato`, `id_cliente`, `id_filial` |

## 4. Regional/filial: provável solução já pronta no código

`backend/app/services/regional.py` já tem um `REGIONAL_CODE_MAP` que traduz **códigos numéricos** (`"6"`
a `"18"`) para nomes de regional (`"UNI - JI PARANA"`, `"UNI - JARU"`, etc.) — exatamente o formato que o
`id_filial` do IXC deveria ter. Isso é forte indício de que esse mapa **já foi feito pensando nos códigos
de filial do próprio IXC** (a numeração começando em 6 e pulando 1-5 não é coincidência de planilha).

Se isso se confirmar, resolver a regional de uma O.S. vinda da API é trivial: usar `id_filial` direto,
sem nenhuma chamada extra. **Confirmado** com amostra real (seção 0.1): os códigos 6, 7, 10, 13, 14, 16, 17
batem certinho com o mapa existente.

**`id_filial = 5` — resolvido, e não é uma regional operacional.** Você confirmou que é a "geral de
cadastro" (filial administrativa, não uma unidade de atendimento de verdade) — bate com o que os dados
mostraram (as 15 primeiras O.S. do sistema inteiro são dessa filial, abertas e fechadas em ~1 minuto,
características de ticket de teste/cadastro, não atendimento real). **Decisão:** tratar `"5"` como código
inválido, igual `"0"`/`"1"` hoje (`INVALID_REGIONAL_CODES` em `regional.py`), em vez de adicionar como
regional nomeada — uma O.S. dessa filial não deveria gerar pontuação nem entrar no cálculo de saúde
regional de nenhuma unidade real.

## 5. Achado mais importante: `is_warranty`/`is_recurrence` não existem nos dados brutos do IXC

A planilha UpValue hoje traz colunas explícitas de "Garantia"/"Reincidência"/"Retorno 30 dias"
(`UPVALUE_COLUMN_ALIASES["is_warranty"]`/`["is_recurrence"]`), presumivelmente preenchidas por alguém na
operação ao montar a exportação. **Não existe campo equivalente em `su_oss_chamado`.**

Investigando mais a fundo, encontrei **dois** lugares que consomem essas flags, não um só:
1. `classify_recurrence_pair` (`scoring_detail.py:518`) — usa a flag só como reforço (`later_is_flagged_return`),
   quando diagnóstico/assunto não batem automaticamente entre a O.S. original e a posterior.
2. **Pontuação direta de cada O.S.** (`scoring_detail.py:983` e `:1064`) — se `order.is_warranty or
   order.is_recurrence` for verdadeiro, isso zera/reduz/manda pra revisão manual os pontos daquela O.S.
   especificamente, independente de qualquer pareamento com outra O.S.

**Resposta confirmada com você:** essas flags nunca foram uma marcação manual confiável — a reincidência é
decidida pelo próprio motor (regra de negócio parametrizada, `RecurrenceClassificationRule`), que já casa
por texto de `os_subject`/`os_type`/`diagnosis` (ex. o assunto "reincidência de suporte" é reconhecido por
essas regras, não pela flag). Ou seja: **usar `is_warranty`/`is_recurrence` sempre `False` nas O.S.
importadas via API não é uma perda — é o comportamento correto**, já que o motor de regras nunca dependeu
dessas flags para identificar reincidência pelo texto do assunto. O único ponto a observar na fase de
validação em paralelo (seção 8, fase C) é confirmar que nenhuma O.S. hoje só é pega pela via 1 acima (o
reforço `later_is_flagged_return`, quando diagnóstico/assunto não batem) — se acontecer, vai aparecer como
uma O.S. que a fonte antiga classificava como reincidência e a nova não, e dá pra tratar caso a caso.

## 6. Como o SLA por regional é medido — e o que muda com a API

A regional não tem "um SLA" próprio guardado em algum lugar: ele é **calculado por período**, a partir
das O.S. dela. `calculate_regional_health()` (`services/scoring_detail.py:827`) agrupa as O.S. concluídas
do período por regional e calcula:

```
sla_rate = (nº de O.S. dentro do prazo / total de O.S. da regional) × 100
```

"Dentro do prazo" é decidido por `sla_inside(order)` (`services/scoring_detail.py:773`): primeiro tenta o
texto `order.sla_status` (ex. "Encerrada no Prazo"/"Encerrada Atrasada", normalizado por
`services/sla.py`); se não tiver, cai para `closing_time_hours <= sla_hours`. Essa taxa entra numa
`HealthRule` configurável (mínimo de SLA + máximo de reincidência) que define o **multiplicador de saúde
regional** aplicado à pontuação de todo colaborador daquela regional no período — o mesmo multiplicador
por trás da divergência "Pontos do mês" vs "Pontos a pagar" que já vimos nesta conversa.

**O problema:** `su_oss_chamado` não tem `sla_hours` nem `closing_time_hours` como campos diretos. O que
existe é `data_abertura`, `data_prazo_limite` e `data_fechamento` (datas brutas), além de um campo
`status_sla` nativo e `justificativa_sla_atrasado` (o IXC claramente rastreia SLA internamente, só não
sei ainda em que formato exato).

**Confirmado com 3 amostras reais (hoje, as 15 O.S. mais antigas do sistema, e um lote real de fim de
junho/2026):** `status_sla` vem **sempre vazio** e `data_prazo_limite` vem vazio ou com `0000-00-00
00:00:00` (um "zero" de data do MySQL, não uma data de verdade) — inclusive em O.S. reais, fechadas, de
atendimento comum (não teste). Essa instância do IXC **não usa esses dois campos na prática**, então as
opções 1 e 2 abaixo estão descartadas.

**Decisão:** opção 3 — calcular localmente a partir da meta de SLA configurada por assunto:
- `sla_hours` = `su_oss_assunto.meta_horas_abertura` do assunto da O.S. (`id_assunto`)
- `closing_time_hours` = `data_fechamento − data_abertura`, em horas
- `sla_inside` = `closing_time_hours <= sla_hours` (mesma fórmula que já existe em `sla_inside()`, só
  muda de onde `sla_hours` vem)

**Cuidado de implementação a registrar para a Fase B:** o valor `"0000-00-00 00:00:00"` que apareceu em
`data_prazo_limite` é um "zero-date" típico de MySQL, não `null`. Se o parser de data não tratar esse
valor explicitamente como ausente, ele pode virar uma data literal do ano 0 e quebrar qualquer comparação
de datas mais adiante — precisa de um guard específico para essa string ao ler qualquer campo de data
vindo do IXC, não só `data_prazo_limite`.

Isso não muda a fórmula do `sla_rate` por regional em si (ela já é agregada em cima de `ServiceOrder`,
independente da fonte) — muda só como cada `ServiceOrder` individual chega com `sla_status`/`sla_hours`/
`closing_time_hours` preenchidos corretamente. Se isso vier errado da integração, o multiplicador de
saúde de toda a regional fica errado, não só uma O.S. — por isso isso precisa ser validado com dados
reais antes de qualquer corte oficial (ver seção 8, fase C — a validação em paralelo compara justamente
o `health_by_regional` das duas fontes, não só a pontuação individual).

## 7. `os_type` — decisão revista (ver seção 0.5)

No importador atual, `os_type` e `os_subject` vêm de colunas de planilha diferentes, mas nem sempre bem
distintas (aliases incluem "Tipo Geral", "Grupo", "Processo", "Departamento", "Setor" para `os_type`, e
"Assunto"/"Tarefa" para `os_subject`). Em `su_oss_chamado` existe `id_assunto` (→ `os_subject`), `setor` e
`tipo`.

**Confirmado com dado real (seção 0.1):** `tipo` veio **sempre `"C"`** numa amostra de 15 O.S. — não serve
para diferenciar nada, é constante. `setor` **não é texto livre, é um código numérico** que aponta para a
tabela `empresa_setor` (`id`, `setor` = nome, `id_depto`) — precisa de mais uma chamada/cache para resolver
o nome, igual às outras tabelas de apoio.

**Decisão original (revista depois):** `os_type` vem de `setor` (resolvido via `empresa_setor.setor`), não
de `tipo`. **Essa decisão estava errada** — `setor` é o departamento/equipe interna do IXC, não a
categoria de serviço que a matriz de pontuação exige (ver seção 0.5, achado crítico). Correção aplicada:
`os_type` agora vem do histórico já importado (aprendido automaticamente por assunto), com `setor` como
reserva só para assuntos genuinamente novos que nunca apareceram via planilha.

## 8. Estratégia de corte: paralelo, não substituição direta

Dado que essa fonte de dados alimenta pagamento, a recomendação é **não desligar a planilha no dia em
que a API funcionar**. Sequência sugerida:

1. **Fase A — cliente de API isolado**: criar `backend/app/services/ixc_client.py` (chamadas HTTP puras:
   autenticação, paginação, `su_oss_chamado` + tabelas de apoio), sem tocar em `upvalue_importer.py`.
2. **Fase B — adaptador**: criar `ixc_importer.py` que usa o cliente da Fase A para montar o mesmo
   payload que `build_service_order_payload` monta hoje, e reaproveita **as mesmas funções** de matching/
   auditoria/bloqueio de período pago/detecção de garantia (`find_existing_service_order`,
   `get_or_create_collaborator`, `find_paid_run_for_service_order_context`,
   `detect_post_payment_warranty_debits`) — extraídas de `upvalue_importer.py` para um módulo comum se
   necessário, em vez de duplicadas.
3. **Fase C — validação em paralelo**: rodar a importação por API **ao lado** da planilha, por pelo menos
   um fechamento completo, comparando O.S. por O.S. e pontuação final por colaborador entre as duas
   fontes, sem que a API seja a fonte oficial ainda.
4. **Fase D — corte**: só depois de um fechamento inteiro validado sem divergências relevantes, a API
   passa a ser a fonte oficial. A planilha continua disponível como fallback manual por mais um tempo.

Cada fase é revisável e reversível — nenhuma delas exige desligar o que já funciona antes da anterior
estar validada.

## 9. Perguntas em aberto antes de avançar para código

1. ~~`REGIONAL_CODE_MAP` bate...~~ **Respondida** (seção 4): códigos 6-18 batem. `id_filial = 5` é a
   "geral de cadastro" (filial administrativa) — vai ser tratada como código inválido, não como regional.
2. ~~O motor `recurrence_penalties` já cobre...~~ **Respondida** (seção 5): reincidência é decidida pela
   regra de negócio parametrizada, não por marcação manual — seguro usar `False` sempre na importação API.
3. ~~`os_type` deve vir de...~~ **Respondida**: mapear a partir de `setor` (resolvido via `empresa_setor`).
4. ~~`status_sla` do IXC já é...~~ **Respondida** (seção 6): confirmado com 3 amostras reais (incluindo
   atendimento real de fim de junho/2026, não teste) que `status_sla`/`data_prazo_limite` não são usados
   nessa instância. SLA será calculado a partir de `su_oss_assunto.meta_horas_abertura` vs.
   `data_fechamento − data_abertura`.
5. ~~Qual granularidade de autenticação...~~ **Respondida**: criar um usuário de webservice novo e
   dedicado (não reaproveitar o token de teste já exposto no chat). Falta você criar esse usuário no IXC
   (Configurações do sistema → Usuários → Novo, marcar "Permite acesso ao webservice", grupo com acesso
   total, remover filtros de setor/funcionário) e colocar o token gerado em `backend/.env` na chave
   `IXC_API_TOKEN` — não precisa me passar esse token, só confirmar que colocou.
6. ~~Frequência de sincronização...~~ **Respondida**: polling periódico (15-30 min). Isso ainda não foi
   implementado (não faz parte da Fase A) — entra na Fase B/C junto com o adaptador de importação.

## 10. O que este documento não é

Não é uma proposta de arquitetura de "UNI Workspace" (o módulo maior mencionado como visão de longo
prazo) — é só sobre trocar a fonte de dados de O.S. Também não inclui nenhuma estimativa de prazo, já que
depende das respostas da seção 8.
