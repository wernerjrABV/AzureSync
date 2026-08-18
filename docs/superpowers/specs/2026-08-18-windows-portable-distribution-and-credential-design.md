# Design: distribuição portátil Windows e credencial do Azure DevOps no SQLite

## Objetivo

Entregar o AzureSync como um pacote portátil e autossuficiente para Windows
corporativo x64. O usuário final deve conseguir extrair um arquivo ZIP,
executar `AzureSync.exe` e usar o sistema em `http://127.0.0.1:5173` sem ter
Python, Node.js, npm, o repositório ou as dependências de desenvolvimento na
máquina.

O mesmo trabalho também move a configuração do PAT do Azure DevOps para a
página de sincronização. O PAT deixa de ser lido de `.env`, é protegido pelo
Windows DPAPI no escopo do usuário atual e é persistido no banco usado pelo
`sync-service`.

## Decisões confirmadas

- A plataforma distribuída é exclusivamente Windows x64.
- Cada instalação é usada por um único usuário do Windows.
- A entrega é uma pasta portátil compactada como ZIP, não um instalador e não
  um executável único autoextraível.
- Python e Node.js são dependências apenas da máquina de build.
- O pacote usa SQLite em `%LOCALAPPDATA%\AzureSync\data\azure_sync.sqlite3`.
- O frontend continua usando exclusivamente componentes Astryx.
- O `sync-service` continua sendo o único escritor do banco, e
  `repository.py` continua sendo o único arquivo com SQL de escrita.
- O PAT nunca é incluído no pacote, em argumentos de processo, em variáveis de
  ambiente, em logs ou em respostas HTTP.

## Arquitetura do pacote

O artefato terá esta composição lógica:

```text
AzureSync-win-x64/
  AzureSync.exe
  StopAzureSync.exe
  _internal/
    sync-service.exe
    api-read.exe
    web/
    runtimes e bibliotecas empacotadas
```

Os nomes e subdiretórios internos podem ser ajustados pelo arquivo de build,
mas somente `AzureSync.exe` e `StopAzureSync.exe` fazem parte da interface
operacional do usuário.

### Processos e portas

`AzureSync.exe` é um launcher Windows sem console visível. Ele:

1. adquire um mutex nomeado por usuário para garantir instância única;
2. se outra instância estiver saudável, abre o navegador e encerra a segunda
   invocação;
3. cria as pastas de dados, logs e estado em `%LOCALAPPDATA%\AzureSync`;
4. inicia `sync-service.exe` em `127.0.0.1:5000`;
5. inicia `api-read.exe` em `127.0.0.1:5173`;
6. consulta os health checks a cada 250 ms por até 30 segundos;
7. abre `http://127.0.0.1:5173` somente após ambos estarem saudáveis; e
8. permanece ativo para monitorar e possuir os processos filhos.

Os processos filhos pertencem a um Windows Job Object configurado para
encerrá-los quando o launcher termina. Isso evita serviços órfãos após queda ou
encerramento forçado do launcher.

`StopAzureSync.exe` sinaliza a instância pertencente ao mesmo usuário. O
launcher solicita o encerramento dos servidores e do scheduler, aguarda por
até 30 segundos uma sincronização em andamento e, ao exceder esse período,
encerra os processos filhos. Ele nunca encerra um processo apenas com base em
um PID não validado.

### Frontend compilado

O Vite permanece como servidor de desenvolvimento, mas não participa do
runtime distribuído. O build React é copiado para `_internal/web` e servido
pelo `api-read` na mesma origem das APIs públicas. Rotas que não começam com
`/api` nem correspondem a um asset existente retornam o `index.html`,
permitindo navegação da SPA.

No pacote, os clientes do frontend usam URLs relativas. No desenvolvimento,
as variáveis Vite existentes continuam permitindo `web-read` em `:5173` e
`api-read` em `:5001`.

O `api-read` continua sem SQL de escrita. As operações mutáveis e as novas
rotas de credencial são apenas encaminhadas ao `sync-service`, que fica
limitado ao loopback em `:5000`.

### Dados mutáveis

Nenhum dado de usuário é escrito dentro da pasta extraída:

```text
%LOCALAPPDATA%\AzureSync\
  data\azure_sync.sqlite3
  logs\
  run\
```

O launcher passa a configuração de runtime diretamente aos processos filhos.
O modo portátil sempre seleciona o SQLite acima, independentemente de um
arquivo `.env` próximo ao executável. Em desenvolvimento, o suporte atual a
PostgreSQL, `DATABASE_URL` e demais opções de `.env` permanece disponível.
`AZURE_DEVOPS_API_KEY` é a única configuração removida integralmente do
`.env`.

## Credencial do Azure DevOps

### Persistência

O schema do `sync-service` ganha uma tabela de configuração compatível com
SQLite e PostgreSQL:

```text
app_settings
  key                TEXT PRIMARY KEY
  encrypted_value    TEXT NOT NULL
  updated_at          TIMESTAMP NOT NULL
```

O registro do PAT usa uma chave estável, por exemplo `azure_devops_api_key`.
`encrypted_value` contém Base64 do blob produzido por `CryptProtectData`,
nunca o PAT em texto puro. A proteção usa DPAPI `CurrentUser`, portanto somente
o mesmo usuário do Windows na mesma instalação consegue chamar
`CryptUnprotectData` com sucesso.

As funções de leitura, upsert e exclusão do setting ficam em
`apps/sync-service/app/repository.py`. Nenhum outro arquivo emite SQL de
escrita. Uma camada de credenciais separada coordena Base64 e DPAPI chamando
essas funções; ela não contém SQL.

O protetor é uma dependência injetável. Produção usa DPAPI por `ctypes`, sem
exigir `pywin32`; testes usam um protetor determinístico e não dependem do
perfil Windows do executor de CI.

### API

O `sync-service` expõe:

- `GET /api/settings/azure-devops`: retorna somente `configured` e
  `updated_at`;
- `PUT /api/settings/azure-devops`: recebe `{ "api_key": "..." }`, protege e
  substitui a credencial em uma transação; e
- `DELETE /api/settings/azure-devops`: remove a credencial armazenada.

O PUT rejeita corpo ausente, valor vazio e valor acima de 4.096 caracteres,
sem reproduzir o conteúdo recebido na mensagem de erro. GET, PUT e DELETE
nunca retornam o PAT, o ciphertext ou parte deles.

O `api-read` encaminha essas três rotas pelo cliente interno existente, assim
como já faz com as mutações de `area_paths`. O frontend acessa somente a origem
pública em `:5173`.

### Uso durante a sincronização

O `AdoClient` deixa de consultar `app.config.get_ado_api_key`. Tanto o worker
manual quanto o scheduler obtêm a credencial pelo serviço de credenciais e a
entregam explicitamente ao cliente.

Ausência da credencial, falha do DPAPI e PAT rejeitado pelo Azure DevOps são
convertidos em `AdoAuthError` durante a execução coberta por
`sync_service.run_sync`. Assim, o pipeline existente continua responsável por
rollback, `last_sync_status=auth_error`, mensagem de erro, liberação do lock e
registro no histórico de sincronização.

A credencial descriptografada existe somente em memória durante a criação e o
uso do cliente. Mensagens de erro podem informar que a credencial está ausente,
ilegível ou foi rejeitada, mas nunca incluem seu valor.

## Interface de sincronização

A página `SynchronizationPage` ganha uma seção feita exclusivamente com
componentes Astryx existentes. Ela apresenta:

- badge de estado `Configured` ou `Not configured`;
- campo de senha vazio para inserir ou substituir o PAT;
- ação `Save credential`;
- ação `Remove credential`, com confirmação; e
- feedback de carregamento, sucesso e falha.

O valor salvo nunca volta a preencher o campo. Ao receber `auth_error`, os
cards de sincronização orientam o usuário a atualizar a credencial nessa mesma
página, em vez de mencionar `AZURE_DEVOPS_API_KEY` ou `.env`.

Não serão adicionados CSS customizado, CSS inline, `styled-components`,
`emotion` ou componentes visuais externos ao Astryx.

## Tratamento de falhas

O launcher não abre o navegador quando uma porta está ocupada, um executável
interno está ausente, o diretório de dados não pode ser criado ou um serviço
não passa no health check dentro do timeout. Nesses casos ele:

1. encerra qualquer filho iniciado parcialmente;
2. grava detalhes técnicos em `%LOCALAPPDATA%\AzureSync\logs`;
3. mostra uma caixa de diálogo nativa do Windows com mensagem curta e caminho
   do log; e
4. encerra com código diferente de zero.

Se um serviço cair durante o uso, o launcher registra a saída, encerra o outro
serviço e informa o usuário. Reinício automático não faz parte desta entrega,
pois poderia ocultar uma falha persistente ou interferir com uma sincronização.

Erros da API são apresentados na página por componentes Astryx. Nenhum log de
launcher, serviço ou frontend pode registrar corpo do endpoint de credencial,
ciphertext ou PAT descriptografado.

## Build e artefatos

Um script `scripts/build-portable.ps1`, executado na máquina de build Windows
x64, realiza de forma reproduzível:

1. validação de Windows x64, Python x64 3.12 ou superior e Node.js x64 22 ou
   superior na máquina de build;
2. criação de ambiente Python isolado e instalação das dependências fixadas;
3. instalação reproduzível do frontend com `npm ci`;
4. execução das suítes Python e React;
5. build de produção do Vite;
6. empacotamento `onedir` do launcher e serviços com PyInstaller;
7. montagem de `dist\AzureSync-win-x64`;
8. smoke test dos binários empacotados;
9. geração de `dist\AzureSync-win-x64.zip`; e
10. geração do hash SHA-256 do ZIP.

O script não instala Python nem Node.js na máquina do usuário final. A pasta
distribuída não contém o checkout do repositório; módulos Python ficam no
formato empacotado pelo PyInstaller e o frontend contém apenas assets de
produção. Isso reduz exposição acidental do código, mas não é tratado como
proteção contra engenharia reversa.

O build funciona sem certificado, sujeito às políticas locais de SmartScreen e
antivírus. O script oferece um ponto opcional de assinatura Authenticode quando
a empresa fornecer certificado e `signtool`. Certificados, senhas e chaves de
assinatura nunca entram no repositório nem no ZIP.

## Estratégia de testes

### Sync service

- schema `app_settings` em SQLite e PostgreSQL;
- repository de leitura, substituição e remoção da configuração;
- proteção, desproteção e falhas por meio do protetor injetado;
- contratos GET, PUT e DELETE sem exposição do segredo;
- credencial ausente ou ilegível resultando em `auth_error`;
- worker manual e scheduler usando a credencial persistida; e
- regressão das garantias de lock, rollback, checkpoint e history backfill.

### API read

- encaminhamento das três rotas, preservando status e JSON;
- `503` quando o `sync-service` estiver indisponível;
- guardrail de ausência de SQL de escrita; e
- entrega de assets e fallback do `index.html` sem interceptar rotas `/api`.

### Web read

- carregamento do estado sem receber o PAT;
- salvamento, substituição, remoção e estados de erro;
- campo de senha sempre vazio após salvar/recarregar;
- orientação atualizada em `auth_error`;
- uso exclusivo de componentes Astryx; e
- testes, typecheck e build de produção existentes.

### Launcher e pacote

- instância única e segunda abertura apenas reabrindo o navegador;
- criação dos caminhos em `%LOCALAPPDATA%`;
- health checks, timeout, porta ocupada e filho que termina cedo;
- encerramento solicitado e encerramento por Job Object;
- logs sem material de credencial;
- smoke test do ZIP extraído; e
- execução dos binários com `python`, `node`, `npm` e o checkout ausentes do
  `PATH` e do diretório de execução.

## Critérios de aceite

1. Em Windows x64, o usuário extrai o ZIP, executa `AzureSync.exe` e acessa o
   sistema em `http://127.0.0.1:5173` sem instalar Python ou Node.js.
2. Uma segunda execução não duplica serviços e apenas abre a aplicação.
3. `StopAzureSync.exe` encerra apenas a instância do mesmo usuário e não deixa
   processos órfãos.
4. SQLite, logs e estado sobrevivem à substituição da pasta distribuída.
5. O PAT é configurado, substituído e removido na página de sincronização.
6. O SQLite nunca contém o PAT em texto puro; o valor persistido é protegido
   por DPAPI `CurrentUser`.
7. Nenhuma API, log ou campo recarregado no navegador revela PAT ou ciphertext.
8. Sincronização manual e agendada usam a credencial persistida; ausência,
   falha de proteção e rejeição pelo ADO aparecem como `auth_error`.
9. `sync-service` e `repository.py` preservam as regras de escritor único e SQL
   de escrita exclusivo.
10. O build produz pasta, ZIP, hash SHA-256 e evidência de smoke test.

## Fora de escopo

- suporte a macOS, Linux ou Windows ARM;
- instalador MSI, atualização automática ou publicação no Portal da Empresa;
- armazenamento compartilhado entre usuários do Windows;
- recuperação do PAT em outra máquina ou outro perfil de usuário;
- ocultação absoluta contra engenharia reversa; e
- fornecimento ou gerenciamento de certificado corporativo de assinatura.
