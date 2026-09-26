# Pratu (ประตู) — Clinical Front Door Interactive Showcase Prototype

ต้นแบบระบบสนับสนุนการตัดสินใจทางคลินิก (Interactive Research Prototype) สำหรับจัดแสดงและนำเสนอในการสอบ Senior Project

---

## 🚀 วิธีนำขึ้น Vercel (เลือกวิธีใดวิธีหนึ่ง)

### วิธีที่ 1: Deploy ผ่าน Terminal ด้วยคำสั่งเดียว (แนะนำ - ไม่ถึง 1 นาที)
1. เปิด Terminal แล้วเข้าไปที่โฟลเดอร์ `prototype/`:
   ```bash
   cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/prototype
   ```
2. รันคำสั่ง Vercel CLI (จะถาม login ครั้งแรกถ้ายังไม่เคย login):
   ```bash
   npx vercel --prod
   ```
3. กด Enter ยืนยันการตั้งค่าเริ่มต้น ระบบจะอัปโหลดและให้ลิงก์ URL ทันที เช่น `https://pratu-clinical-frontdoor-prototype.vercel.app`

---

### วิธีที่ 2: Deploy ผ่าน GitHub (สำหรับคนที่ต่อ Git กับ Vercel ไว้แล้ว)
1. Push โค้ดขึ้น GitHub Repository
2. ไปที่ [Vercel Dashboard](https://vercel.com/dashboard) -> คลิก **Add New Project**
3. เลือก Repository นี้
4. ในส่วน **Root Directory** ให้กด Edit แล้วเลือกโฟลเดอร์ `prototype`
5. กด **Deploy** จะได้ลิงก์พร้อมใช้งานอัตโนมัติ

---

## 💻 วิธีเปิดดูในเครื่องทันทีแบบ Local (ไม่ต้องต่อเน็ต)

### วิธี A: เปิดไฟล์ HTML ตรงๆ
ดับเบิ้ลคลิกไฟล์ `prototype/index.html` หรือเปิดในเบราว์เซอร์:
```bash
open prototype/index.html
```

### วิธี B: รัน Local Server จำลอง
```bash
python3 -m http.server 3000 --directory prototype
```
แล้วเปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:3000`

---

## 📱 จุดเด่นและลูกเล่นแบบ Interactive (สำหรับโชว์กรรมการ)

1. **แถบควบคุมด้านบน (Navigation Toolbar):**
   - สลับดูได้ทั้ง 8 หน้าจอทันที:
     - 🏥 **Pratu Intake:** Desktop | iPad (Tablet) | iPhone (Mobile) | ส่งต่อแล้ว (Handoff)
     - 🩺 **Pratu Console:** คิวเคส (Queue) | ตรวจเคส (Review) | Audit & Executed DAG
     - 📊 **ก่อน Redesign:** เปรียบเทียบภาพก่อน-หลังการปรับปรุง UI
   - ปุ่ม **"📱 กรอบอุปกรณ์"**: สลับระหว่างกรอบ Apple Device (iPhone/iPad) กับมุมมองขยายเต็มจอ
   - ปุ่ม **"ℹ️ ข้อมูลเคส (demo-014)"**: เปิด Modal สรุปประเด็นทางคลินิกของเคสจำลอง

2. **Flow การทำงานที่คลิกได้จริง:**
   - **หน้า Nurse Desktop:**
     - กดปุ่ม **"ยืนยัน"** ในการ์ดรอยืนยัน (เวลาเริ่มอาการ / อาการร่วม) -> ข้อมูลจะเด้งไปอยู่ส่วน "ยืนยันแล้ว" พร้อมอัปเดตหลอดความครบของข้อมูล (Progress Bar)
     - กดปุ่ม **"ส่งให้แพทย์ตรวจ"** -> เปลี่ยนไปหน้าส่งต่อสำเร็จ (Handoff)
     - กดปุ่ม **"แจ้งแพทย์เวร"** ในแถบสีแดง -> แสดงหน้าต่างแจ้งเตือนด่วน
     - คลื่นเสียง (Waveform) มีแอนิเมชันเคลื่อนไหว และกดหยุด/เริ่มบันทึกเสียงได้
   - **หน้า Platform Queue:**
     - คลิกที่เคส `demo-014` เพื่อเปิดหน้าตรวจเคส
     - ปุ่มกรอง (ด่วน, รอตรวจ, ต้องตรวจใหม่, ยืนยันแล้ว) กรองแถวในตารางได้จริง
   - **หน้า Platform Review:**
     - ตัวเลือกการตัดสินใจของแพทย์ (ยืนยัน / แก้ไข / ESCALATE / ปฏิเสธ) คลิกเลือกได้จริง
     - กด **"บันทึก ESCALATE"** -> ขึ้น Toast แจ้งเตือนและเปลี่ยนไปหน้า Audit Trail
   - **หน้า Platform Audit:**
     - แสดง Executed DAG พร้อมกล่องขั้นตอนการคำนวณที่คลิกดูรายละเอียดของแต่ละ Node ได้
