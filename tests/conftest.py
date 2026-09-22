from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from innovation.config import Settings

# .env ของ deployment ไม่ใช่ input ของเทสต์ — pydantic อ่านมันเทียบกับ cwd
# ทำให้ pytest จาก repo root ตั้งค่า Settings() ทุกตัวในสวีทจากไฟล์ที่บังเอิญมีในเครื่องใครเครื่องมัน
Settings.model_config["env_file"] = None
