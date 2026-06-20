"""
KHQR payment integration via CamRapidPay (matches the working integration
already used in Phanna's Telegram bot — pay.camrapidpay.com).

Create payment : POST {CAMRAPID_CREATE}
  body: { api_key, amount, reference, webhook_url }
  resp: { success, qr_code, payment_url, amount, expires_in }

Check payment   : GET {CAMRAPID_CHECK}
  params: { api_key, reference }
  resp:   { success, status }   status = "success" / "paid" when paid
"""
import requests
from flask import current_app


class CamRapidError(Exception):
    pass


def _session():
    s = requests.Session()
    s.mount("https://", requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
    ))
    return s


def create_payment(amount: float, reference: str) -> dict:
    """
    Create a KHQR payment on CamRapidPay.
    Returns the raw response dict (contains qr_code, payment_url, expires_in)
    on success, raises CamRapidError otherwise.
    """
    api_key = current_app.config["CAMRAPID_API_KEY"]
    create_url = current_app.config["CAMRAPID_CREATE_URL"]
    base_url = current_app.config["APP_BASE_URL"]

    if not api_key:
        raise CamRapidError("CAMRAPID_API_KEY មិនទាន់បានកំណត់ទេ (.env)")

    try:
        r = _session().post(
            create_url,
            json={
                "api_key": api_key,
                "amount": round(float(amount), 2),
                "reference": reference,
                "webhook_url": f"{base_url}/dashboard/deposit/webhook/{reference}",
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise CamRapidError(f"CamRapidPay connection error: {e}")

    try:
        data = r.json()
    except ValueError:
        raise CamRapidError("CamRapidPay returned non-JSON response")

    if not data.get("success"):
        raise CamRapidError(f"CamRapidPay create failed: {data}")

    return data  # keys: qr_code, payment_url, amount, expires_in


def check_payment(reference: str) -> bool:
    """Returns True if the payment for this reference has been paid."""
    api_key = current_app.config["CAMRAPID_API_KEY"]
    check_url = current_app.config["CAMRAPID_CHECK_URL"]

    if not api_key:
        raise CamRapidError("CAMRAPID_API_KEY មិនទាន់បានកំណត់ទេ (.env)")

    try:
        r = _session().get(
            check_url,
            params={"api_key": api_key, "reference": reference},
            headers={"Accept": "application/json"},
            timeout=10,
        )
    except requests.RequestException as e:
        raise CamRapidError(f"CamRapidPay connection error: {e}")

    try:
        data = r.json()
    except ValueError:
        raise CamRapidError("CamRapidPay returned non-JSON response")

    return bool(data.get("success")) and str(data.get("status", "")).lower() in ("success", "paid")
