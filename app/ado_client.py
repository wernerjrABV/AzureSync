import datetime
import json
import time

import requests

from app.config import get_ado_api_key

RETRY_DELAYS = [5, 15, 30]
API_VERSION = "7.1"


class AdoAuthError(Exception):
    pass


class AdoRetryExhaustedError(Exception):
    pass


class AdoClient:
    def __init__(self, organization: str, project: str, pat: str | None = None):
        self.organization = organization
        self.project = project
        self.pat = pat or get_ado_api_key()

    def _auth(self):
        return ("", self.pat)

    def _post_with_retry(self, url: str, json_body: dict) -> dict:
        last_status = None
        for attempt in range(len(RETRY_DELAYS)):
            response = requests.post(url, json=json_body, auth=self._auth())

            if response.status_code == 401:
                raise AdoAuthError(f"Azure DevOps rejected credentials (401) calling {url}")

            if response.status_code in (429, 500, 502, 503, 504):
                last_status = response.status_code
                delay = RETRY_DELAYS[attempt]
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, int(retry_after))
                    except ValueError:
                        pass
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                try:
                    detail = response.json().get("message", response.text)
                except ValueError:
                    detail = response.text
                raise requests.HTTPError(
                    f"{response.status_code} error calling {url}: {detail}", response=response
                )
            return response.json()

        raise AdoRetryExhaustedError(
            f"Exhausted retries calling {url}, last status={last_status}"
        )

    def _wiql_query(self, query: str) -> list[int]:
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit/wiql?api-version={API_VERSION}"
        body = self._post_with_retry(url, {"query": query})
        return [item["id"] for item in body.get("workItems", [])]

    def get_all_ids(self, area_path: str, incluir_subpaths: bool) -> list[int]:
        operator = "UNDER" if incluir_subpaths else "="
        query = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = "
            f"'{self.project}' AND [System.AreaPath] {operator} '{area_path}'"
        )
        return self._wiql_query(query)

    def get_changed_ids(self, area_path: str, incluir_subpaths: bool, since=None) -> list[int]:
        operator = "UNDER" if incluir_subpaths else "="
        query = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = "
            f"'{self.project}' AND [System.AreaPath] {operator} '{area_path}'"
        )
        if since is not None:
            # This project uses date precision, not datetime precision: WIQL rejects a time
            # component ("You cannot supply a time with the date..."). Use >= on the date only,
            # re-fetching that day's items is harmless since upserts are idempotent.
            query += f" AND [System.ChangedDate] >= '{since.strftime('%Y-%m-%d')}'"
        return self._wiql_query(query)

    def get_work_items_batch(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []

        url = f"https://dev.azure.com/{self.organization}/_apis/wit/workitemsbatch?api-version={API_VERSION}"

        results = []
        for start in range(0, len(ids), 200):
            chunk = ids[start : start + 200]
            body = self._post_with_retry(url, {"ids": chunk, "$expand": "fields"})
            for raw in body.get("value", []):
                results.append(self._map_work_item(raw))
        return results

    @staticmethod
    def _map_work_item(raw: dict) -> dict:
        fields = raw.get("fields", {})
        assigned_to_field = fields.get("System.AssignedTo")
        assigned_to = None
        if isinstance(assigned_to_field, dict):
            assigned_to = assigned_to_field.get("uniqueName")
        elif isinstance(assigned_to_field, str):
            assigned_to = assigned_to_field

        changed_date_raw = fields.get("System.ChangedDate")
        changed_date = None
        if changed_date_raw:
            changed_date = datetime.datetime.strptime(
                changed_date_raw.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S"
            )

        return {
            "id": raw["id"],
            "title": fields.get("System.Title"),
            "work_item_type": fields.get("System.WorkItemType"),
            "state": fields.get("System.State"),
            "assigned_to": assigned_to,
            "changed_date": changed_date,
            "raw_json": json.dumps(raw),
        }
