"""
KHQR (Bakong EMV QR) generator + payment status checker.

Generates the QR payload locally (no external dependency needed to RENDER
a QR — this matches the offline EMV generator approach used in earlier
Kairozen projects). Payment verification optionally calls the official
Bakong API; if that token is invalid/unauthorized we fail soft and let
admin manually confirm deposits instead of crashing the flow.
"""
import hashlib
import requests
from flask import current_app


def _tlv(tag: str, value: str) -> str:
    length = f"{len(value):02d}"
    return f"{tag}{length}{value}"


def _crc16(payload: str) -> str:
    """CRC-16/CCITT-FALSE as required by EMV QR spec."""
    crc = 0xFFFF
    for b in payload.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def build_khqr_payload(amount: float, bill_number: str) -> str:
    """
    Build an individual (personal) Bakong KHQR EMV payload.
    Tag 30 = Merchant Account Info for individual accounts (bakong account id).
    """
    account_id = current_app.config["BAKONG_ACCOUNT_ID"]
    merchant_name = current_app.config["BAKONG_MERCHANT_NAME"][:25]
    merchant_city = current_app.config["BAKONG_MERCHANT_CITY"][:15]

    # --- Tag 30: Merchant Account Information (individual) ---
    sub_00 = _tlv("00", "khqr@bakong")  # bakong identifier (well-known guid style)
    sub_01 = _tlv("01", account_id)
    tag_30_value = sub_00 + sub_01
    tag_30 = _tlv("30", tag_30_value)

    fields = [
        _tlv("00", "01"),                       # Payload Format Indicator
        _tlv("01", "12"),                       # Point of Initiation (12 = dynamic, has amount)
        tag_30,                                  # Merchant Account Info
        _tlv("52", "5999"),                     # Merchant Category Code
        _tlv("53", "840"),                       # Currency: 840 = USD
        _tlv("54", f"{amount:.2f}"),             # Transaction Amount
        _tlv("58", "KH"),                        # Country Code
        _tlv("59", merchant_name),               # Merchant Name
        _tlv("60", merchant_city),                # Merchant City
        _tlv("62", _tlv("01", bill_number)),     # Additional data: bill number
    ]

    payload_no_crc = "".join(fields) + "6304"
    crc = _crc16(payload_no_crc)
    return payload_no_crc + crc


def payload_md5(payload: str) -> str:
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class BakongCheckError(Exception):
    pass


def check_payment_by_md5(md5_hash: str) -> dict:
    """
    Calls the official Bakong "check transaction by MD5" endpoint.
    Returns {"paid": bool, "raw": <response>}.
    Raises BakongCheckError on auth/connection failure so the caller
    can fall back to manual admin confirmation instead of silently
    treating it as unpaid forever.
    """
    token = current_app.config["BAKONG_API_TOKEN"]
    base = current_app.config["BAKONG_API_URL"]

    if not token:
        raise BakongCheckError("BAKONG_API_TOKEN មិនទាន់បានកំណត់ទេ")

    url = f"{base}/check_transaction_by_md5"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.post(url, json={"md5": md5_hash}, headers=headers, timeout=15)
    except requests.RequestException as e:
        raise BakongCheckError(f"Bakong connection error: {e}")

    if resp.status_code == 401:
        raise BakongCheckError("Bakong API token unauthorized (401) — ត្រូវ admin manual confirm")

    try:
        data = resp.json()
    except ValueError:
        raise BakongCheckError("Bakong returned non-JSON response")

    paid = bool(data.get("responseCode") == 0 and data.get("data"))
    return {"paid": paid, "raw": data}
