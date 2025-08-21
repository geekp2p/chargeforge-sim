import argparse
import json
from typing import Optional

import requests

# API_BASE = "http://45.136.236.186:8080"
API_BASE="http://host.docker.internal:8080"
DEFAULT_IDTAG = "DEMO_IDTAG"


def _do_json(method: str, url: str, body: str) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "Connection": "close",
    }
    resp = requests.request(method, url, data=body, headers=headers, timeout=15)
    print(f"{method} {url} -> {resp.status_code} {resp.reason}")
    print(resp.text)
    return resp
def start_charge(cpid: str, connector_id: int, id_tag: Optional[str]) -> None:
    url = f"{API_BASE}/api/v1/start"
    payload = {
        "cpid": cpid,
        "connectorId": connector_id,
    }
    if id_tag is not None:
        payload["idTag"] = id_tag
    _do_json("POST", url, json.dumps(payload))


def stop_charge(cpid: str, connector_id: int) -> None:
    url = f"{API_BASE}/api/v1/stop"
    payload = {
        "cpid": cpid,
        "connectorId": connector_id,
    }
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

    p_stop = sub.add_parser("stop", help="stop charging")
    p_stop.add_argument("cpid")
    p_stop.add_argument("connectorId", type=int)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.cmd == "start":
        start_charge(args.cpid, args.connectorId, args.idTag)
    elif args.cmd == "stop":
        stop_charge(args.cpid, args.connectorId)


if __name__ == "__main__":
    main()