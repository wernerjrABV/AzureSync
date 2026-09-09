# sync-service

Sincroniza work items do Azure DevOps para PostgreSQL ou SQLite, por area
path. Este é o único serviço autorizado a escrever no banco.

## Execução

Na instalação padrão, use `scripts/run-all.ps1` na raiz instalada. Para
executar isoladamente:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\run.py
```

O token do Azure DevOps é configurado pela interface web e protegido para o
usuário atual do Windows.

## Testes

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/azure_sync_test'
pytest
```

Regras de escrita e transação estão documentadas em `docs/adr/0002-single-writer.md`.
