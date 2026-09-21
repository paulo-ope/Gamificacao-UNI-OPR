# SLA por tecnologia — como consumir

Guia de leitura do indicador "SLA por tecnologia" (Ativação/Suporte × Fibra Urbana/Fibra
Rural/Rádio) para quem for consumir a API do UNI Workspace. Extraído por leitura direta do
código-fonte em 2026-09-18 — não é um contrato escrito à mão. Ver
[README.md](README.md) para ambiente/autenticação e [validacao.md](validacao.md) para o que já
foi validado contra dados reais (a maioria dos indicadores deste pacote ainda não foi).

## 1. Consultar o SLA por tecnologia

```
GET /api/operations/sla?date_from=2026-09-01&date_to=2026-09-18&group_by=technology_group
Authorization: Bearer <token>
```

- Requer a permissão `operations:view_sla` na identidade técnica.
- `date_from` e `date_to` são obrigatórios.
- `group_by=technology_group` é o que ativa a visão por tecnologia. Outros valores possíveis do
  mesmo parâmetro: `os_type`, `subject`, `diagnosis`, `department`, `sector` — não usar esses para
  o indicador de tecnologia.
- Filtros opcionais (repetíveis na query string, mesmos de todo o módulo Operações):
  `regionals`, `sectors`, `team_models`, `os_types`, `subjects`, `sla_statuses`, `search`, entre
  outros. Ver `backend/app/modules/operations/router.py:441` para a lista completa.

Fonte: `backend/app/modules/operations/router.py:1164`.

## 2. Formato da resposta

Array de objetos, um por grupo de tecnologia ativo (fonte:
`backend/app/modules/operations/schemas.py:613`):

```json
[
  {
    "label": "Ativação Fibra Urbana",
    "completed": 340,
    "on_time": 310,
    "out_of_time": 30,
    "sla_rate": 91.2,
    "up_to_12h": 200,
    "from_12h_to_24h": 90,
    "from_24h_to_48h": 30,
    "from_48h_to_72h": 15,
    "after_72h": 5,
    "average_closing_hours": 18.4
  }
]
```

| Campo | Significado |
|---|---|
| `label` | Nome do grupo de tecnologia (ex.: "Ativação Fibra Urbana", "Suporte Rádio") |
| `completed` | Total de O.S. fechadas no período/filtro, para esse grupo |
| `on_time` / `out_of_time` | Quantas ficaram dentro/fora do prazo de SLA |
| `sla_rate` | Percentual no prazo (`on_time / (on_time + out_of_time) * 100`), arredondado em 1 casa |
| `up_to_12h` … `after_72h` | Distribuição por faixa de tempo até o fechamento |
| `average_closing_hours` | Média de horas até o fechamento |

### Regras de leitura importantes

- **`sla_rate: null` não é 0%.** É o que a API devolve quando não há nenhuma O.S. com prazo
  medível (`on_time + out_of_time == 0`) no período/filtro. Tratar como "sem dado", nunca
  renderizar como SLA ruim.
- **"Outros" existe e não deve ser somado ao SLA por tecnologia.** Todo assunto de O.S. que não
  está atribuído a nenhum grupo ativo cai automaticamente em `"Outros"` (fonte:
  `backend/app/modules/operations/technology_group.py:90`). Ele aparece na resposta como mais um
  item da lista, mas não é uma das categorias oficiais do painel — não incluir no cálculo do SLA
  geral por tecnologia.
- **O SLA geral por tecnologia não é média simples dos percentuais dos grupos.** Para reproduzir
  o cálculo do painel, ponderar pelas bases (`completed`/`on_time`/`out_of_time`) de cada grupo,
  não fazer média aritmética dos `sla_rate` individuais.
- Resultado vem ordenado por volume decrescente (`completed`), não por nome do grupo.

## 3. De onde vêm os grupos "Fibra Urbana / Fibra Rural / Rádio"

Os grupos não são calculados na hora — são um cadastro persistido, consultável em:

```
GET /api/operations/sla-groups
Authorization: Bearer <token>
```

Requer `operations:view_sla`. Resposta (fonte:
`backend/app/modules/operations/schemas.py:812`):

```json
[
  {
    "id": 1,
    "card_label": "Ativação",
    "name": "Fibra Urbana",
    "display_order": 1,
    "active": true,
    "subjects": ["Instalação Fibra Urbana", "Retorno de Instalação Fibra Urbana"],
    "created_at": "2026-09-17T00:00:00Z",
    "updated_at": "2026-09-17T00:00:00Z"
  }
]
```

Quem só vai **ler** o indicador de SLA não precisa chamar esse endpoint — os grupos padrão
(Ativação/Suporte × Fibra Urbana/Fibra Rural/Rádio) já vêm cadastrados e `active: true`. Ele é
útil para:

- Descobrir de antemão quais `label`s esperar na resposta de `/sla?group_by=technology_group`,
  sem hardcodear os nomes no lado do consumidor.
- Saber se um grupo foi desativado (`active: false`) — nesse caso seus assuntos passam a cair em
  `"Outros"` até serem realocados para outro grupo, mas o grupo em si não aparece mais como linha
  separada.

### Administração da taxonomia (fora do escopo de leitura)

Só quem tiver a permissão mais restrita `operations:manage_sla_groups` pode criar/editar grupos ou
mover assuntos de O.S. entre eles:

- `POST /api/operations/sla-groups` — cria grupo (`card_label`, `name`)
- `PATCH /api/operations/sla-groups/{group_id}` — edita `card_label`/`name`/`display_order`/`active`
- `DELETE /api/operations/sla-groups/{group_id}`
- `PUT /api/operations/sla-groups/{group_id}/subjects` — substitui a lista inteira de assuntos do
  grupo (um assunto já atribuído a outro grupo é movido, nunca duplicado)

Um time consumidor que só lê dados **não precisa dessa permissão** e não deve receber essa
credencial — ela só é necessária para quem administra a classificação de O.S. por tecnologia dentro
do UNI Workspace.

## 4. Resumo mínimo para integrar

1. Chamar `GET /api/operations/sla-groups` uma vez para saber os `label`s ativos (opcional, mas
   evita hardcode).
2. Chamar `GET /api/operations/sla?group_by=technology_group&date_from=...&date_to=...` para os
   números.
3. Tratar `sla_rate: null` como "sem dado" e excluir o grupo `"Outros"` de qualquer agregação de
   SLA geral por tecnologia.
4. Repetir a mesma chamada trocando `date_from`/`date_to` para obter janelas de comparação (período
   anterior, acumulado anual) — a API não tem endpoint dedicado para isso; é o mesmo filtro com
   datas diferentes.

Esta página cobre só o contrato técnico. Se o número precisa ser publicado como indicador
corporativo (ex.: no Cubo), confirmar antes com a área de Operações se a classificação de assuntos
em `/sla-groups` já reflete o que a área considera correto — este documento não homologa a
completude da taxonomia, só descreve como ela funciona hoje no código.
