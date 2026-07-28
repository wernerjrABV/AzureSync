# Task 6 report — verify vertical slice and document operation

## Status

Completed. The three application READMEs document the capacity publication
workflow, eligibility rules, endpoint, page name, and Windows environment
variable setup. No application behavior was changed.

## Verification

### sync-service targeted capacity, schema, repository, and sync tests

Command:

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/azure_sync_test'
py -m pytest tests/test_capacity.py tests/test_db.py tests/test_repository.py tests/test_sync_service.py
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-8.3.3, pluggy-1.6.0
rootdir: C:\Projects\AzureSync\.worktrees\team-capacity-forecast\apps\sync-service
collected 56 items

tests\test_capacity.py ...............                                   [ 26%]
tests\test_db.py ......                                                  [ 37%]
tests\test_repository.py .....................                           [ 75%]
tests\test_sync_service.py ..............                                [100%]

============================= 56 passed in 8.48s =============================
```

### api-read repository, routes, and read-only guardrail tests

Command:

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/azure_sync_test'
py -m pytest tests/test_repository.py tests/test_routes.py tests/test_readonly_guardrail.py
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-8.3.3, pluggy-1.6.0
rootdir: C:\Projects\AzureSync\.worktrees\team-capacity-forecast\apps\api-read
collected 57 items

tests\test_repository.py .........................                       [ 43%]
tests\test_routes.py ...............................                     [ 98%]
tests\test_readonly_guardrail.py .                                       [100%]

============================= 57 passed in 10.28s =============================
```

### web-read tests

Command (the existing Node PATH workaround and `npm.cmd` avoid the local
PowerShell execution-policy block on `npm.ps1`):

```powershell
$env:Path='C:\Program Files\nodejs;' + $env:Path
npm.cmd test
```

Output:

```text
Test Files  1 failed | 7 passed (8)
Tests  9 failed | 61 passed (70)
Duration  15.58s
```

All nine failures are the known baseline `src/pages/SynchronizationPage.test.tsx`
failures. The Capacity & Flow tests passed as part of the seven passing test
files.

### web-read production build

Command:

```powershell
$env:Path='C:\Program Files\nodejs;' + $env:Path
npm.cmd run build
```

Output:

```text
> web-read@0.0.1 build
> tsc -b && vite build

✓ 2108 modules transformed.
✓ built in 7.72s
```

Vite emitted its existing chunk-size advisory: `index-DW-wYqtZ.js` is 743.64
kB before gzip, above the 500 kB warning threshold. The build exited 0.

### Whitespace check

Command:

```powershell
git diff --check
```

Output:

```text
(no output; exit code 0)
```

## Baseline concerns

The documented unrelated baseline failures remain outside this task:

- sync-service full-suite failures: the ADO expand expectation and the route
  test that expects a missing `AZURE_DEVOPS_API_KEY` environment value;
- web-read: the nine `SynchronizationPage` tests shown above.

The targeted sync-service and api-read capacity-related suites passed, and the
web production build passed.
