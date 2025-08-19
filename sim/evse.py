import asyncio
import json
import logging
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI
import websockets

from ocpp.v16 import call
from ocpp.v16.enums import Action, Measurand
from ocpp.transport import WebSocketTransport

from .config import *
from .state_machine import EVSEModel, EVSEState
from .ocpp_handlers import EVSEChargePoint

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

app = FastAPI(title="ChargeForge-Sim Control")


@app.get("/health")
async def health():
    return {"ok": True}

model = EVSEModel(connectors=CONNECTORS, meter_start_wh=METER_START_WH)
cp = None  # type: ignore

# -------- helper: send StatusNotification --------
async def send_status(connector_id: int):␊
    global cp␊
    st = model.get(connector_id).to_status()
    req = call.StatusNotificationPayload(
        connector_id=connector_id,
        error_code="NoError",
        status=st,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await cp.call(req)  # type: ignore
    logging.info(f"StatusNotification sent: connector={connector_id}, status={st}")

# -------- local state transitions --------
async def start_local(connector_id: int, id_tag: str):
    c = model.get(connector_id)
    c.id_tag = id_tag
    c.session_active = True
    c.state = EVSEState.CHARGING
    await send_status(connector_id)
    # inform CSMS and store transaction id
    req = call.StartTransactionPayload(
        connector_id=connector_id,
        id_tag=id_tag,
        meter_start=c.meter_wh,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    conf = await cp.call(req)  # type: ignore
    c.tx_id = conf.transaction_id
    logging.info(
        f"StartTransaction confirmed: connector={connector_id}, tx_id={c.tx_id}"
    )

async def stop_local_by_tx(tx_id: int, meter_stop: int | None = None):
    for c in model.connectors.values():
        if not c.session_active or c.tx_id != tx_id:
            continue
        if meter_stop is None:
            meter_stop = c.meter_wh
        req = call.StopTransactionPayload(
            transaction_id=tx_id,
            meter_stop=meter_stop,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await cp.call(req)  # type: ignore
        c.session_active = False
        c.state = EVSEState.FINISHING
        await send_status(c.id)
        await asyncio.sleep(1)
        c.state = EVSEState.AVAILABLE
        c.tx_id = None
        c.id_tag = None
        await send_status(c.id)
        return

# -------- OCPP client main --------
async def ocpp_client():
    global cp
    cpid = CPID
    url = f"{CSMS_URL}/{cpid}"
    while True:
        try:
            logging.info(f"Connecting to CSMS: {url}")
            async with websockets.connect(url, subprotocols=['ocpp1.6']) as ws:
                transport = WebSocketTransport(ws)
                cp = EVSEChargePoint(
                    cpid, transport, model,
                    send_status_cb=send_status,
                    start_cb=start_local,
                    stop_cb=stop_local_by_tx
                )
                # Boot → Available
                asyncio.create_task(cp.start())
                await asyncio.sleep(1)
                for cid in model.connectors.keys():
                    await send_status(cid)

                # tasks: heartbeat, metering
                hb_task = asyncio.create_task(send_heartbeat_loop())
                mv_task = asyncio.create_task(send_meter_loop())

                await ws.wait_closed()
                hb_task.cancel()
                mv_task.cancel()
        except Exception as e:
            logging.error(f"OCPP connection error: {e}")
        logging.info("Reconnecting to CSMS in 5s...")
        await asyncio.sleep(5)

async def send_heartbeat_loop():
    while True:
        try:
            await asyncio.sleep(SEND_HEARTBEAT_SEC)
            req = call.HeartbeatPayload()
            await cp.call(req)  # type: ignore
        except Exception:
            return

async def send_meter_loop():
    while True:
        await asyncio.sleep(METER_PERIOD_SEC)
        t = datetime.now(timezone.utc).isoformat()
        for c in model.connectors.values():
            if not c.session_active:
                continue
            # เพิ่มพลังงาน (Wh) ตาม rate * period
            added_wh = int((METER_RATE_W * METER_PERIOD_SEC) / 3600)
            c.meter_wh += added_wh
            mv = [{
                "timestamp": t,
                "sampledValue": [{"value": str(c.meter_wh), "measurand": "Energy.Active.Import.Register"}]
            }]
            req = call.MeterValuesPayload(connector_id=c.id, meter_value=mv)
            await cp.call(req)  # type: ignore
            logging.info(f"MeterValues: cid={c.id}, energy(Wh)={c.meter_wh}")

# -------- HTTP control for simulating plug/unplug & local start/stop --------
@app.post("/plug/{connector_id}")
async def plug(connector_id: int):
    c = model.get(connector_id)
    c.plugged = True
    c.state = EVSEState.PREPARING
    await send_status(connector_id)
    return {"ok": True, "connector": connector_id, "plugged": True}

@app.post("/unplug/{connector_id}")
async def unplug(connector_id: int):
    c = model.get(connector_id)
    c.plugged = False
    c.session_active = False
    c.state = EVSEState.AVAILABLE
    c.tx_id = None
    c.id_tag = None
    await send_status(connector_id)
    return {"ok": True, "connector": connector_id, "plugged": False}

@app.post("/local_start/{connector_id}")
async def local_start(connector_id: int, id_tag: str = "LOCAL_TAG"):
    c = model.get(connector_id)
    if not c.plugged:
        return {"ok": False, "error": "not plugged"}
    await start_local(connector_id, id_tag)
    return {"ok": True}

@app.post("/local_stop/{connector_id}")
async def local_stop(connector_id: int):
    c = model.get(connector_id)
    if not c.session_active:
        return {"ok": False, "error": "no active session"}
    await stop_local_by_tx(c.tx_id, c.meter_wh)  # type: ignore
    return {"ok": True}

async def main():
    # run OCPP client and HTTP API together
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, loop="asyncio", log_level="info"))
    api_task = asyncio.create_task(server.serve())
    await ocpp_client()
    api_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())