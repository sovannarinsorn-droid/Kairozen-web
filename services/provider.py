"""
Provider client for khmer-smm.com (standard SMM Panel v2 API format).

Standard v2 API actions used here:
  - services        -> list all services
  - add              -> place a new order
  - status           -> single order status
  - status (multi)   -> multiple order status
  - balance          -> provider account balance

Docs convention (used by most SMM panels incl. khmer-smm.com):
  POST {PROVIDER_API_URL}
  body: { key, action, ...params }
"""
import requests
from flask import current_app


class ProviderError(Exception):
    pass


def _post(payload: dict, timeout: int = 20) -> dict:
    url = current_app.config["PROVIDER_API_URL"]
    key = current_app.config["PROVIDER_API_KEY"]

    if not key:
        raise ProviderError("PROVIDER_API_KEY មិនទាន់បានកំណត់ទេ (.env)")

    body = {"key": key, **payload}

    try:
        resp = requests.post(url, data=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ProviderError(f"Provider connection error: {e}")

    try:
        data = resp.json()
    except ValueError:
        raise ProviderError("Provider returned non-JSON response")

    if isinstance(data, dict) and data.get("error"):
        raise ProviderError(str(data["error"]))

    return data


def fetch_services() -> list:
    """Return raw service list from provider: [{service, name, type, category, rate, min, max, ...}]"""
    data = _post({"action": "services"})
    if not isinstance(data, list):
        raise ProviderError("Unexpected services response format")
    return data


def place_order(provider_service_id: str, link: str, quantity: int, extra: dict | None = None) -> dict:
    """Place order on provider. Returns {"order": "12345"} on success."""
    payload = {
        "action": "add",
        "service": provider_service_id,
        "link": link,
        "quantity": quantity,
    }
    if extra:
        payload.update(extra)
    return _post(payload)


def order_status(provider_order_id: str) -> dict:
    """Returns {charge, start_count, status, remains, currency}"""
    return _post({"action": "status", "order": provider_order_id})


def multi_order_status(provider_order_ids: list) -> dict:
    """Returns { "<order_id>": {status...}, ... }"""
    ids = ",".join(str(i) for i in provider_order_ids)
    return _post({"action": "status", "orders": ids})


def provider_balance() -> dict:
    """Returns {balance, currency}"""
    return _post({"action": "balance"})
