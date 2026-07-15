# Azure DevOps → PostgreSQL Sync — Design

## Objetivo
App local (Windows) que sincroniza work items do Azure DevOps por area path (com sub-paths opcionais) para PostgreSQL local existente. Primeira execução por area path = full load; execuções seguintes = delta (incremental), incluindo remoção de itens que saíram do escopo.

## Stack
- Python 3.12
- Flask (server-rendered, Jinja2) — UI simples de CRUD + botão de sync
- psycopg (v3) — acesso direto ao Postgres, sem ORM
- APScheduler (in-process) — dispara sync por intervalo configurado por area path
- `requests` — chamadas REST à API do Azure DevOps
- Credencial: variável de ambiente Windows `AZURE_DEVOPS_API_KEY` (PAT), usada via Basic Auth
- Sem Docker, sem filas, sem websocket, sem auth de usuário, sem UI sofisticada

## Modelo de dados
```sql
area_paths (
  id SERIAL PRIMARY KEY,
  organization TEXT NOT NULL,
  project TEXT NOT NULL,
  area_path TEXT NOT NULL,
  incluir_subpaths BOOLEAN NOT NULL DEFAULT TRUE,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  intervalo_minutos INTEGER NOT NULL DEFAULT 60,
  is_running BOOLEAN NOT NULL DEFAULT FALSE,
  last_sync_at TIMESTAMP,
  last_sync_status TEXT,          -- 'ok' | 'running' | 'auth_error' | 'error'
  last_sync_count INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

work_items (
  id INTEGER PRIMARY KEY,          -- work item id do Azure DevOps
  area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
  title TEXT,
  work_item_type TEXT,
  state TEXT,
  assigned_to TEXT,
  changed_date TIMESTAMP,
  raw_json JSONB,
  synced_at TIMESTAMP NOT NULL DEFAULT now()
);

sync_checkpoints (
  area_path_id INTEGER PRIMARY KEY REFERENCES area_paths(id),
  last_changed_date TIMESTAMP
);

sync_logs (
  id SERIAL PRIMARY KEY,
  area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  status TEXT,                     -- 'ok' | 'auth_error' | 'error'
  items_processed INTEGER,
  error_msg TEXT
);
```

## Estratégia de sync
Query WIQL usa `UNDER 'area_path'` quando `incluir_subpaths=true`, senão `=`.

Para toda execução (full ou delta) do job de uma area path:
1. **Lock**: marca `is_running=true`. Se já estava `true`, aborta imediatamente (não roda).
2. Busca lista completa de IDs atuais no escopo (WIQL somente com `[System.Id]`, sem filtro de data — consulta leve mesmo em milhares de itens).
3. Busca IDs novos/alterados desde o checkpoint (`[System.ChangedDate] > @checkpoint`, ou sem filtro na primeira execução).
4. Para os IDs alterados: busca em lotes de 200 via `workitemsbatch` → upsert em `work_items`.
5. **Remoção**: IDs presentes no banco (`work_items.area_path_id = X`) mas ausentes da lista atual (passo 2) → `DELETE` físico. Cobre itens excluídos no Azure DevOps e itens movidos para fora do area path/sub-paths.
6. Atualiza `sync_checkpoints.last_changed_date` com o maior `ChangedDate` retornado no lote.
7. Grava `sync_logs` (started_at, finished_at, status, items_processed, error_msg).
8. Atualiza `area_paths` (last_sync_at, last_sync_status, last_sync_count) e libera `is_running=false`.

## Erros e resiliência
- **401 Unauthorized** (token inválido/expirado): aborta sync, `last_sync_status='auth_error'`, grava mensagem em `sync_logs.error_msg`. UI exibe banner vermelho fixo no topo: "Token inválido/expirado — verifique AZURE_DEVOPS_API_KEY".
- **429 / 5xx**: retry com backoff fixo **5s → 15s → 30s** (3 tentativas); respeita header `Retry-After` se presente e maior que o backoff padrão. Esgotadas as tentativas → `last_sync_status='error'`.
- **Concorrência**: `is_running` funciona como lock por area path.
  - Botão "sincronizar agora" fica desabilitado na UI quando `is_running=true`, e o endpoint retorna erro (409) se chamado mesmo assim.
  - O scheduler pula silenciosamente o disparo agendado se `is_running=true` (log de skip opcional, sem falha).

## UI (Flask, server-rendered)
- Página única: tabela de area paths com colunas: organization, project, area_path, incluir sub-paths, ativo, intervalo, última sync, status, quantidade processada, ação (sincronizar agora / editar / excluir).
- Formulário simples (mesma página ou `/area-paths/new`) para criar/editar: organization, project, area_path, incluir_subpaths, ativo, intervalo_minutos.
- Banner de erro de autenticação global no topo quando qualquer area path está com `auth_error`.
- Sem autenticação de usuário (uso local).

## Fora de escopo
Docker, microservices, Redis, filas, websocket, autenticação de usuário, UI sofisticada, multi-usuário, soft-delete/histórico de itens removidos.
