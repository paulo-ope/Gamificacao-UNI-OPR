# Módulo de Suporte - Análise e Evolução

## Índice

1. [Situação Atual](#situação-atual)
2. [Problemas Identificados](#problemas-identificados)
3. [Oportunidades de Evolução](#oportunidades-de-evolução)
4. [Proposta do Módulo de Suporte](#proposta-do-módulo-de-suporte)
5. [Arquitetura Sugerida](#arquitetura-sugerida)
6. [Roadmap de Implementação](#roadmap-de-implementação)

---

## Situação Atual

### Fluxo Existente de Ordens de Serviço

O sistema atual trabalha com **Ordens de Serviço (O.S.)** como unidade de trabalho:

- **Origem**: IXC (sistema de gestão de contratos)
- **Fluxo**: IXC → `operations_orders` → `service_orders` (projeção analítica)
- **Visualização**: Módulo de Operações Analíticas (módulo `/operacao`)
- **Contexto de Colaborador**: Portal (módulo `/portal`)

### Módulos Existentes

| Módulo | URL | Propósito | Usuários |
|--------|-----|----------|----------|
| **Gamificação** | `/gamificacao` | Pontos, ranking, histórico | Colaboradores, Gestores |
| **Operações Analíticas** | `/operacao` | Análise de O.S., SLA, Calendário | Gestores, Operadores |
| **Portal** | `/portal` | Perfil, ranking próprio, O.S. pessoais | Colaboradores |
| **Admin** | `/admin` | Usuários, perfis, configurações | Administradores |

### Funcionalidades Atuais de Suporte/Atendimento

**O que existe hoje:**
- ✅ Registro de O.S. com histórico completo (IXC)
- ✅ Associação O.S. ↔ Colaborador
- ✅ Status e SLA de atendimento
- ✅ Análise de pendências e recorrências
- ✅ Auditoria de mudanças em O.S.
- ✅ Importação e sincronização automática

**O que falta:**
- ❌ Dashboard de suporte em tempo real
- ❌ Fila de atendimento unificada
- ❌ Atribuição dinâmica de O.S.
- ❌ Comunicação intra-equipe sobre O.S. específicas
- ❌ Histórico de tentativas de resolução
- ❌ Escalonamento automático
- ❌ Métricas de tempo de resposta
- ❌ Priorização visual de casos críticos

---

## Problemas Identificados

### 1. Fragmentação de Visualização

**Problema**: O mesmo colaborador/gestor precisa acessar múltiplos módulos para ter visão completa:
- Gamificação → Ver ranking e histórico pessoal
- Operações → Ver contexto operacional de O.S.
- Portal → Ver perfil e O.S. pessoais

**Impacto**: 
- Perda de contexto ao navegar entre módulos
- Tempo gasto em "montagem" de visão holística
- Informações desincronizadas entre abas

---

### 2. Falta de Gerenciamento de Fila

**Problema**: Não há mecanismo de **"próxima O.S. para atender"**
- Colaboradores veem lista de O.S. mas não há priorização clara
- Gestor não consegue redirecionar O.S. entre times
- Sem conceito de "O.S. em atendimento vs. pendente"

**Impacto**:
- Oportunidade de paralelização de trabalho
- Impossibilidade de balanceamento de carga
- Sem visibilidade de "quem está fazendo o quê agora"

---

### 3. Comunicação Assíncrona Limitada

**Problema**: Sem histórico de interações sobre O.S. específicas
- Anotações devem ser feitas externamente (WhatsApp, email, etc.)
- Sem registro de tentativas de resolução
- Sem escalonamento documentado

**Impacto**:
- Perda de contexto quando O.S. passa entre colaboradores
- Duplicação de esforço (mesma tentativa 2x)
- Sem rastreabilidade para auditoria

---

### 4. Métricas Reativas

**Problema**: Análise é feita **após** o período encerrado
- SLA é calculado ao final (não em tempo real)
- Sem alertas de "vai bater SLA em X minutos"
- Sem previsão de conclusão baseada em histórico

**Impacto**:
- Impossibilidade de intervenção preventiva
- Gestores não conseguem antecipar problemas
- Dados só úteis para análise retrospectiva

---

### 5. Integração Incompleta com IXC

**Problema**: Dados de O.S. são **apenas importados**, nunca **exportados de volta**
- Status em IXC pode divergir do status em nossa base
- Anotações em nosso sistema não sincronizam com IXC
- Sem loop fechado de comunicação

**Impacto**:
- Verdade fragmentada (qual fonte é canônica?)
- Impossibilidade de usar o sistema como "source of truth"
- Perda de histórico se reimportação acontece

---

## Oportunidades de Evolução

### 1. Dashboard de Suporte Unificado

**O que seria**:
- Visão única de todas O.S. em progresso
- Fila de priorização inteligente (SLA, criticidade, tempo aberto)
- Filtros rápidos (por cliente, regional, tipo, status)
- Métricas em tempo real (% SLA, tempo médio, backlog)

**Benefício**:
- Redução de tempo de busca (2-5 min → 10 seg)
- Melhor decisão de priorização
- Visibilidade para gestão em tempo real

---

### 2. Sistema de Atribuição Dinâmica

**O que seria**:
- Conceito de "estado" da O.S.: pendente, em atendimento, bloqueado, concluído
- Colaborador marca "próxima O.S." e começa atendimento
- Gestor pode reatribuir (se necessário)
- Histórico de quem atendeu quando

**Benefício**:
- Transparência de quem está fazendo o quê
- Evita duplicação (2 pessoas atendendo mesma O.S.)
- Base para métricas de produtividade individual

---

### 3. Comunicação Intra-Sistema

**O que seria**:
- Abas de comentários/anotações por O.S.
- @mentions para chamar colega específico
- Histórico de tentativas (timestamp + autor + descrição)
- Escalonamento documentado

**Benefício**:
- Contexto preservado quando O.S. passa entre pessoas
- Auditoria completa
- Reduz necessidade de comunicação paralela (chat, email)

---

### 4. Métricas Preditivas

**O que seria**:
- Alertas de "SLA vai bater em 30 min"
- Estimativa de tempo para resolver baseada em histórico similar
- Tendências (tempo fechamento está aumentando?)
- Correlações (clientes X têm O.S. mais longas)

**Benefício**:
- Intervenção preventiva
- Identificação de gargalos reais
- Base para otimização

---

### 5. Loop Fechado com IXC

**O que seria**:
- Exportar anotações de volta para IXC (se permitido pela API)
- Sincronizar status bidirecionalmente
- Detectar divergências automáticas
- Versionar snapshots de dados

**Benefício**:
- Maior confiança nos dados
- Sistema como source of truth
- Rastreabilidade completa

---

## Proposta do Módulo de Suporte

### Visão Geral

Um novo módulo (`/suporte`) que funciona como **central de operações para O.S.** em tempo real, integrando:

- **Fila de Atendimento**: O que fazer agora?
- **Histórico de Casos**: O que foi feito antes?
- **Comunicação Intra-Sistema**: Quem sabe mais sobre isso?
- **Métricas Operacionais**: Como estamos indo?

### Página Principal: Fila de Atendimento

```
┌────────────────────────────────────────────┐
│ FILA DE ATENDIMENTO                        │
├────────────────────────────────────────────┤
│ Filtros: [Regional] [Tipo] [Status] [SLA] │
├────────────────────────────────────────────┤
│ CRÍTICA (4)  |  NORMAL (12)  |  BAIXA (28)│
├────────────────────────────────────────────┤
│ OS-12345  │ Cliente XYZ │ Sem Conexão    │
│ ⚠️ SLA: 15 min restante  │ Aberto: 2h45m │
│ Atribuído a: João Silva                   │
│ [Ver Detalhes] [Começar Atendimento]      │
├────────────────────────────────────────────┤
│ OS-12346  │ Cliente ABC │ Fatura Vencida │
│ ✅ SLA: 4h 30m restante │ Aberto: 30m   │
│ Não atribuído                            │
│ [Ver Detalhes] [Pegar Essa O.S.]         │
├────────────────────────────────────────────┤
```

### Página de Detalhes: Histórico + Comunicação

```
┌──────────────────────────────────────────────────┐
│ OS-12345 | Cliente XYZ | Sem Conexão Fibra      │
├──────────────────────────────────────────────────┤
│ Status: EM ATENDIMENTO                          │
│ Atribuído a: João Silva (desde 09:30)           │
│ SLA: 14:45 (⚠️ 15 min restante)                  │
│ Aberto: 14:30 | Previsão: 15:00                 │
├──────────────────────────────────────────────────┤
│ [Tentativas] [Comunicação] [Histórico] [SLA]   │
├──────────────────────────────────────────────────┤
│ COMUNICAÇÃO                                     │
│                                                 │
│ 09:30 - João Silva iniciou                     │
│ "Chamando o cliente, telefone sem resposta"     │
│                                                 │
│ 09:45 - Gestor Regional                        │
│ "@João - tenta mensagem SMS?"                  │
│                                                 │
│ 10:00 - João Silva                             │
│ "SMS enviado, aguardando resposta"             │
│                                                 │
│ [Nova Anotação]                                │
│ _________________________________              │
│ [Enviar]                                       │
└──────────────────────────────────────────────────┘
```

### Página de Métricas: Dashboard

```
┌──────────────────────────────────────────────────┐
│ MÉTRICAS DE OPERAÇÃO                            │
├──────────────────────────────────────────────────┤
│                                                 │
│ EM PROGRESSO: 16 O.S.                          │
│ ├─ Dentro do SLA: 14 (87.5%)  ✅               │
│ └─ Fora do SLA:   2  (12.5%)  ⚠️               │
│                                                 │
│ TEMPO MÉDIO: 2h 34m                           │
│ ├─ Última semana: 2h 45m ⬆️                    │
│ └─ Tendência: ↗️ AUMENTANDO                    │
│                                                 │
│ COLABORADOR COM MAIS CARGA                    │
│ João Silva: 8 O.S. em progresso               │
│ Maria: 5 O.S. em progresso                   │
│ Carlos: 3 O.S. em progresso                  │
│                                                 │
│ TIPOS MAIS FREQUENTES (HOJE)                  │
│ Sem Conexão: 8 O.S. (média 3h 15m)           │
│ Fatura: 4 O.S. (média 45m)                   │
│ Hardware: 2 O.S. (média 1h 30m)              │
│                                                 │
│ [Gráfico de SLA Histórico] [Análise Detalhada]│
└──────────────────────────────────────────────────┘
```

---

## Arquitetura Sugerida

### Backend: Novos Endpoints

```
POST   /suporte/queue
       Listar fila com filtros e priorização

GET    /suporte/queue/{os_id}
       Detalhes completos da O.S.

POST   /suporte/queue/{os_id}/assign
       Atribuir O.S. a colaborador

POST   /suporte/queue/{os_id}/start
       Marcar como "em atendimento"

POST   /suporte/queue/{os_id}/comment
       Adicionar comentário/anotação

GET    /suporte/metrics
       Métricas agregadas em tempo real

GET    /suporte/metrics/{period}
       Histórico de métricas
```

### Banco de Dados: Novas Tabelas

```sql
-- Estado de atendimento
CREATE TABLE support_ticket (
    id SERIAL PRIMARY KEY,
    os_id INTEGER REFERENCES service_orders(id),
    assigned_to INTEGER REFERENCES collaborators(id),
    status VARCHAR(20),  -- pending, in_progress, blocked, closed
    started_at TIMESTAMP,
    closed_at TIMESTAMP,
    priority VARCHAR(20)  -- critical, normal, low
);

-- Histórico de comunicação
CREATE TABLE support_comment (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER REFERENCES support_ticket(id),
    author_id INTEGER REFERENCES collaborators(id),
    content TEXT,
    created_at TIMESTAMP
);

-- Tentativas de resolução
CREATE TABLE support_attempt (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER REFERENCES support_ticket(id),
    collaborator_id INTEGER REFERENCES collaborators(id),
    description TEXT,
    result VARCHAR(20),  -- resolved, escalated, pending
    created_at TIMESTAMP
);
```

### Frontend: Novos Componentes

```
frontend/app/suporte/
├── page.tsx                  // Hub do módulo
├── queue/page.tsx            // Fila de atendimento
├── queue/[os_id]/page.tsx    // Detalhes da O.S.
├── metrics/page.tsx          // Dashboard de métricas
└── components/
    ├── queue-list.tsx        // Lista filtrada de O.S.
    ├── ticket-detail.tsx     // Detalhes + comunicação
    ├── metrics-dashboard.tsx // Gráficos e KPIs
    └── comment-section.tsx   // Seção de comentários
```

### Permissões Necessárias

```python
PERMISSION_LABELS = {
    # ... existentes ...
    "suporte:read": "Ver fila de atendimento",
    "suporte:assign": "Atribuir O.S.",
    "suporte:comment": "Comentar em O.S.",
    "suporte:escalate": "Escalar para gestor",
    "suporte:metrics": "Ver métricas operacionais",
}
```

---

## Roadmap de Implementação

### Fase 1: MVP (2-3 semanas)

**Objetivo**: Fila básica funcionando

- [x] Tabelas de support_ticket e support_comment
- [x] Endpoint GET /suporte/queue com filtros
- [x] Endpoint POST /suporte/queue/{os_id}/assign
- [x] Frontend: página de fila com botão "pegar O.S."
- [x] Sistema de permissões básico

**Resultado**: Colaboradores conseguem ver fila e pegar próxima O.S.

---

### Fase 2: Comunicação (2-3 semanas)

**Objetivo**: Histórico e colaboração funcionando

- [ ] Endpoint POST /suporte/queue/{os_id}/comment
- [ ] Seção de comentários no detalhe da O.S.
- [ ] @mentions para alertar colegas
- [ ] Notificações quando mencionado
- [ ] Histórico de tentativas de resolução

**Resultado**: Informação preservada e acessível quando O.S. passa entre pessoas

---

### Fase 3: Métricas (1-2 semanas)

**Objetivo**: Visibilidade operacional em tempo real

- [ ] Endpoint GET /suporte/metrics
- [ ] Dashboard com KPIs principais
- [ ] Alertas de "SLA vai bater"
- [ ] Tendências históricas
- [ ] Relatório por colaborador/tipo

**Resultado**: Gestores têm visão real de como está a operação

---

### Fase 4: Inteligência (2-4 semanas)

**Objetivo**: Sistema aprende e recomenda

- [ ] Roteamento inteligente (baseado em histórico)
- [ ] Estimativa de tempo para resolver
- [ ] Detecção de recorrências
- [ ] Sugestões de próximas ações
- [ ] Previsão de SLA

**Resultado**: Sistema ajuda a tomar melhores decisões

---

### Fase 5: Integração com IXC (2-3 semanas)

**Objetivo**: Loop fechado com sistema origem

- [ ] Exportar comentários para IXC
- [ ] Sincronizar status bidirecionalmente
- [ ] Detectar divergências
- [ ] Versionamento de snapshots

**Resultado**: Sistema é source of truth para operação

---

## Impacto Esperado

### Para Colaboradores

- ⏱️ **Tempo de busca**: 2-5 min → 10 seg
- 📊 **Contexto**: Precisa de 3 abas → 1 aba
- 💬 **Comunicação**: Paralela (chat/email) → Centralizada
- 🔍 **Rastreabilidade**: Ausente → Completa

### Para Gestores

- 👁️ **Visibilidade**: Apenas semanal → Tempo real
- ⚠️ **Reatividade**: Retrospectiva → Preventiva
- 📈 **Métricas**: Manuais → Automáticas
- ⚡ **Intervenção**: Tardia → Tempestiva

### Para Negócio

- 📞 **Tempo médio de resolução**: ↓ 15-20%
- 😊 **Satisfação do cliente**: ↑ SLA compliance
- 💰 **Produtividade**: ↑ Menos re-trabalho
- 🎯 **Previsibilidade**: ↑ Planejamento melhor

---

## Notas Técnicas

### 1. Diferença com Operações Analíticas

- **Operações**: Análise histórica, tendências, padrões
- **Suporte**: Operação em tempo real, fila, atribuição

Complementares, não concorrentes.

### 2. Integração com Gamificação

O módulo de suporte **não altera** o scoring:
- Pontos continuam baseados em O.S. concluída
- Histórico de atendimento é apenas contexto operacional
- Gestor vê quem atendeu, não muda a pontuação retroativamente

### 3. Performance em Escala

Com 1.000+ O.S./dia:
- Fila precisa de índices em (regional, status, priority, created_at)
- Comentários usam partição por ticket
- Métricas em cache (Redis) com TTL de 1 min

### 4. Segurança

- Colaborador só vê O.S. sua regional (FK para regional_manager)
- Gestor vê sua equipe
- Admin vê tudo
- Auditoria de quem viu o quê (para dados sensíveis)

---

## Conclusão

O módulo de suporte transforma o sistema de:

**"Análise de dados históricos"** → **"Operação em tempo real"**

Mantendo a identidade de análise, mas agregando **capacidade operacional** que o negócio demanda.

Quer que eu detalhe alguma seção?
