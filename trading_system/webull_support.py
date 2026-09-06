"""Shared Webull OpenAPI helpers (errors, payload unwrap). No order placement."""

from __future__ import annotations

from typing import Any

# Official documented hosts (SDKs and Tools). Do not invent others.
WEBULL_PROD_HTTP = "api.webull.com"
WEBULL_SANDBOX_HTTP = "api.sandbox.webull.com"

_ACCOUNT_ID_KEYS = (
    "account_id",
    "accountId",
    "accountID",
    "id",
    "brokerage_account_id",
    "brokerageAccountId",
)

_ERROR_KEYS = ("error_code", "errorCode", "code", "error")


class WebullApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        action: str,
        status: int | None = None,
        error_code: str | None = None,
        endpoint: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.action = action
        self.status = status
        self.error_code = error_code
        self.endpoint = endpoint
        self.body = body

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "action": self.action,
            "status": self.status,
            "error_code": self.error_code,
            "endpoint": self.endpoint,
        }


def is_sandbox_endpoint(endpoint: str) -> bool:
    host = (endpoint or "").lower().split("/")[0]
    return "sandbox" in host or host.startswith("api.sandbox.")


def account_access_hint(*, endpoint: str | None, account_id: str | None = None) -> str:
    """Operator-facing guidance for ACCOUNT_ACCESS_DENIED / missing account id."""
    env = "sandbox" if is_sandbox_endpoint(endpoint or "") else "production"
    other = WEBULL_PROD_HTTP if env == "sandbox" else WEBULL_SANDBOX_HTTP
    bits = [
        f"WEBULL_ACCOUNT_ID must be an OpenAPI account id returned by "
        f"TradeClient.account_v2.get_account_list() on the same host "
        f"({endpoint or 'WEBULL_API_ENDPOINT'} = {env}).",
        f"Do not reuse a Webull-app paper-trading id, or an id issued for {other}.",
        "Run `python -m trading_system account` after listing succeeds and copy "
        "account_id from that payload into WEBULL_ACCOUNT_ID.",
    ]
    if account_id:
        bits.append(f"Requested account_id={account_id!r} was rejected on this endpoint.")
    return " ".join(bits)


def response_body(res: Any) -> Any:
    if hasattr(res, "json") and callable(res.json):
        try:
            return res.json()
        except Exception:  # noqa: BLE001
            return getattr(res, "text", res)
    return res


def _error_code_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in _ERROR_KEYS:
        value = body.get(key)
        if value in (None, "", 0, "0", 200, "200"):
            continue
        text = str(value)
        if text.upper() in {"OK", "SUCCESS", "NONE"}:
            continue
        # Numeric success / empty codes are ignored; named codes are errors.
        if text.isdigit() and int(text) < 400:
            continue
        return text
    return None


def require_ok(res: Any, action: str, *, endpoint: str | None = None) -> Any:
    """Unwrap an SDK response; raise on HTTP or Webull error_code envelopes."""
    status = getattr(res, "status_code", None)
    body = response_body(res)
    code = _error_code_from_body(body)
    http_bad = status is not None and int(status) >= 400
    if http_bad or code:
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message") or body.get("msg") or body.get("error_msg") or "")
        detail = message or (str(body)[:400] if body is not None else "")
        status_part = f"HTTP {status}" if status is not None else "application error"
        code_part = f" {code}" if code else ""
        text = f"Webull {action} failed ({status_part}{code_part}): {detail}".strip()
        if code and "ACCESS_DENIED" in code.upper():
            text = f"{text} {account_access_hint(endpoint=endpoint)}"
        raise WebullApiError(
            text,
            action=action,
            status=int(status) if status is not None else None,
            error_code=code,
            endpoint=endpoint,
            body=body,
        )
    return body


def extract_account_id(row: dict[str, Any]) -> str:
    for key in _ACCOUNT_ID_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def collect_account_ids(accounts: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in accounts:
        acct = extract_account_id(row)
        if acct and acct not in seen:
            seen.add(acct)
            out.append(acct)
    return out


def as_record_list(payload: Any, keys: tuple[str, ...] = ("data", "result", "items", "list")) -> list[Any]:
    """Unwrap common list envelopes without dropping nested dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return list(value)
    return []
