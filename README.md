# Azure DevOps Sync Monorepo

Aplicação local para sincronizar work items do Azure DevOps. O
`apps/sync-service` é o único app autorizado a escrever no banco; consulte
`docs/architecture/monorepo-architecture.md` para a arquitetura completa.

## Instalação no Windows

Requisitos: Windows 10/11 x64, PowerShell 5.1+, Python 3.12+ e Node.js 22+.

Como este repositório é privado, autentique o GitHub CLI e clone o projeto:

```powershell
gh auth login
gh repo clone wernerjrABV/AzureSync "$env:LOCALAPPDATA\AzureSync\app"
cd "$env:LOCALAPPDATA\AzureSync\app"
& .\scripts\install.ps1
```

O instalador reutiliza o clone local, cria ambientes Python isolados, instala
as dependências com `pip` e instala o frontend com `npm ci`. Nenhum executável
compilado é baixado ou gerado.

Depois da instalação:

```powershell
& "$env:LOCALAPPDATA\AzureSync\app\scripts\run-all.ps1"
```

Para parar os serviços:

```powershell
& "$env:LOCALAPPDATA\AzureSync\app\scripts\stop-all.ps1"
```

A interface abre em http://127.0.0.1:5173. Configure o token do Azure DevOps
na tela Synchronization; ele é protegido para o usuário atual do Windows e
não é salvo em `.env`. Logs ficam na pasta `logs` da instalação.

Para instalar outra versão ou branch, execute o instalador novamente.

## Execução a partir de um clone

```powershell
gh repo clone wernerjrABV/AzureSync
cd AzureSync
& .\scripts\install.ps1 -InstallRoot (Join-Path $PWD 'local-install')
& .\local-install\scripts\run-all.ps1
```

O instalador também pode ser apontado para uma branch específica com
`-Branch nome-da-branch`.

## Desenvolvimento

O sync service usa `DATABASE_URL` quando configurado e SQLite como fallback
local. Para instalar e executar apenas esse serviço:

```powershell
cd apps/sync-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\run.py
```

Para testes que usam PostgreSQL:

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/azure_sync_test'
cd apps/sync-service
pytest
```

## Layout

```text
apps/sync-service/  único escritor do banco e sincronizador ADO
apps/api-read/      API somente leitura
apps/web-read/      frontend React
packages/           contratos e documentação compartilhados
docs/               arquitetura, ADRs e planos
scripts/            instalação e execução local no Windows
```

## Governança

- Decisões de arquitetura: `docs/adr/`
- Regra de único escritor: `docs/adr/0002-single-writer.md`
- Planos e especificações: `docs/superpowers/`
