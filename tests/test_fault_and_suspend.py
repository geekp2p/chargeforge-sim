import asyncio

import pytest

from sim.state_machine import EVSEState


@pytest.mark.asyncio
async def test_fault_and_suspend(simulator):
    client = simulator["client"]
    csms_cp = simulator["csms"].cp
    evse = simulator["evse"]
    connector_id = 1

    # ensure boot and initial statuses have been processed
    await asyncio.wait_for(csms_cp.boot_notifications.get(), timeout=5)
    while not csms_cp.status_notifications.empty():
        csms_cp.status_notifications.get_nowait()
    async def get_latest_status():
        status = await asyncio.wait_for(csms_cp.status_notifications.get(), timeout=5)
        while not csms_cp.status_notifications.empty():
            status = csms_cp.status_notifications.get_nowait()
        return status

    # inject fault
    resp = await client.post(f"/fault/{connector_id}?error_code=GroundFailure")
    assert resp.json()["ok"] is True
    status = await get_latest_status()
    assert status == {
        "connector_id": connector_id,
        "error_code": "GroundFailure",
        "status": "Faulted",
    }
    assert evse.model.get(connector_id).state == EVSEState.FAULTED

    # clear fault
    resp = await client.post(f"/clear_fault/{connector_id}")
    assert resp.json()["ok"] is True
    status = await get_latest_status()
    assert status == {
        "connector_id": connector_id,
        "error_code": "NoError",
        "status": "Available",
    }
    assert evse.model.get(connector_id).state == EVSEState.AVAILABLE

    # suspend by EV
    resp = await client.post(f"/suspend_ev/{connector_id}")
    assert resp.json()["ok"] is True
    status = await get_latest_status()
    assert status == {
        "connector_id": connector_id,
        "error_code": "NoError",
        "status": "SuspendedEV",
    }
    assert evse.model.get(connector_id).state == EVSEState.SUSPENDED_EV

    # suspend by EVSE
    resp = await client.post(f"/suspend_evse/{connector_id}")
    assert resp.json()["ok"] is True
    status = await get_latest_status()
    assert status == {
        "connector_id": connector_id,
        "error_code": "NoError",
        "status": "SuspendedEVSE",
    }
    assert evse.model.get(connector_id).state == EVSEState.SUSPENDED_EVSE

    # resume
    resp = await client.post(f"/resume/{connector_id}")
    assert resp.json()["ok"] is True
    status = await get_latest_status()
    assert status == {
        "connector_id": connector_id,
        "error_code": "NoError",
        "status": "Available",
    }
    assert evse.model.get(connector_id).state == EVSEState.AVAILABLE