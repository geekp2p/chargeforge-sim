import pytest
import httpx
from ocpp.v16.enums import RemoteStartStopStatus

from central import app, connected_cps


class DummyCP:
    def __init__(self):
        self.pending_start = {}
        self.recorded: list[tuple[int, str]] = []

    async def remote_start(self, connector_id: int, id_tag: str):
        self.recorded.append((connector_id, id_tag))
        return RemoteStartStopStatus.accepted


@pytest.mark.asyncio
async def test_start_with_custom_id_tag():
    cp = DummyCP()
    connected_cps["CP1"] = cp
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/start",
            json={"cpid": "CP1", "connectorId": 1, "id_tag": "TAG123"},
        )
    assert resp.status_code == 200
    assert cp.recorded == [(1, "TAG123")]
    assert cp.pending_start[1]["id_tag"] == "TAG123"
    connected_cps.pop("CP1", None)