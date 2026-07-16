"""One-off backfill: repopulate work_items.assigned_to from the displayName
already present in each row's raw_json, instead of the uniqueName (email)
that earlier syncs stored there.

No calls to the Azure DevOps API — raw_json already contains the original
payload, so this is a pure local data migration.

Run once, after deploying the ado_client.py displayName fix:
    cd apps/sync-service
    python -m scripts.backfill_assigned_to_display_name
"""

import json

from app import db

BATCH_SIZE = 200


def extract_display_name(raw_json: str) -> str | None:
    raw = json.loads(raw_json)
    assigned_to_field = raw.get("fields", {}).get("System.AssignedTo")
    if isinstance(assigned_to_field, dict):
        return assigned_to_field.get("displayName")
    if isinstance(assigned_to_field, str):
        return assigned_to_field
    return None


def run(conn) -> int:
    updated = 0
    with conn.cursor(name="backfill_assigned_to") as read_cur:
        read_cur.execute(
            "SELECT id, raw_json, assigned_to FROM work_items WHERE raw_json IS NOT NULL"
        )
        with conn.cursor() as write_cur:
            for work_item_id, raw_json, current_assigned_to in read_cur:
                display_name = extract_display_name(json.dumps(raw_json))
                if display_name != current_assigned_to:
                    write_cur.execute(
                        "UPDATE work_items SET assigned_to = %s WHERE id = %s",
                        (display_name, work_item_id),
                    )
                    updated += 1
                    if updated % BATCH_SIZE == 0:
                        conn.commit()
    conn.commit()
    return updated


if __name__ == "__main__":
    connection = db.get_connection()
    try:
        count = run(connection)
        print(f"Updated assigned_to on {count} work item(s).")
    finally:
        connection.close()
