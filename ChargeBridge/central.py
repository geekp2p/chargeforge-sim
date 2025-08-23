import asyncio
import logging
import json
from datetime import datetime
from typing import List, Any, Dict
import itertools
import threading

from websockets import serve
from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import (
    RegistrationStatus,
    AuthorizationStatus,
    Action,
    RemoteStartStopStatus,
    DataTransferStatus,
)

from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
import uvicorn

logging.basicConfig(level=logging.INFO)

connected_cps: Dict[str, "CentralSystem"] = {}
_tx_counter = itertools.count(1)


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO8601 timestamp and fall back to now on error."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()

def make_display_message_call(message_type: str, uri: str):
    payload = {"message_type": message_type, "uri": uri}
    if hasattr(call, "DisplayMessage"):
        DisplayMessageCls = getattr(call, "DisplayMessage")
        for attempt_kwargs in ("message", "payload", "content", "display"):
            try:
                return DisplayMessageCls(**{attempt_kwargs: payload})  # type: ignore
            except Exception:
                continue
    try:
        return call.DataTransfer("com.yourcompany.payment", "DisplayQRCode", json.dumps(payload))
    except Exception as e:
        logging.error(f"Failed to build DataTransfer fallback: {e}")
        raise


class CentralSystem(ChargePoint):
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.active_tx: Dict[int, Dict[str, Any]] = {}
        self.pending_remote: Dict[int, str] = {}
        self.pending_start: Dict[int, Dict[str, Any]] = {}
        self.connector_status: Dict[int, str] = {}
        self.no_session_tasks: Dict[int, asyncio.Task] = {}
        self.completed_sessions: List[Dict[str, Any]] = []

    async def remote_start(self, connector_id: int, id_tag: str):
        req = call.RemoteStartTransaction(
            id_tag=id_tag,
            connector_id=connector_id
        )
        logging.info(f"→ RemoteStartTransaction to {self.id} (connector={connector_id}, idTag={id_tag})")
        resp = await self.call(req)
        status = getattr(resp, "status", None)
        if status == RemoteStartStopStatus.accepted:
            self.pending_remote[int(connector_id)] = id_tag
        else:
            logging.warning(f"RemoteStartTransaction rejected: {status}")
        return status

    async def remote_stop(self, transaction_id: int):
        req = call.RemoteStopTransaction(transaction_id=transaction_id)
        logging.info(f"→ RemoteStopTransaction to {self.id} (tx={transaction_id})")
        resp = await self.call(req)
        status = getattr(resp, "status", None)
        if status != RemoteStartStopStatus.accepted:
            logging.warning(f"RemoteStopTransaction rejected: {status}")
        return status

    async def change_configuration(self, key: str, value: str):
        req = call.ChangeConfiguration(key=key, value=value)
        logging.info(f"→ ChangeConfiguration to {self.id} ({key}={value})")
        resp = await self.call(req)
        logging.info(f"← ChangeConfiguration.conf: {resp}")
        return getattr(resp, "status", None)

    async def unlock_connector(self, connector_id: int):
        req = call.UnlockConnector(connector_id=connector_id)
        logging.info(f"→ UnlockConnector to {self.id} (connector={connector_id})")
        resp = await self.call(req)
        logging.info(f"← UnlockConnector.conf: {resp}")
        return getattr(resp, "status", None)

    async def _no_session_watchdog(self, connector_id: int, timeout: int = 90):
        try:
            await asyncio.sleep(timeout)
            status = self.connector_status.get(connector_id)
            if status in ("Preparing", "Occupied") and connector_id not in self.active_tx:
                logging.info(
                    f"No session started for connector {connector_id} after {timeout}s → unlocking"
                )
                await self.unlock_connector(connector_id)
                self.pending_remote.pop(connector_id, None)
                self.pending_start.pop(connector_id, None)
        except asyncio.CancelledError:
            logging.debug(f"Watchdog for connector {connector_id} cancelled")
        finally:
            self.no_session_tasks.pop(connector_id, None)

    @on(Action.boot_notification)
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"← BootNotification from vendor={charge_point_vendor}, model={charge_point_model}")
        response = call_result.BootNotification(
            current_time=datetime.utcnow().isoformat() + "Z",
            interval=300,
            status=RegistrationStatus.accepted
        )

        supported_keys: List[str] = []
        try:
            conf_req = call.GetConfiguration()
            conf_resp = await asyncio.wait_for(self.call(conf_req), timeout=10)
            items: Any = []
            if hasattr(conf_resp, "configuration_key"):
                items = getattr(conf_resp, "configuration_key")
            elif hasattr(conf_resp, "configurationKey"):
                items = getattr(conf_resp, "configurationKey")
            elif isinstance(conf_resp, dict):
                items = conf_resp.get("configuration_key") or conf_resp.get("configurationKey") or []
            for entry in items:
                if isinstance(entry, dict):
                    key_name = entry.get("key")
                else:
                    key_name = getattr(entry, "key", None)
                if key_name:
                    supported_keys.append(key_name)
        except asyncio.TimeoutError:
            logging.warning("Timeout fetching GetConfiguration; proceeding without supported keys.")
        except Exception as e:
            logging.warning(f"Failed to fetch supported configuration keys: {e}")

        if "AuthorizeRemoteTxRequests" in supported_keys:
            cfg_req = call.ChangeConfiguration(
                key="AuthorizeRemoteTxRequests", value="true"
            )
            asyncio.create_task(self._send_change_configuration(cfg_req))

        qr_url = "https://your-domain.com/qr?order_id=TEST123"
        target_key = "QRcodeConnectorID1"
        if target_key in supported_keys:
            change_req = call.ChangeConfiguration(key=target_key, value=qr_url)
            asyncio.create_task(self._send_change_configuration(change_req))
        else:
            try:
                fallback = make_display_message_call(message_type="QRCode", uri=qr_url)
                asyncio.create_task(self._send_change_configuration(fallback))
            except Exception as e:
                logging.error(f"Failed to send fallback display message: {e}")

        return response

    async def _send_change_configuration(self, request_payload):
        try:
            resp = await self.call(request_payload)
            logging.info(f"→ ChangeConfiguration / Custom response: {resp}")
        except Exception as e:
            logging.error(f"!!! ChangeConfiguration/custom failed: {e}")

    @on(Action.authorize)
    async def on_authorize(self, id_tag, **kwargs):
        logging.info(f"← Authorize request, idTag={id_tag}")
        return call_result.Authorize(id_tag_info={"status": AuthorizationStatus.accepted})

    @on(Action.status_notification)
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        logging.info(
            f"← StatusNotification: connector {connector_id} → status={status}, errorCode={error_code}"
        )
        c_id = int(connector_id)
        self.connector_status[c_id] = status
        if status in ("Preparing", "Occupied"):
            if c_id not in self.active_tx and c_id not in self.no_session_tasks:
                self.no_session_tasks[c_id] = asyncio.create_task(
                    self._no_session_watchdog(c_id)
                )
        else:
            task = self.no_session_tasks.pop(c_id, None)
            if task:
                task.cancel()
        return call_result.StatusNotification()

    @on(Action.heartbeat)
    def on_heartbeat(self, **kwargs):
        logging.info("← Heartbeat received")
        return call_result.Heartbeat(current_time=datetime.utcnow().isoformat() + "Z")

    @on(Action.meter_values)
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        logging.info(f"← MeterValues from connector {connector_id}: {meter_value}")
        return call_result.MeterValues()

    @on(Action.data_transfer)
    async def on_data_transfer(self, vendor_id, message_id=None, data=None, **kwargs):
        logging.info(
            f"← DataTransfer: vendorId={vendor_id}, messageId={message_id}, data={data}"
        )
        return call_result.DataTransfer(status=DataTransferStatus.accepted)

    @on(Action.start_transaction)
    async def on_start_transaction(
        self,
        connector_id,
        id_tag,
        meter_start,
        timestamp,
        reservation_id=None,
        **kwargs,
    ):
        expected = self.pending_remote.get(int(connector_id))
        if expected is not None and expected != id_tag:
            logging.warning(
                f"StartTransaction for connector {connector_id} received with unexpected idTag (expected={expected}, got={id_tag}); rejecting"
            )
            await self.unlock_connector(int(connector_id))
            self.pending_remote.pop(int(connector_id), None)
            self.pending_start.pop(int(connector_id), None)
            return call_result.StartTransaction(
                transaction_id=0,
                id_tag_info={"status": AuthorizationStatus.invalid},
            )

        pending = self.pending_start.pop(int(connector_id), None)
        self.pending_remote.pop(int(connector_id), None)

        tx_id = next(_tx_counter)
        info = {
            "transaction_id": tx_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "start_time": _parse_timestamp(timestamp),
        }
        if pending and "vid" in pending:
            info["vid"] = pending["vid"]
        self.active_tx[int(connector_id)] = info
        task = self.no_session_tasks.pop(int(connector_id), None)
        if task:
            task.cancel()
        logging.info(
            f"← StartTransaction from {self.id}: connector={connector_id}, idTag={id_tag}, meterStart={meter_start}, vid={info.get('vid')}"
        )
        logging.info(f"→ Assign transactionId={tx_id}")
        return call_result.StartTransaction(
            transaction_id=tx_id,
            id_tag_info={"status": AuthorizationStatus.accepted},
        )

    @on(Action.stop_transaction)
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        session_info = None
        c_id = None
        for conn_id, info in list(self.active_tx.items()):
            if info.get("transaction_id") == int(transaction_id):
                session_info = info
                c_id = conn_id
                self.active_tx.pop(conn_id, None)
                break
        logging.info(f"← StopTransaction from {self.id}: tx={transaction_id}, meterStop={meter_stop}")
        if session_info:
            start_time = session_info.get("start_time")
            stop_time = _parse_timestamp(timestamp)
            duration_secs = (stop_time - start_time).total_seconds() if start_time else 0
            meter_start = session_info.get("meter_start", meter_stop)
            energy = meter_stop - meter_start
            record = {
                "connectorId": c_id,
                "transactionId": int(transaction_id),
                "idTag": session_info.get("id_tag", ""),
                "meterStart": meter_start,
                "meterStop": meter_stop,
                "energy": energy,
                "startTime": start_time.isoformat() if start_time else None,
                "stopTime": stop_time.isoformat(),
                "durationSecs": duration_secs,
            }
            self.completed_sessions.append(record)
            logging.info(f"Session summary: {record}")
        return call_result.StopTransactionPayload(
            id_tag_info={"status": AuthorizationStatus.accepted}
        )


DEFAULT_ID_TAG = "DEMO_IDTAG"
API_KEY = "changeme-123"

app = FastAPI(title="OCPP Central Control API", version="1.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f">>> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logging.info(f"<<< {request.method} {request.url.path} -> {response.status_code}")
        return response
    except Exception:
        logging.exception("Handler crashed")
        raise


@app.get("/api/v1/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}


class StartReq(BaseModel):
    cpid: str
    connectorId: int
    id_tag: str | None = Field(default=None, alias="idTag")
    transactionId: int | None = None
    timestamp: str | None = None
    vid: str | None = None
    kv: str | None = None
    kvMap: Dict[str, str] | None = None
    hash: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class StopReq(BaseModel):
    cpid: str
    transactionId: int | None = None
    connectorId: int | None = None
    idTag: str | None = None
    timestamp: str | None = None
    vid: str | None = None
    kv: str | None = None
    kvMap: Dict[str, str] | None = None
    hash: str | None = None


class StopByConnectorReq(BaseModel):
    cpid: str
    connectorId: int


class ReleaseReq(BaseModel):
    cpid: str
    connectorId: int


class ActiveSession(BaseModel):
    cpid: str
    connectorId: int
    idTag: str
    transactionId: int


class CompletedSession(BaseModel):
    """Summary of a finished charging transaction."""

    cpid: str
    connectorId: int
    idTag: str
    transactionId: int
    meterStart: int
    meterStop: int
    energy: int
    startTime: str
    stopTime: str
    durationSecs: float


class ConnectorStatus(BaseModel):
    cpid: str
    connectorId: int
    status: str


def require_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


@app.post("/api/v1/start")
async def api_start(req: StartReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        id_tag = req.id_tag or DEFAULT_ID_TAG
        cp.pending_start[int(req.connectorId)] = {"id_tag": id_tag}
        status = await cp.remote_start(req.connectorId, id_tag)
        if status != RemoteStartStopStatus.accepted:
            cp.pending_start.pop(int(req.connectorId), None)
            raise HTTPException(status_code=409, detail=f"RemoteStart rejected: {status}")
        return {"ok": True, "message": "RemoteStartTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/stop")
async def api_stop(req: StopReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        tx_id = req.transactionId
        if tx_id is not None:
            if not any(
                session.get("transaction_id") == tx_id
                for session in cp.active_tx.values()
            ):
                raise HTTPException(status_code=404, detail="No matching active transaction")
        elif req.connectorId is not None:
            session = cp.active_tx.get(req.connectorId)
            if session:
                tx_id = session.get("transaction_id")
        if tx_id is None:
            raise HTTPException(status_code=404, detail="No matching active transaction")
        status = await cp.remote_stop(tx_id)
        if status != RemoteStartStopStatus.accepted:
            raise HTTPException(status_code=409, detail=f"RemoteStop rejected: {status}")
        return {"ok": True, "transactionId": tx_id, "message": "RemoteStopTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/charge/stop")
async def api_stop_by_connector(req: StopByConnectorReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    session = cp.active_tx.get(req.connectorId)
    if session is None:
        raise HTTPException(status_code=404, detail="No active transaction for this connector")
    tx_id = session["transaction_id"]
    try:
        status = await cp.remote_stop(tx_id)
        if status != RemoteStartStopStatus.accepted:
            raise HTTPException(status_code=409, detail=f"RemoteStop rejected: {status}")
        return {"ok": True, "transactionId": tx_id, "message": "RemoteStopTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/release")
async def api_release(req: ReleaseReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    if req.connectorId in cp.active_tx:
        raise HTTPException(status_code=400, detail="Connector has active transaction")
    task = cp.no_session_tasks.pop(req.connectorId, None)
    if task:
        task.cancel()
    cp.pending_remote.pop(req.connectorId, None)
    cp.pending_start.pop(req.connectorId, None)
    try:
        await cp.unlock_connector(req.connectorId)
        return {"ok": True, "message": "UnlockConnector sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/active")
async def api_active_sessions():
    sessions: list[ActiveSession] = []
    for cpid, cp in connected_cps.items():
        for conn_id, info in cp.active_tx.items():
            sessions.append(
                ActiveSession(
                    cpid=cpid,
                    connectorId=conn_id,
                    idTag=info.get("id_tag", ""),
                    transactionId=info.get("transaction_id", 0),
                )
            )
    return {"sessions": [s.dict() for s in sessions]}


@app.get("/api/v1/history")
async def api_session_history():
    sessions: list[CompletedSession] = []
    for cpid, cp in connected_cps.items():
        for record in cp.completed_sessions:
            sessions.append(CompletedSession(cpid=cpid, **record))
    return {"sessions": [s.dict() for s in sessions]}


@app.get("/api/v1/status")
async def api_connector_status():
    statuses: list[ConnectorStatus] = []
    for cpid, cp in connected_cps.items():
        for conn_id, status in cp.connector_status.items():
            statuses.append(ConnectorStatus(cpid=cpid, connectorId=conn_id, status=status))
    return {"connectors": [s.dict() for s in statuses]}


async def run_http_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    async def handler(websocket, path=None):
        if path is None:
            try:
                path = websocket.request.path
            except AttributeError:
                path = websocket.path if hasattr(websocket, "path") else ""
        cp_id = path.rsplit('/', 1)[-1] if path else "UNKNOWN"
        logging.info(f"[Central] New connection for Charge Point ID: {cp_id}")

        central = CentralSystem(cp_id, websocket)
        connected_cps[cp_id] = central
        try:
            await central.start()
        finally:
            connected_cps.pop(cp_id, None)
            logging.info(f"[Central] Disconnected: {cp_id}")

    def console_thread(loop: asyncio.AbstractEventLoop):
        while True:
            try:
                cmd = input().strip()
            except EOFError:
                return
            if not cmd:
                continue
            parts = cmd.split()
            if parts[0] == "ls":
                print("Connected CPs:", ", ".join(connected_cps.keys()) or "(none)")
                continue
            if parts[0] == "map" and len(parts) == 2:
                cp = connected_cps.get(parts[1])
                if not cp:
                    print("No such CP")
                else:
                    print(f"{parts[1]} active_tx:", cp.active_tx)
                continue
            if parts[0] == "config" and len(parts) >= 4:
                cpid, key, value = parts[1], parts[2], " ".join(parts[3:])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                asyncio.run_coroutine_threadsafe(cp.change_configuration(key, value), loop)
                continue
            if parts[0] == "start" and len(parts) >= 4:
                cpid, connector, idtag = parts[1], int(parts[2]), " ".join(parts[3:])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                asyncio.run_coroutine_threadsafe(cp.remote_start(connector, idtag), loop)
                continue
            if parts[0] == "stop" and len(parts) == 3:
                cpid, num = parts[1], int(parts[2])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                session = cp.active_tx.get(num)
                if session:
                    txid = session.get("transaction_id", num)
                    asyncio.run_coroutine_threadsafe(cp.remote_stop(txid), loop)
                    continue
                tx_match = None
                for info in cp.active_tx.values():
                    if info.get("transaction_id") == num:
                        tx_match = num
                        break
                if tx_match is not None:
                    asyncio.run_coroutine_threadsafe(cp.remote_stop(tx_match), loop)
                else:
                    asyncio.run_coroutine_threadsafe(cp.unlock_connector(num), loop)
                continue
            print("Unknown command. Examples: start CP_123 1 TESTTAG | stop CP_123 42 | ls | map CP_123")

    loop = asyncio.get_running_loop()
    threading.Thread(target=console_thread, args=(loop,), daemon=True).start()

    api_task = asyncio.create_task(run_http_api())

    async with serve(
        handler,
        host='0.0.0.0',
        port=9000,
        subprotocols=['ocpp1.6']
    ):
        logging.info("⚡ Central listening on ws://0.0.0.0:9000/ocpp/<ChargePointID> | HTTP :8080")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
