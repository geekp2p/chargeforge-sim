import argparse
import hashlib
import json
from datetime import datetime
from typing import Optional

import requests

# API_BASE = "http://45.136.236.186:8080"
API_BASE="http://host.docker.internal:8080"
API_KEY = "changeme-123"
DEFAULT_IDTAG = "DEMO_IDTAG"


def _do_json(method: str, url: str, body: str) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "Connection": "close",
    }
    resp = requests.request(method, url, data=body, headers=headers, timeout=15)
    print(f"{method} {url} -> {resp.status_code} {resp.reason}")
    print(resp.text)
    return resp


def compute_hash(cpid: str, connector_id: int, id_tag: str, tx_id: str, ts: str) -> str:
    canonical = f"{cpid}|{connector_id}|{id_tag}|{tx_id}|{ts}|-|-"
    return hashlib.sha256(canonical.encode()).hexdigest()


def start_charge(cpid: str, connector_id: int, id_tag: str, tx_id: Optional[int]) -> None:
    url = f"{API_BASE}/api/v1/start"
    ts = datetime.utcnow().isoformat()
    tx_str = str(tx_id) if tx_id is not None else "-"
    payload = {
        "cpid": cpid,
        "connectorId": connector_id,
        "idTag": id_tag,
        "timestamp": ts,
        "hash": compute_hash(cpid, connector_id, id_tag, tx_str, ts),
    }
    if tx_id is not None:
        payload["transactionId"] = tx_id
    _do_json("POST", url, json.dumps(payload))


def stop_charge(cpid: str, connector_id: int, id_tag: Optional[str], tx_id: Optional[int]) -> None:
    url = f"{API_BASE}/api/v1/stop"
    ts = datetime.utcnow().isoformat()
    id_val = id_tag if id_tag is not None else "-"
    tx_str = str(tx_id) if tx_id is not None else "-"
    payload = {
        "cpid": cpid,
        "connectorId": connector_id,
        "timestamp": ts,
        "hash": compute_hash(cpid, connector_id, id_val, tx_str, ts),
    }
    if id_tag is not None:
        payload["idTag"] = id_tag
    if tx_id is not None:
        payload["transactionId"] = tx_id

    resp = _do_json("POST", url, json.dumps(payload))
    if resp.status_code == 404:
        rel_url = f"{API_BASE}/api/v1/release"
        rel_body = json.dumps({"cpid": cpid, "connectorId": connector_id})
        _do_json("POST", rel_url, rel_body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start or stop a charging session via HTTP API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="start charging")
    p_start.add_argument("cpid")
    p_start.add_argument("connectorId", type=int)
    p_start.add_argument("idTag", nargs="?", default=DEFAULT_IDTAG)
    p_start.add_argument("transactionId", nargs="?", type=int)

    p_stop = sub.add_parser("stop", help="stop charging")
    p_stop.add_argument("cpid")
    p_stop.add_argument("connectorId", type=int)
    p_stop.add_argument("idTag", nargs="?")
    p_stop.add_argument("transactionId", nargs="?", type=int)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.cmd == "start":
        start_charge(args.cpid, args.connectorId, args.idTag, args.transactionId)
    elif args.cmd == "stop":
        stop_charge(args.cpid, args.connectorId, args.idTag, args.transactionId)


if __name__ == "__main__":
    main()