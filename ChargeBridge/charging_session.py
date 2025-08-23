from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ocpp_client import OCPPClient


@dataclass
class ChargingSession:
    """Track a charging session and communicate via OCPP."""

    ocpp: OCPPClient
    connector_id: int = 1
    id_tag: str = "GUEST"
    transaction_id: int | None = None
    meter_start: int | None = None

    async def start(self, meter_start: int) -> dict:
        """Begin a charging session and record the starting meter value."""
        self.meter_start = meter_start
        await self.ocpp.connect()
        response = await self.ocpp.start_transaction(
            self.connector_id, self.id_tag, self.meter_start
        )
        self.transaction_id = response.get("transactionId")
        return response

    async def stop(self, meter_stop: int) -> dict:
        """Stop an active charging session and send the final meter value."""
        if self.transaction_id is None:
            raise RuntimeError("Session not started")
        response = await self.ocpp.stop_transaction(
            self.transaction_id, self.id_tag, meter_stop
        )
        await self.ocpp.close()
        return response