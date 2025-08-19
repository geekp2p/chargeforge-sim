## ✅ เช็กลิสต์งาน

### ทำแล้ว
- [x] ตั้งชื่อโปรเจกต์: **ChargeForge-Sim**
- [x] โครงสร้างไฟล์ + Dockerfile + compose
- [x] EVSE emulator (OCPP 1.6J) เชื่อม CSMS ของคุณ
- [x] จำลองสถานะ: Available → Preparing → Charging → Finishing → Available
- [x] ส่ง StatusNotification, Heartbeat, MeterValues (พลังงาน Wh เพิ่มตามอัตรา)
- [x] รองรับการเริ่ม/หยุดจากฝั่ง local (HTTP control) และสอดรับกับ RemoteStart/Stop ของ CSMS
- [x] ตั้งค่าได้ผ่าน ENV: อัตราพลังงาน, คาบเวลาส่ง meter, จำนวน connector, CPID, CSMS_URL

### 📋 TODO ต่อไป
- [ ] รองรับหลาย connector แบบครบ flow RemoteStart/Stop แยกเส้น
- [ ] จับคู่ `transactionId` ที่ CSMS ออกเลข → เก็บกลับใน simulator เพื่อ stop แบบระบุ tx ตรง ๆ
- [ ] จำลอง faults/error codes (เช่น GroundFailure) และสถานะ SuspendedEV/EVSE
- [ ] สุ่ม fluctuation ค่าวัตต์/แรงดัน/กระแส (Measurand อื่น ๆ)
- [ ] เพิ่ม TLS/WSS สำหรับ OCPP (ใบ cert ทดสอบ)
- [ ] โหมด **OCPP 2.0.1** (แยกสาขา/ไดเรกทอรี)
- [ ] ชุด integration tests (pytest) ยิง REST ฝั่ง CSMS + ตรวจ state/metrics
