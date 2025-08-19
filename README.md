## ✅ เช็กลิสต์งาน (อัปเดต)

### ทำแล้ว
- [x] Handle RemoteStartTransaction/RemoteStopTransaction (OCPP 1.6J)
- [x] เก็บ `transactionId` จาก StartTransaction.conf ต่อ connector
- [x] Stop โดยอ้างอิง `transactionId` ที่เก็บไว้
- [x] เพิ่ม `/health` และ Docker healthcheck
- [x] เพิ่ม reconnect loop ของ OCPP client

### TODO ต่อไป
- [ ] รองรับหลาย connector เต็มรูปแบบ (สั่ง remote พร้อมกันหลายเส้น)
- [ ] จำลอง faults/error codes และสถานะ SuspendedEV/EVSE
- [ ] เพิ่ม random fluctuation ของกระแส/แรงดัน/กำลัง (Measurand เพิ่มเติม)
- [ ] รองรับ WSS/TLS
- [ ] โหมด OCPP 2.0.1
- [ ] Integration tests (pytest)

### Requirements
- Python 3.10+ (ทดสอบกับ 3.12)
- ติดตั้ง dependencies ใน `sim/requirements.txt` (โดยใช้ `ocpp` 0.26.0 รองรับ OCPP 1.6J ผ่าน WebSocket)
