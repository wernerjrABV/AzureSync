import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import get_sync_service_base_url


@dataclass(frozen=True)
class SyncServiceResponse:
    status_code: int
    json_body: object | None


class SyncServiceUnavailable(Exception):
    pass


class SyncServiceClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_sync_service_base_url()).rstrip("/")

    def request(
        self, method: str, path: str, json_body: object | None = None
    ) -> SyncServiceResponse:
        data = None
        headers = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urlopen(request) as response:
                return SyncServiceResponse(response.status, _decode_json(response.read()))
        except HTTPError as error:
            return SyncServiceResponse(error.code, _decode_json(error.read()))
        except URLError as error:
            raise SyncServiceUnavailable() from error


def _decode_json(body: bytes) -> object | None:
    return json.loads(body) if body else None
