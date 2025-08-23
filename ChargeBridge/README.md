# ChargeBridge

Minimal orchestrator for EV charging sessions using OCPP 1.6j.
The WebSocket subprotocol can be customized for later OCPP versions,
and the project primarily targets Gresgying 120–180 kW DC charging
stations while remaining flexible for other models.

## Features
- `OCPPClient` for WebSocket communication with OCPP 1.6j and newer versions
- `ChargingSession` dataclass to manage meter readings and transaction IDs
- `central.py` orchestrator for demo start/stop session flow
- Session history and connector status APIs for energy use and plug state monitoring
- Primarily tested with Gresgying 120–180 kW DC chargers but adaptable to other stations

## Conda Installation

1. Install [Miniconda or Anaconda](https://docs.conda.io/en/latest/miniconda.html).
2. Create and activate an environment and install dependencies:

```bash
conda create -n chargebridge python=3.12
conda activate chargebridge
pip install websockets ocpp fastapi uvicorn
```

## Quick Start

Run the demo orchestrator after the environment is prepared:

```bash
python charging_controller.py
```

## Local Testing

1. Start the included `central.py` server or any OCPP simulator (e.g., `chargeforge-sim`):

```bash
python central.py
```

2. Point the client to the local server in `charging_controller.py` (note the Charge Point ID in the URL):

```python
client = OCPPClient(
    "ws://127.0.0.1:9000/ocpp/CP_1",
    "CP_1",
    ocpp_protocol="ocpp1.6",  # adjust for newer versions
    charger_model="Gresgying 120-180 kW DC",
)
```

3. Run the orchestrator:

```bash
python charging_controller.py
```

## Testing with a Remote Server

1. Ensure the remote machine exposes the OCPP port (e.g., `9000`).
2. Update `charging_controller.py` with the real IP address (e.g., `45.136.236.186`) and include the Charge Point ID in the path:

```python
client = OCPPClient(
    "ws://45.136.236.186:9000/ocpp/CP_1",
    "CP_1",
    ocpp_protocol="ocpp1.6",  # or another supported version
    charger_model="Gresgying 120-180 kW DC",
)
```

3. Start the client:

```bash
python charging_controller.py
```

## Connecting a Real Gresgying Charger

1. Configure the charger to use WebSocket URL `ws://<csms-host>:9000/ocpp/<ChargePointID>` with OCPP 1.6J.
2. If the charger supports remote operations, invoke `/api/v1/start` and `/api/v1/stop` as above.
3. Monitor logs from `central.py` for BootNotification, StatusNotification, StartTransaction, and StopTransaction events.

This setup has been validated with a Gresgying 120 kW–180 kW DC charging station using OCPP 1.6J over WebSocket.

## ตัวอย่างการใช้งาน (Example Usage)

The following steps demonstrate a full charging flow via the CSMS APIs. Replace `localhost` with `45.136.236.186` to interact with the live server.

### 1. ตรวจสอบว่าไม่มีเซสชัน active

```bash
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active
```

Expected result: `{"sessions":[]}`

---

### 2. จำลองการเสียบสายที่หัวชาร์จหมายเลข 1

```bash
curl -X POST http://localhost:7071/plug/1
```

---

### 3. สั่งเริ่มชาร์จ (Remote Start) ผ่าน CSMS

```bash
curl -X POST http://localhost:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1,\"id_tag\":\"VID:FCA47A147858\"}"
```

---

### 4. ตรวจสอบว่ามีเซสชัน active แล้ว

```bash
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active
```

The session for `Gresgying02` should now include the CSMS-assigned `transactionId`.

---

### 5. สั่งหยุดชาร์จ (Remote Stop)

```bash
curl -X POST http://localhost:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":1}"
```

---

### 6. ตรวจสอบอีกครั้งว่าไม่มีเซสชัน active

```bash
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active
```

Expected result: `{"sessions":[]}`

---

### 7. ดึงสายออกจากหัวชาร์จหมายเลข 1

```bash
curl -X POST http://localhost:7071/unplug/1
```

---

### 8. ตรวจสอบประวัติการชาร์จและพลังงานที่ใช้

```bash
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/history
```

The response includes `meterStart`, `meterStop`, `energy` (Wh), and `durationSecs` (seconds) for each session.

---

### 9. ตรวจสอบสถานะหัวชาร์จ

```bash
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/status
```

Lists each connector with its current OCPP status.

---

### ✅ สรุปขั้นตอนการจำลอง

- ขับรถเข้ามา
- เสียบสาย (plug)
- เริ่มชาร์จ (remote start)
- หยุดชาร์จ (remote stop)
- ถอดสาย (unplug)

Status can be monitored throughout via the CSMS.