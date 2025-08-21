# คู่มือการจำลองการใช้งาน CSMS (Windows 11 CMD)

## 1. ตรวจสอบว่าไม่มีเซสชัน active
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active

ควรได้ผลลัพธ์: {"sessions":[]}

---

## 2. จำลองการเสียบสายที่หัวชาร์จหมายเลข 1
curl -X POST http://localhost:7071/plug/1

---

## 3. สั่งเริ่มชาร์จ (Remote Start) ผ่าน CSMS
curl -X POST http://localhost:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1,\"id_tag\":\"VID:FCA47A147858\"}"

---

## 4. ตรวจสอบว่ามีเซสชัน active แล้ว
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active

ควรเห็น session ของ Gresgying02 พร้อม transactionId ที่ CSMS กำหนด

---

## 5. สั่งหยุดชาร์จ (Remote Stop)
curl -X POST http://localhost:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":1}"

---

## 6. ตรวจสอบอีกครั้งว่าไม่มีเซสชัน active
curl -H "X-API-Key: changeme-123" http://localhost:8080/api/v1/active

ควรได้ {"sessions":[]}

---

## 7. ดึงสายออกจากหัวชาร์จหมายเลข 1
curl -X POST http://localhost:7071/unplug/1

---

## ✅ สรุปขั้นตอนการจำลอง
- ขับรถเข้ามา
- เสียบสาย (plug)
- เริ่มชาร์จ (remote start)
- หยุดชาร์จ (remote stop)
- ถอดสาย (unplug)

ทั้งหมดสามารถตรวจสอบสถานะได้ผ่าน CSMS อย่างครบถ้วน 🚗⚡
