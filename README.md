# OPR Gamificacao Operacional

Sistema inicial para Remuneracao Variavel Operacional / Gamificacao da Produtividade do time de campo da OPR.

## Stack

- Frontend: Next.js, TypeScript, Tailwind, Radix/shadcn-style components, TanStack Table, ECharts
- Backend: FastAPI, SQLAlchemy, Pydantic
- Banco: PostgreSQL
- Infra: Docker e Docker Compose

## Estrutura

```text
.
├── backend
│   ├── app
│   │   ├── api/routes
│   │   ├── core
│   │   ├── db
│   │   ├── services
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── seed.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend
│   ├── app/gamificacao
│   ├── components
│   ├── lib
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── .env.example
```

## Rodando localmente

1. Copie as variaveis de ambiente, se quiser customizar:

```powershell
Copy-Item .env.example .env
```

2. Suba a stack:

```powershell
docker compose up --build
```

3. Acesse:

- Frontend: [http://localhost:3000/gamificacao](http://localhost:3000/gamificacao)
- Backend health: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- Swagger/OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)
- PostgreSQL: `localhost:5432`

## Seed inicial

Com `AUTO_SEED=true`, o backend cria automaticamente:

- grupos de pontuacao
- penalidades
- regras de saude operacional
- valor do ponto inicial
- configuracao inicial da logica de calculo

O seed nao cria O.S de demonstracao. A matriz passa a ser alimentada apenas por assuntos importados das O.S reais ou por regras cadastradas manualmente.

Para rodar o seed manualmente:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/service-orders/seed
```

## Recalcular pontuacao

Pela interface, use o botao `Recalcular Pontuação`.

Via API:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/calculation-runs/calculate `
  -ContentType "application/json" `
  -Body '{"point_value":2.50}'
```

## Importar planilha do UpValue

A tela `/gamificacao` possui a secao `Importar O.S UpValue`.

Fluxo pela interface:

1. Selecione um arquivo `.xlsx`, `.xls` ou `.csv` exportado do UpValue.
2. O sistema chama o preview e mostra colunas detectadas, mapeamento sugerido e primeiras linhas.
3. Clique em `Confirmar Importação`.
4. Confira o resumo com linhas importadas, ignoradas e erros por linha.
5. Clique em `Recalcular Pontuação`.

Fluxo via API:

```powershell
$form = @{
  file = Get-Item "C:\caminho\ordens_upvalue.xlsx"
}
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/imports/upvalue-service-orders/preview `
  -Form $form

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/imports/upvalue-service-orders `
  -Form $form
```

### Formatos aceitos

- `.xlsx`
- `.xls`
- `.csv`

### Colunas reconhecidas

O importador normaliza cabecalhos removendo acentos, convertendo para minusculo e trocando espacos/caracteres especiais por underline.

Campos e variacoes aceitas:

- `os_code`: ID, ID O.S, ID O.S., ID da O.S, O.S, O.S., Protocolo, Protocolo da O.S, Codigo, Codigo O.S
- `contract_id`: Contrato, ID Contrato, ID do Contrato, Codigo Contrato, Contrato ID
- `customer_name`: Cliente, Pessoa, 1 Nome, 1º Nome, ID Cliente, Nome Cliente, Nome do Cliente, Assinante
- `collaborator`: Responsavel, Tecnico, Colaborador, Equipe, Tecnico/Equipe, Executor
- `regional`: Regional, Filial, Unidade, Base
- `os_type`: Tipo Geral, Solicitacao, Tipo, Tipo da O.S, Grupo, Processo, Departamento, Setor
- `os_subject`: Assunto, Descricao Solicitacao, Diagnostico, Assunto da O.S, Tarefa, Descricao da Tarefa, Servico
- `status`: Status, Situacao, Status da O.S
- `sla_status`: Status SLA, SLA, Situacao SLA
- `sla_hours`: SLA Horas, Tempo SLA, Horas SLA, SLA em horas, SLA, Min. Estimados
- `closing_time_hours`: Min. Trabalhados, TMF, T.M. Fechamento, Tempo Medio de Fechamento, Tempo de Fechamento, Tempo Total, Duracao
- `opened_at`: DT Abertura, Data Abertura, Data de Abertura, Abertura, Criado em
- `closed_at`: DT Fechamento, Data Fechamento, Data de Fechamento, Fechamento, Finalizado em, Encerrado em
- `scheduled_at`: DT Agendamento, Data Agendamento, Data de Agendamento, Agendamento
- `deadline_at`: DT Prazo, Data Prazo, Data de Prazo, Prazo
- `has_reschedule`: Reagendamento, Reagendado, Qtd Reagendamento, Quantidade de Reagendamentos
- `has_pending`: Pendencia, Pendente, Possui Pendencia
- `is_warranty`: Garantia, Garantia Ativacao, Garantia Manutencao, Dentro da Garantia
- `is_recurrence`: Reincidencia, Recorrencia, Retorno 30 dias

### Tratamento dos dados

- Datas aceitam `dd/mm/yyyy`, datetime e vazio.
- Numeros aceitam virgula decimal, texto com `h`, duracao `HH:MM` e vazio.
- Colunas em minutos, como `Min. Trabalhados`, sao convertidas para horas.
- Booleanos aceitam `sim`, `yes`, `true`, `1` e valores numericos maiores que zero como verdadeiro.
- Colaboradores inexistentes sao criados automaticamente com `active=true`.
- Sem responsavel, o colaborador fica como `NÃO IDENTIFICADO`.
- Sem assunto ou tipo, o campo fica como `NÃO IDENTIFICADO`.
- O.S repetidas por `os_code` sao atualizadas, nao duplicadas.
- Sem `os_code`, a duplicidade usa `contract_id + os_subject + opened_at`.
- A resposta de importacao inclui `first_errors` com os primeiros 20 erros reais para debug.

## Operacao auditavel da remuneracao

A tela `/gamificacao` foi organizada em quatro areas:

1. `Dashboard Executivo`: indicadores de pagamento, ranking auditavel, custo por regional/grupo/assunto e importacao UpValue.
2. `Matriz de Pontuacao`: grupos operacionais, pontuacao padrao, vinculo dos assuntos reais do UpValue e sobrescrita por assunto.
3. `Assuntos sem Regra`: fila de todos os assuntos importados que ainda nao possuem regra ativa.
4. `Auditoria do Calculo`: extrato linha a linha de cada O.S, com grupo aplicado, regra aplicada, pontos, penalidades e motivos.

### Nova matriz de pontuacao

A regra operacional agora e:

```text
Assunto real do UpValue
-> pertence a um grupo
-> grupo define pontuacao padrao
-> assunto pode sobrescrever a pontuacao
```

As tabelas principais sao:

- `scoring_groups`: nome, descricao, pontos padrao e status ativo.
- `scoring_subject_rules`: tipo geral, assunto real do UpValue, grupo, uso do padrao do grupo, pontos especificos e status ativo.

Se `use_group_default=true`, a O.S usa `scoring_groups.default_points`.
Se `use_group_default=false` e `custom_points` estiver preenchido, a O.S usa a pontuacao especifica do assunto.
Se o assunto nao existir na matriz, a O.S fica com status `Sem regra` e nao pontua ate ser vinculada.

### Assuntos sem regra

Depois de importar uma planilha real:

1. Abra a aba `Assuntos sem Regra`.
2. Veja tipo geral, assunto, quantidade de O.S, quantidade de colaboradores, regional predominante e impacto estimado.
3. Escolha um grupo destino e clique em `Vincular`.
4. Se ainda nao existir grupo adequado, clique em `Criar Grupo`.
5. Abra `Matriz de Pontuacao`, ajuste padrao do grupo ou pontos especificos do assunto.
6. Clique em `Recalcular Pontuacao`.

### Auditoria antes do pagamento

Use `Auditoria do Calculo` para validar a remuneracao antes de pagar. A tabela mostra O.S, colaborador, regional, cliente, contrato, tipo geral, assunto, grupo aplicado, regra aplicada, pontos, penalidades, SLA e motivos do calculo.

No ranking, clique em `Ver O.S` para abrir o extrato individual do colaborador. Os totais do extrato usam a mesma engine do ranking.

## Principais endpoints

- `GET /api/health`
- `POST /api/imports/upvalue-service-orders/preview`
- `POST /api/imports/upvalue-service-orders`
- `GET /api/collaborators`
- `POST /api/collaborators`
- `GET /api/scoring-groups`
- `POST /api/scoring-groups`
- `PUT /api/scoring-groups/{id}`
- `GET /api/scoring-rules`
- `POST /api/scoring-rules`
- `PUT /api/scoring-rules/{id}`
- `GET /api/scoring-subject-rules`
- `POST /api/scoring-subject-rules`
- `PUT /api/scoring-subject-rules/{id}`
- `GET /api/scoring-subject-rules/unmapped`
- `GET /api/audit/service-orders`
- `GET /api/collaborators/{id}/service-orders-detail`
- `GET /api/penalty-rules`
- `POST /api/penalty-rules`
- `PUT /api/penalty-rules/{id}`
- `GET /api/health-rules`
- `PUT /api/health-rules/{id}`
- `GET /api/settings`
- `PUT /api/settings/{key}`
- `GET /api/service-orders`
- `POST /api/service-orders/seed`
- `POST /api/calculation-runs/calculate`
- `GET /api/calculation-runs/latest`
- `GET /api/dashboard/summary`

## Logica de calculo

1. Busca as O.S do mes de referencia.
2. Para cada O.S, procura o assunto real em `scoring_subject_rules`.
3. Se encontrar regra ativa, aplica a pontuacao padrao do grupo ou a sobrescrita do assunto.
4. Se nao encontrar regra, marca a O.S como `Sem regra` e registra o motivo.
5. Aplica penalidades ativas em `penalty_rules`.
6. Identifica reincidencia operacional por mesmo contrato e mesmo assunto dentro da janela configurada em `app_settings.recurrence_window_days`.
7. Calcula a saude operacional por regional usando SLA, reincidencia, pendencias e reagendamentos.
8. Aplica o multiplicador ativo de `health_rules`.
9. Calcula pagamento estimado com `app_settings.point_value`.
10. Retorna motivos linha a linha para auditoria e para o extrato do colaborador.

## Fluxo esperado na tela

1. Abra `/gamificacao`.
2. Importe a planilha UpValue, se necessario.
3. Abra `Assuntos sem Regra` e vincule os assuntos reais aos grupos.
4. Abra `Matriz de Pontuacao` e ajuste pontos padrao ou pontos especificos.
5. Clique em `Recalcular Pontuacao`.
6. Abra `Auditoria do Calculo` para revisar linha a linha.
7. Clique em `Ver O.S` no ranking para auditar um colaborador.
8. Exporte a auditoria ou o extrato do colaborador antes do pagamento.
