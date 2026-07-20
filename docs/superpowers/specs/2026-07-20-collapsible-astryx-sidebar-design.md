# Sidebar retraída por padrão no web-read

## Objetivo

Fazer a sidebar do `apps/web-read` iniciar retraída em todo carregamento da aplicação,
mantendo a possibilidade de expandi-la e retraí-la pelo controle nativo do Astryx.

## Decisão

Configurar o `SideNav` com a API oficial não controlada:

```tsx
collapsible={{defaultIsCollapsed: true}}
```

O Astryx continuará responsável pelo estado, pelo botão de alternância, pela
acessibilidade e pelo layout icon-only quando retraído. Não haverá persistência em
`localStorage` nem estado adicional no `App`.

## Escopo e comportamento

- Alterar somente a composição existente de `SideNav` em `apps/web-read/src/App.tsx`.
- O estado inicial será retraído a cada montagem/carregamento da aplicação.
- O botão oficial do Astryx permanecerá habilitado para alternância manual.
- Os itens de navegação continuarão funcionando e mantendo a seleção atual.
- Nenhum CSS customizado, estilo inline ou componente visual novo será introduzido.

## Verificação

Adicionar um teste de regressão no frontend que monte o shell com a sidebar configurada
e confirme o estado inicial retraído por meio do comportamento/atributos públicos do
componente. Executar o teste frontend e o build TypeScript/Vite.

