# web-read: adoção do Astryx design system (tema neutral)

## Objetivo

Tornar `apps/web-read` aderente ao design system Astryx (https://astryx.atmeta.com),
usando exclusivamente componentes nativos do pacote `@astryxdesign/core` com o tema
`@astryxdesign/theme-neutral`, sem nenhum CSS custom/estilizado. Aproveitar a migração
para reorganizar o layout da única página existente (lista de work items).

## Contexto atual

`apps/web-read` é uma app React 19 + Vite + TS com uma única página
(`WorkItemsListPage.tsx`) que renderiza HTML puro (table, select, input, button) sem
CSS algum. Ela consome `apps/api-read` via `services/apiReadClient.ts` para listar
work items com filtro por area path / tipo e paginação client-driven (page/pageSize).

## Pacotes

Adicionar como dependências de produção:
- `@astryxdesign/core` — biblioteca de componentes
- `@astryxdesign/theme-neutral` — tema neutro

Como dev dependency:
- `@astryxdesign/cli` — tooling (scaffold/lookup de componentes), não usado em runtime

## Setup de tema

Criar `src/index.css` (novo arquivo, importado em `main.tsx`) com, nesta ordem:

```css
@import '@astryxdesign/core/reset.css';
@import '@astryxdesign/core/astryx.css';
@import '@astryxdesign/theme-neutral/theme.css';
```

Como o projeto não tem CSS concorrente hoje, não é necessário `@layer` explícito além
do que os próprios pacotes já definem (eles são cascade-layered internamente).

## Layout

```
AppShell (variant="elevated", contentPadding={4})
├── topNav: TopNav > TopNavHeading (heading="Work Items")
└── children:
    Card
    ├── HStack (gap, filtros)
    │   ├── Selector (label="Area path", hasSearch, hasClear, options=areaPaths)
    │   └── TextInput (label="Type", hasClear, placeholder="e.g. Bug")
    ├── conteúdo condicional:
    │   ├── erro  -> Banner status="error" title="Error loading work items" description={mensagem}
    │   ├── loading -> Spinner centralizado (substitui a tabela)
    │   ├── vazio -> EmptyState title="No work items found"
    │   └── dados -> Table (density="balanced", dividers="rows", hasHover)
    │       colunas: ID, Title, Type, State (renderCell com Badge), Assigned To, Changed Date
    └── Pagination (variant="compact", page, onChange, totalItems=total, pageSize=50)
```

Sem `sideNav` (app de página única) e sem `mobileNav` customizado (deixar o default do
`AppShell`, que é seguro mesmo sem sideNav).

## Mapeamento de estado → componente

- `error` (string | null) → `Banner status="error"`
- `loading` (bool) → `Spinner` no lugar da tabela (Table não tem prop de loading nativa)
- `items.length === 0` (após load, sem erro) → `EmptyState`
- `items.length > 0` → `Table` + `Pagination`

State da coluna "State" renderizado com `Badge` (variant neutro, já que o app não tem
mapeamento de cores por status do Azure DevOps definido — usar `variant="neutral"` ou
o default do Badge, sem inventar semântica de cor não pedida).

## Fora de escopo

- Não alterar `apiReadClient.ts`, `models/*` ou o contrato com `apps/api-read`.
- Não adicionar sideNav, navegação multi-página, dark mode toggle, ou breadcrumbs —
  não existem outras páginas ainda.
- Não customizar cores/tokens do tema — usar `theme-neutral` como vem.

## Testes

Projeto não tem testes hoje (`apps/web-read` não tem devDependency de test runner).
Não introduzir suite de testes como parte desta migração — fora de escopo. Verificação
será manual: `npm run dev`, exercitar filtro por area path, filtro por tipo, paginação,
estado vazio (filtro que não bate nada) e estado de erro (parar a api-read).
