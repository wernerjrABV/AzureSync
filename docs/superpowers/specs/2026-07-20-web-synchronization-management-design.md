# Design: gerenciamento de sincronização no web-read

## Objetivo

Substituir a tela HTML atualmente servida pelo `sync-service` em `:5000` por uma tela de gerenciamento dentro do `web-read`. A nova tela terá cadastro completo de `area_paths`, acompanhamento de status e disparo manual de sincronizações sem bloquear a interface.

## Decisões arquiteturais

- `apps/sync-service` continua sendo o único writer do banco e dono da execução da sincronização.
- `repository.py` continua sendo o único arquivo que emite SQL de escrita.
- `sync_service.run_sync` continua responsável por locking, checkpoints, upserts, deletes, histórico, status e rollback.
- O `sync-service` passará a expor endpoints JSON de gerenciamento. O `api-read` permanece somente leitura e não será proxy dessas operações.
- O `web-read` chamará diretamente o `sync-service` usando `VITE_SYNC_SERVICE_BASE_URL`.
- A interface HTML/Jinja de `:5000` deixa de ser a interface oficial e será removida ou desativada; o processo do serviço permanece para API e scheduler.

## API de gerenciamento

Serão disponibilizados contratos JSON equivalentes a:

- `GET /api/area-paths`: lista configuração e status de cada área.
- `POST /api/area-paths`: cria uma área.
- `PUT /api/area-paths/<id>`: atualiza uma área.
- `DELETE /api/area-paths/<id>`: remove uma área.
- `POST /api/area-paths/<id>/sync`: inicia sincronização e retorna `202 Accepted`.

As respostas de área incluirão identificação, configuração (`organization`, `project`, `area_path`, `incluir_subpaths`, `ativo`, `intervalo_minutos`) e status (`is_running`, `last_sync_at`, `last_sync_status`, `last_sync_count`, `last_error_msg`).

O disparo manual será não bloqueante. Se a área já estiver executando, responderá `409`; se não existir, `404`. A execução em background usará o ciclo de vida próprio do sync-service e não compartilhará a conexão da requisição.

## Interface web

O `SideNav` receberá o item `Synchronization`. A página usará exclusivamente componentes do design system Astryx: não serão criados CSS customizado, estilos inline, `styled-components`, `emotion` ou folhas de estilo próprias.

Cada área exibirá organização, projeto, caminho, ativo/inativo, sub-paths, intervalo, última sincronização, quantidade processada, estado e erro quando presente. As ações serão sincronizar, editar e excluir.

Cadastro e edição usarão um modal Astryx reutilizável. Os padrões serão `incluir_subpaths=true`, `ativo=true` e `intervalo_minutos=60`. A exclusão exigirá confirmação.

Após iniciar uma sincronização, o botão correspondente será desabilitado e a tela fará polling da listagem até `is_running=false`. Ao concluir, exibirá sucesso, `auth_error` ou erro geral sem exigir reload manual. Erros de autenticação indicarão a necessidade de configurar `AZURE_DEVOPS_API_KEY`.

As páginas existentes de Work Items e Features Roadmap permanecerão inalteradas.

## Testes e verificação

Serão adicionados ou atualizados testes para:

- rotas JSON de listagem, criação, edição, exclusão e início;
- `404` para área inexistente e `409` para sincronização concorrente;
- validação de campos e valores booleanos;
- transição de polling de executando para sucesso, erro e `auth_error`;
- cliente TypeScript e renderização/interação da nova página;
- guardrail que mantém `api-read` sem SQL de escrita;
- build e testes do web, além da suíte relevante do sync-service e api-read.

## Critérios de aceite

1. O usuário consegue cadastrar, editar e excluir area paths no web.
2. O usuário consegue iniciar uma sincronização no web sem esperar a requisição terminar.
3. O web mostra o progresso lógico e o resultado final da sincronização por polling.
4. Nenhuma escrita é feita pelo web ou pelo api-read.
5. O serviço em `:5000` não precisa mais expor a tela HTML antiga.
6. A interface nova usa somente componentes Astryx.
