# api-read

API Flask somente leitura sobre os dados populados pelo `sync-service`.

## Execução

Na instalação padrão, use `scripts/run-all.ps1` na raiz instalada. Para
executar isoladamente:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\run.py
```

O serviço escuta em `http://127.0.0.1:5001` por padrão. A porta pode ser
alterada com `API_READ_PORT`.

## Limites arquiteturais

- Não contém SQL de escrita, DDL ou migrações.
- Usa `DATABASE_URL` e o fallback SQLite configurado pelo serviço.
- A regra de único escritor está em `docs/adr/0002-single-writer.md`.
