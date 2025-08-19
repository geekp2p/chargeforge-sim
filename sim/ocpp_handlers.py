import asyncio
import logging
from datetime import datetime, timezone
from ocpp.routing import on
from ocpp.v16 import call_result, ChargePoint as CP
from ocpp.v16.enums import (
    AuthorizationStatus,
    RegistrationStatus,
    Action,
    RemoteStartStopStatus,
)

class EVSEChargePoint(CP):
    def __init__(self, id, connection, model, send_status_cb, start_cb, stop_cb):
        super().__init__(id, connection)
        self.model = model
        self.send_status = send_status_cb
        self.on_start_local = start_cb
        self.on_stop_local = stop_cb

    # ====== CSMS -> EVSE ======

    @on(Action.RemoteStartTransaction)
    async def on_remote_start(self, id_tag, connector_id=None, **kwargs):
        cid = int(connector_id or 1)
        c = self.model.get(cid)
        # reject when not plugged
        if not c.plugged:
            return call_result.RemoteStartTransactionPayload(
                status=RemoteStartStopStatus.rejected
            )
        await self.on_start_local(cid, id_tag)
        return call_result.RemoteStartTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop(self, transaction_id, **kwargs):
        await self.on_stop_local(int(transaction_id), None)
        return call_result.RemoteStopTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )

    # ====== EVSE -> CSMS handlers ======
    @on(Action.BootNotification)
    async def on_boot(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info("BootNotification received")
        return call_result.BootNotificationPayload(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=300,
            status=RegistrationStatus.accepted
        )

    @on(Action.Heartbeat)
    async def on_heartbeat(self, **kwargs):
        return call_result.HeartbeatPayload(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    @on(Action.Authorize)
    async def on_authorize(self, id_tag, **kwargs):
        return call_result.AuthorizePayload(id_tag_info={"status": AuthorizationStatus.accepted})

    @on(Action.StartTransaction)
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        # CSMS ของคุณจะออก tx_id เองใน StartTransaction.conf
        # ที่นี่เราแค่รับ req แล้วตอบ accepted พร้อม meterStart
        await self.on_start_local(int(connector_id), id_tag)
        return call_result.StartTransactionPayload(
            transaction_id=0,  # จะถูกแทนด้วยเลขจาก CSMS ฝั่งคุณ
            id_tag_info={"status": AuthorizationStatus.accepted}
        )

    @on(Action.StopTransaction)
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        await self.on_stop_local(int(transaction_id), meter_stop)
        return call_result.StopTransactionPayload(id_tag_info={"status": AuthorizationStatus.accepted})
