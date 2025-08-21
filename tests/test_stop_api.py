import pytest
import httpx
from ocpp.v16.enums import RemoteStartStopStatus

from central import app, connected_cps


class DummyCP:
    def __init__(self):
        # simulate one active transaction with id 100
        self.active_tx = {1: {"transaction_id": 100}}
        self.recorded: list[int] = []

    async def remote_stop(self, transaction_id: int):
        self.recorded.append(transaction_id)
        return RemoteStartStopStatus.accepted


@pytest.mark.asyncio
async def test_stop_invalid_transaction_id():
    cp = DummyCP()
    connected_cps["CP1"] = cp
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/stop",
            json={"cpid": "CP1", "transactionId": 999},
        )
    assert resp.status_code == 404
    assert cp.recorded == []
    connected_cps.pop("CP1", None)