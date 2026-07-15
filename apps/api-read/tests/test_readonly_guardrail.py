import pathlib
import re

FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|UPSERT)\b", re.IGNORECASE)
APP_DIR = pathlib.Path(__file__).parent.parent / "app"


def test_no_write_sql_in_app_source():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert not offenders, "Write SQL found in apps/api-read (must be read-only):\n" + "\n".join(offenders)
