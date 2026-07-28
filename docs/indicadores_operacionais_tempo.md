# Indicadores operacionais de tempo

## Contratos atuais

- **TMA de atendimento:** média de `início da execução → finalização`. Mede o tempo efetivamente empregado no atendimento.
- **Tempo em atendimento:** soma de `início da execução → finalização` no recorte.
- **Deslocamento médio:** média de `status de início do deslocamento → início da execução`. Não usa GPS.
- **Espera até deslocamento:** média de `abertura → status de início do deslocamento`.
- **Ciclo total médio:** média de `abertura → finalização`.
- **Finalizações fora da jornada configurada:** compara o horário de fechamento da O.S. com a jornada do modelo de equipe aplicável ao dia útil, sábado ou domingo. O indicador não afirma a existência de hora extra trabalhista.

## Onde cada indicador deve aparecer

O detalhe diário e o detalhe mensal do colaborador mostram somente TMA, tempo em atendimento, deslocamento e SLA. Espera até deslocamento e ciclo total são indicadores de fluxo da operação e ficam na Visão Geral, sempre agregados e respeitando os filtros.

## Futura aba de agendamento

Quando a agenda operacional for implementada, a espera deve ser decomposta em:

1. abertura → horário agendado;
2. horário agendado → início do deslocamento;
3. início do deslocamento → início da execução;
4. início da execução → finalização.

Essa decomposição evita atribuir ao técnico atrasos anteriores ao horário planejado e deve considerar reagendamentos e ausência de timestamps como estados explicitamente não mensuráveis.
