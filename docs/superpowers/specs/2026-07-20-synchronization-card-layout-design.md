# Synchronization card layout

## Objetivo

Ajustar os cards da página de sincronização para destacar o estado ativo/inativo e exibir o intervalo de sincronização no formato `hh:mm`.

## Design

Cada card terá a Badge `Active`/`Inactive` em uma linha própria, alinhada à direita, acima do area path. O area path permanece abaixo, seguido pelos dados de organização e projeto.

O intervalo configurado em minutos será formatado como duração com horas e minutos de dois dígitos: `30` vira `00:30` e `90` vira `01:30`. O texto exibido será `Every HH:MM`.

A implementação reutilizará exclusivamente os componentes Astryx já usados pelo card (`HStack`, `VStack`, `Badge` e `Text`) e não introduzirá CSS customizado.

## Validação

Os testes da `SynchronizationPage` validarão a conversão de minutos para `hh:mm` e a presença do estado acima do area path no conteúdo renderizado. A suíte existente da aplicação web será executada após a alteração.
