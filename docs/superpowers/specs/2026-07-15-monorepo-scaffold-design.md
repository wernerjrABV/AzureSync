# Design: Monorepo Scaffold + Reposicionamento do sync-service

## Escopo

Este design cobre **apenas** a Etapa 1-3 do roadmap corporativo (diagnóstico,
scaffold de monorepo, reposicionamento do app existente). `api-read`,
`web-read`, revisão de índices e documentação de ADR/lifecycle completa ficam
como specs futuras e separadas — este projeto é grande demais para uma única
spec, e o valor imediato está em ter a estrutura pronta sem quebrar o app
atual.

## Estado atual (diagnóstico)

- App Flask único na raiz do repo: `run.py` + pacote `app/`
  (`ado_client.py`, `db.py`, `repository.py`, `routes.py`, `scheduler.py`,
  `sync_service.py`, `config.py`, `templates/`, `static/`).
- Dependências: `flask`, `psycopg[binary]`, `apscheduler`, `requests`,
  `pytest` — declaradas em `requirements.txt` na raiz, sem lockfile.
- Testes em `tests/`, usam `TEST_DATABASE_URL` via `tests/conftest.py`.
- Env vars lidas do SO (Windows), não de `.env`.
- Sem CI, sem Docker, sem infra declarada hoje.
- `app` é um pacote plano — nenhum import relativo problemático, todos os
  imports internos usam `app.X`, o que torna a movimentação mecânica.
- Já existe único writer de fato (só este app grava no Postgres); a mudança
  aqui é tornar essa regra **explícita e estrutural**, não mudar
  comportamento.

## Estrutura proposta

```
apps/
  sync-service/
    app/                  (movido, intacto)
    run.py                (movido, intacto)
    requirements.txt      (movido, intacto)
    tests/                (movido, intacto)
    README.md             (novo — documenta ownership: único writer)
packages/
  shared-contracts/       (placeholder + README explicando propósito futuro)
  shared-config/          (placeholder + README)
  shared-observability/   (placeholder + README)
  shared-db-guidelines/   (placeholder + README)
docs/
  architecture/
    monorepo-architecture.md   (novo)
  adr/
    0001-monorepo.md           (novo)
    0002-single-writer.md      (novo)
  standards/
    technology-lifecycle.md    (novo, resume regra semestral/V-2)
  superpowers/            (inalterado — específico do processo de trabalho)
README.md                 (raiz, atualizado com mapa do monorepo)
```

`api-read/` e `web-read/` **não são criados** nesta etapa — apenas
mencionados no roadmap do README raiz e no `monorepo-architecture.md` como
próximos passos, para não criar esqueletos que ficariam obsoletos antes de
suas próprias specs.

## O que muda mecanicamente

1. `git mv app apps/sync-service/app`
2. `git mv run.py apps/sync-service/run.py`
3. `git mv requirements.txt apps/sync-service/requirements.txt`
4. `git mv tests apps/sync-service/tests`
5. Nenhuma alteração de código Python é necessária — os imports já são
   absolutos (`from app import db`, etc.) e continuam funcionando porque
   `run.py` e `app/` mantêm a mesma posição relativa entre si.
6. Comandos do `CLAUDE.md` são atualizados para refletir o novo `cwd`
   (`cd apps/sync-service && python run.py`, etc.) — documentado no novo
   `apps/sync-service/README.md` e no `CLAUDE.md` raiz/local.
7. Mudanças não commitadas existentes em `ado_client.py`, `db.py`,
   `repository.py` são preservadas durante o `git mv` (movidas junto, não
   descartadas).

## Guardrails de fronteira (o que dá pra fazer *hoje*, sem novo código)

Como `api-read` ainda não existe, os guardrails desta etapa são documentais,
não técnicos:

- `apps/sync-service/README.md` declara explicitamente: "Este é o único
  serviço autorizado a executar INSERT/UPDATE/DELETE/UPSERT no banco."
- `docs/adr/0002-single-writer.md` registra a decisão e o motivo.
- `docs/architecture/monorepo-architecture.md` desenha o fluxo
  `sync-service -> Postgres -> (futuro) api-read -> (futuro) web-read` e
  marca a regra do único writer como não-negociável.
- Guardrail técnico de CI (ex: lint que bloqueia SQL de escrita fora de
  `apps/sync-service`) fica para quando `api-read` existir de fato — não há
  o que impor ainda.

## Testes / verificação

- Após mover, rodar a suíte de testes a partir do novo caminho
  (`cd apps/sync-service && pytest`) para confirmar que nada quebrou.
- Rodar `python run.py` a partir do novo caminho para confirmar que a app
  sobe normalmente.

## Fora de escopo (specs futuras)

- Esqueleto do `apps/api-read` (read-only backend)
- Esqueleto do `apps/web-read` (frontend React)
- Revisão de índices do banco (`docs/architecture/database-index-review.md`)
- CI real (GitHub Actions) e placeholders de SonarQube/Snyk/Apiiro/Datadog
- Conteúdo real dentro de `packages/*` (hoje só placeholders com README)
