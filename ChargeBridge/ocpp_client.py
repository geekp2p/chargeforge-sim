import asyncio
import json
import uuid
from datetime import datetime

import websockets


class OCPPClient:
    """Minimal OCPP client for interacting with charging stations.

    The client targets OCPP 1.6j by default but the WebSocket subprotocol
    can be adjusted to support newer revisions.  It was written with
    Gresgying 120–180 kW DC stations in mind yet keeps messaging
    generic so other vendors and models can be supported as well.
    """

    def __init__(
        self,
        uri: str,
        charge_point_id: str,
        ocpp_protocol: str = "ocpp1.6",
        charger_model: str = "Gresgying 120-180 kW DC",
    ) -> None:
        self.uri = uri
        self.charge_point_id = charge_point_id
        self.ocpp_protocol = ocpp_protocol
        self.charger_model = charger_model
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        """Establish a WebSocket connection using the configured subprotocol."""
        self._ws = await websockets.connect(self.uri, subprotocols=[self.ocpp_protocol])

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _call(self, action: str, payload: dict) -> dict:
        """Send an OCPP CALL message and return the payload of the result."""
        if self._ws is None:
            raise RuntimeError("Client is not connected")

        message_id = str(uuid.uuid4())
        request = [2, message_id, action, payload]
        await self._ws.send(json.dumps(request))

        raw_response = await self._ws.recv()
        response = json.loads(raw_response)
        # OCPP result frames are of the form [3, message_id, payload]
        return response[2]

    async def start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int
    ) -> dict:
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": meter_start,
            "timestamp": datetime.utcnow().isoformat(),
        }
        return await self._call("StartTransaction", payload)

    async def stop_transaction(
        self, transaction_id: int, id_tag: str, meter_stop: int
    ) -> dict:
        payload = {
            "transactionId": transaction_id,
            "idTag": id_tag,
            "meterStop": meter_stop,
            "timestamp": datetime.utcnow().isoformat(),
        }
        return await self._call("StopTransaction", payload)