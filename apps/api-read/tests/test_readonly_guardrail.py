import pathlib
import re

FORBIDDEN_SQL = re.compile(
    r"(?im)^\s*(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|UPSERT\s+INTO)\b"
)
APP_DIR = pathlib.Path(__file__).parent.parent / "app"


def test_no_write_sql_in_app_source():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_SQL.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert not offenders, "Write SQL found in apps/api-read (must be read-only):\n" + "\n".join(offenders)
