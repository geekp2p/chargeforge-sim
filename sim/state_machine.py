import asyncio
from typing import Dict

class EVSEState:
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    FINISHING = "Finishing"
    FAULTED = "Faulted"
    SUSPENDED_EV = "SuspendedEV"
    SUSPENDED_EVSE = "SuspendedEVSE"
    OCCUPIED = "Occupied"

class ConnectorSim:
    def __init__(self, connector_id: int, meter_start_wh: int = 0):
        self.id = connector_id
        self.state = EVSEState.AVAILABLE
        self.plugged = False
        self.session_active = False
        self.id_tag = None
        self.meter_wh = meter_start_wh
        self.tx_id = None

    def to_status(self) -> str:
        # map internal -> OCPP status set
        if self.state == EVSEState.AVAILABLE:
            return "Available"
        if self.state == EVSEState.PREPARING:
            return "Preparing"
        if self.state == EVSEState.CHARGING:
            return "Charging"
        if self.state == EVSEState.FINISHING:
            return "Finishing"
        return "Available"

class EVSEModel:
    def __init__(self, connectors=1, meter_start_wh=0):
        self.connectors: Dict[int, ConnectorSim] = {
            i: ConnectorSim(i, meter_start_wh) for i in range(1, connectors + 1)
        }

    def get(self, cid: int) -> ConnectorSim:
        return self.connectors[cid]
