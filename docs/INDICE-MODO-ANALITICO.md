# 📚 Índice de Documentação - Modo Analítico (Operations)

## 📖 Documentos Disponíveis

### 1. **[modo-analitico-operacoes-completo.md](./modo-analitico-operacoes-completo.md)** - GUIA PRINCIPAL
**Tamanho:** ~1400 linhas | **Duração de leitura:** 45-60 min

**O que você encontra:**
- ✅ **Visão Geral e Objetivo** - Por que o módulo existe
- ✅ **Estrutura de Dados Completa** - Todas as 8 tabelas do banco de dados
  - OperationOrder, OperationImportRun, OperationBackfillJob
  - OperationTeamModel, OperationResponsibleAssignment
  - OperationSavedFilter, e mais...
- ✅ **Funcionalidades Principais** (Página por página)
  - Visão Geral (Dashboard)
  - SLA (Análise de Conformidade)
  - Calendário Operacional Mensal
  - Abertura (Análise de Demanda)
  - Torre de Controle Preventiva
  - Andamento (Backlog Aberto)
  - E mais...
- ✅ **Regras de Negócio Críticas** - 10 regras essenciais
- ✅ **Dados Extraíveis** - O que pode ser consultado
- ✅ **Hierarquias e Dimensões** - Como os dados se relacionam
- ✅ **Métricas e Indicadores** - KPIs e fórmulas
- ✅ **APIs e Endpoints** - Rotas REST completas
- ✅ **Permissões e Escopo** - Controle de acesso

**Ideal para:** Visão geral, compreensão do produto, arquitetura

---

### 2. **[modo-analitico-especificacoes-tecnicas.md](./modo-analitico-especificacoes-tecnicas.md)** - DETALHES TÉCNICOS
**Tamanho:** ~970 linhas | **Duração de leitura:** 30-40 min

**O que você encontra:**
- ✅ **Algoritmos de Cálculo** - Implementações exatas
  - SLA Técnico (ponderado, não simples)
  - Tempo Médio de Fechamento
  - Execução Efetiva
  - Classificação de Desempenho Diário
  - Desempenho Esperado (Control Tower)
  - Janela Customizada
- ✅ **Transformações de Dados**
  - Normalização de campos (IXC → DB)
  - Conversão de Timezone
  - Agregação de Payload JSON
- ✅ **Validações e Regras**
  - Período, Segurança, Sequência Temporal
- ✅ **Padrões de Query**
  - Agregação Multidimensional
  - Ranking com Limite
  - Operações de Join
- ✅ **Performance e Indexação**
  - Índices otimizados
  - Técnicas de query eficiente
- ✅ **Tratamento de Erros**
  - Retry exponencial para IXC
  - Logging e Auditoria

**Ideal para:** Desenvolvimento, debug, otimização

---

### 3. **[modo-analitico-exemplos-dados-extraiveis.md](./modo-analitico-exemplos-dados-extraiveis.md)** - EXEMPLOS PRÁTICOS
**Tamanho:** ~890 linhas | **Duração de leitura:** 30-40 min

**O que você encontra:**
- ✅ **Dados de Ordem Individual**
  - Exemplo completo de O.S. (42 campos)
  - Timeline de execução
- ✅ **Agregações Simples**
  - Dashboard de Visão Geral (Jul 2026)
  - Tendências (Day/Week/Month)
- ✅ **Análises Dimensionais**
  - SLA por Regional
  - Desempenho Individual (Colaborador)
- ✅ **Séries Temporais**
  - Calendário Mensal Operacional
  - Detalhe de Dia Específico
- ✅ **Indicadores de Risco**
  - Torre de Controle com dados reais
- ✅ **Exemplos de Query (SQL)**
  - 4 queries SQL práticas com resultados
  - SLA por Tipo Geral
  - Desempenho Diário por Colaborador
  - Backlog Envelhecido (Aging)
  - Taxa de Pressão por Assunto

**Ideal para:** Business Intelligence, análise de dados, reports

---

## 🎯 Como Usar Esta Documentação

### Por Função:

**👨‍💼 Gerente / Gestor Operacional**
1. Leia: **Documentação Completa** - Seção "Visão Geral" e "Funcionalidades Principais"
2. Explore: **Exemplos Práticos** - Veja dados reais do seu negócio
3. Referência: **Documentação Completa** - Seção "Métrics e Indicadores"

**👨‍💻 Desenvolvedor Backend**
1. Comece: **Documentação Completa** - Seção "Estrutura de Dados"
2. Aprofunde: **Especificações Técnicas** - Seção "Algoritmos de Cálculo"
3. Implemente: **Especificações Técnicas** - Seção "Padrões de Query"
4. Otimize: **Especificações Técnicas** - Seção "Performance"

**👨‍🎨 Desenvolvedor Frontend**
1. Comece: **Documentação Completa** - Seção "APIs e Endpoints"
2. Explore: **Exemplos Práticos** - Veja estrutura de respostas
3. Implemente: Use exemplos JSON como mock data

**📊 Analista de Dados / BI**
1. Comece: **Exemplos Práticos** - Seção "Agregações Simples"
2. Aprofunde: **Exemplos Práticos** - Seção "Queries SQL"
3. Crie: Use as queries como base para suas análises customizadas

**🔐 Arquiteto / Tech Lead**
1. Leia: **Documentação Completa** - TUDO
2. Aprove: **Especificações Técnicas** - Performance e Segurança
3. Monitore: **Documentação Completa** - Integração com Gamificação

---

## 📋 Mapa Mental Rápido

```
Modo Analítico (Operations)
│
├── 📊 DADOS
│   ├── Ordem (42 campos)
│   ├── Período (01/05/26 - hoje)
│   └── Timezone (America/Porto_Velho)
│
├── 🔗 ESTRUTURA
│   ├── 8 tabelas principais
│   ├── 20+ dimensões de análise
│   └── Hierarquias multinível
│
├── 📈 FUNCIONALIDADES
│   ├── Visão Geral (Dashboard)
│   ├── SLA (Conformidade)
│   ├── Calendário (Produção diária)
│   ├── Abertura (Demanda)
│   ├── Torre de Controle (Risco)
│   ├── Andamento (Backlog)
│   └── Detalhes (Drill-through)
│
├── 📊 MÉTRICAS
│   ├── SLA Técnico (%)
│   ├── Tempo Médio (horas)
│   ├── Pressão (ratio)
│   ├── Backlog Aging (dias)
│   └── Desvio (%)
│
├── 🔐 SEGURANÇA
│   ├── Permissão: operations:read
│   ├── Escopo: Regional
│   └── Auditoria: Total
│
└── 🔌 INTEGRAÇÃO
    ├── IXC (Origem dos dados)
    └── Gamificação (Consumidor)
```

---

## 🔍 Checklist de Implementação

### MVP (Fase 1-2)
- [x] Fundação (Registro, Migrations, Ingestão)
- [x] Visão Geral (Dashboard, Filtros, Detalhe)
- [x] SLA (Tabela hierárquica)
- [x] Abertura (Analytics com Torre de Controle)
- [x] Andamento (Backlog aberto)
- [x] Calendário (Desempenho mensal)

### Próximas Fases
- [ ] Garantia (Análise de 30 dias)
- [ ] Internas (Projetos/POP)
- [ ] Snapshots (Histórico de backlog)
- [ ] Projeção para Gamificação

---

## 📞 Referências Cruzadas

### Dentro da Documentação
- **Documentação Completa** → Especificações Técnicas: Cada métrica é detalhada
- **Especificações Técnicas** → Exemplos Práticos: Cada algoritmo tem exemplo SQL
- **Exemplos Práticos** → Documentação Completa: Cada dado é explicado

### Fora da Documentação
- **PRD Original**: `/docs/prd_modulo_operacao_analitica.md`
- **Código Backend**: `/backend/app/modules/operations/`
- **Código Frontend**: `/frontend/components/operations/`

---

## 📈 Estatísticas da Documentação

| Documento | Linhas | Palavras | Seções | Exemplos |
|-----------|--------|----------|--------|----------|
| Completo | ~1400 | ~9500 | 10 | Conceituais |
| Técnicas | ~970 | ~6800 | 6 | Code snippets |
| Exemplos | ~890 | ~7200 | 6 | JSON + SQL |
| **TOTAL** | **~3260** | **~23500** | **22** | **50+** |

---

## 🎓 Histórico de Revisões

| Versão | Data | Autor | Alterações |
|--------|------|-------|-----------|
| 1.0 | 28/07/2026 | Claude Code | Documentação inicial completa |

---

## 💡 Dicas de Navegação

1. **Use Ctrl+F** para buscar dentro de cada documento
2. **Abra em abas separadas** para comparar documentos
3. **Imprima a Visão Geral** para ter como referência
4. **Mantenha os Exemplos próximos** ao código durante desenvolvimento
5. **Consulte as Queries** ao criar relatórios

---

## 🤝 Contribuições

Se encontrar:
- ❌ Erros ou inconsistências
- 🔍 Pontos obscuros
- 💬 Sugestões de melhoria
- 📝 Documentação faltante

**Faça um PR ou abra uma issue!**

---

## 📞 Suporte

Para dúvidas sobre:
- **Produto/Regras de Negócio** → Documentação Completa
- **Implementação/Código** → Especificações Técnicas
- **Análise/Dados** → Exemplos Práticos

---

**Última atualização:** 28/07/2026  
**Versão da documentação:** 1.0  
**Status:** ✅ Documentado até Fase 4 (Calendário + Modelos)
