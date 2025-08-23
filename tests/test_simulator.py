import asyncio

import pytest
from ocpp.v16.enums import RemoteStartStopStatus, UnlockStatus


@pytest.mark.asyncio
async def test_boot_notification_sent(simulator):
    csms_cp = simulator["csms"].cp
    bn = await asyncio.wait_for(csms_cp.boot_notifications.get(), timeout=5)
    assert bn["charge_point_model"] == "F3-EU180-CC"
    assert bn["charge_point_vendor"] == "Gresgying"


@pytest.mark.asyncio
async def test_health_endpoint(simulator):
    client = simulator["client"]
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_local_start_stop(simulator):
    client = simulator["client"]
    csms = simulator["csms"].cp

    # plug in
    resp = await client.post("/plug/1")
    assert resp.json()["ok"] is True

    # local start
    resp = await client.post("/local_start/1")
    assert resp.json()["ok"] is True
    start = await asyncio.wait_for(csms.start_requests.get(), timeout=5)
    assert start["connector_id"] == 1

    # local stop
    resp = await client.post("/local_stop/1")
    assert resp.json()["ok"] is True
    stop = await asyncio.wait_for(csms.stop_requests.get(), timeout=5)
    assert int(stop["transaction_id"]) == 1



@pytest.mark.asyncio
async def test_unknown_connector_returns_404(simulator):
    client = simulator["client"]

    resp = await client.post("/plug/3")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_can_plug_second_connector(simulator):
    client = simulator["client"]

    resp = await client.post("/plug/2")
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_remote_start_stop(simulator):
    client = simulator["client"]
    csms_cp = simulator["csms"].cp

    # plug in so remote start will be accepted
    resp = await client.post("/plug/1")
    assert resp.json()["ok"] is True

    # remote start
    res = await csms_cp.remote_start(id_tag="REMOTETAG", connector_id=1)
    assert res.status == RemoteStartStopStatus.accepted
    start = await asyncio.wait_for(csms_cp.start_requests.get(), timeout=5)
    assert start["connector_id"] == 1
    await asyncio.sleep(0.1)

    # remote stop
    res = await csms_cp.remote_stop(transaction_id=1)
    assert res.status == RemoteStartStopStatus.accepted
    stop = await asyncio.wait_for(csms_cp.stop_requests.get(), timeout=5)
    assert int(stop["transaction_id"]) == 1


@pytest.mark.asyncio
async def test_remote_start_multiple_connectors(simulator):
    client = simulator["client"]
    csms_cp = simulator["csms"].cp

    # plug in both connectors
    resp = await client.post("/plug/1")
    assert resp.json()["ok"] is True
    resp = await client.post("/plug/2")
    assert resp.json()["ok"] is True

    # remote start both connectors
    res1 = await csms_cp.remote_start(id_tag="TAG1", connector_id=1)
    res2 = await csms_cp.remote_start(id_tag="TAG2", connector_id=2)
    assert res1.status == RemoteStartStopStatus.accepted
    assert res2.status == RemoteStartStopStatus.accepted

    start_a = await asyncio.wait_for(csms_cp.start_requests.get(), timeout=5)
    start_b = await asyncio.wait_for(csms_cp.start_requests.get(), timeout=5)
    assert {start_a["connector_id"], start_b["connector_id"]} == {1, 2}

    # remote stop sessions with assigned transaction ids
    res = await csms_cp.remote_stop(transaction_id=1)
    assert res.status == RemoteStartStopStatus.accepted
    res = await csms_cp.remote_stop(transaction_id=2)
    assert res.status == RemoteStartStopStatus.accepted

    stop_a = await asyncio.wait_for(csms_cp.stop_requests.get(), timeout=5)
    stop_b = await asyncio.wait_for(csms_cp.stop_requests.get(), timeout=5)
    assert {int(stop_a["transaction_id"]), int(stop_b["transaction_id"])} == {1, 2}


@pytest.mark.asyncio
async def test_remote_unlock(simulator):
    client = simulator["client"]
    csms_cp = simulator["csms"].cp

    resp = await client.post("/plug/1")
    assert resp.json()["ok"] is True

    res = await csms_cp.unlock_connector(connector_id=1)
    assert res.status == UnlockStatus.unlocked


@pytest.mark.asyncio
async def test_plug_auto_start(simulator):
    client = simulator["client"]
    csms = simulator["csms"].cp

    resp = await client.post("/plug/1?auto_start=true&id_tag=AUTO123")
    assert resp.json()["ok"] is True

    start = await asyncio.wait_for(csms.start_requests.get(), timeout=5)
    assert start["connector_id"] == 1
    assert start["id_tag"] == "AUTO123"

    resp = await client.post("/local_stop/1")
    assert resp.json()["ok"] is True
    stop = await asyncio.wait_for(csms.stop_requests.get(), timeout=5)
    assert int(stop["transaction_id"]) == 1