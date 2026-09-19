"""Builds the Front Door redesign canvas (v3: Gemini-inspired light theme): one .dc.html per screen plus canvas.json."""
import json
from pathlib import Path

ROOT = Path(__file__).parent / "project"
ROOT.mkdir(parents=True, exist_ok=True)

CSS = """
body{margin:0;background:#f3f1ec}
a{color:#0f766e}a:hover{color:#0b5a54}
.screen{box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;background:#f3f1ec;color:#111c26;font:400 15px/24px 'Noto Sans Thai',sans-serif}
.row{display:flex;align-items:center}.col{display:flex;flex-direction:column}.grow{flex-grow:1;min-width:0}
.display{font-family:'Noto Sans Thai',sans-serif;font-weight:500;letter-spacing:-0.01em}
.mono{font-family:'Roboto Mono',monospace;font-size:13px;letter-spacing:0}
.meta{font-size:13px;line-height:20px;color:#5b6670}
.strong{font-weight:600}
.eyebrow{font-size:12px;line-height:16px;letter-spacing:0.06em;text-transform:uppercase;color:#5b6670;font-weight:600}
.chrome{background:#f2f0f0;color:#1f1f1f}
.chrome .meta{color:#444746}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:13px;line-height:20px;font-weight:600;white-space:nowrap}
.p-urgent{background:#b42318;color:#fff}.p-warn{background:#fdf3e1;color:#8a4b05}.p-ok{background:#e6f4ec;color:#146c40}
.p-info{background:#e5f1f6;color:#155e75}.p-neutral{background:#ecebe6;color:#3b4751}.p-teal{background:#e3f2ef;color:#0b5a54}
.p-proto{border:1px solid #e6c47a;color:#7a4f00;background:#fff3dc}
.p-proto-light{border:1px solid #d9a441;color:#8a4b05;background:#fdf3e1}
.btn{box-sizing:border-box;height:40px;padding:0 16px;border-radius:9999px;font:500 15px/24px 'Noto Sans Thai',sans-serif;display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid transparent;background:none;color:#111c26;cursor:pointer;white-space:nowrap;text-decoration:none}
.btn-primary{background:#0f766e;color:#fff}.btn-primary:hover{background:#0b5a54;color:#fff}
.btn-ink{background:#0b1f2e;color:#fff}.btn-ink:hover{background:#3c3c3c;color:#fff}
.btn-secondary{background:#fff;border-color:#d5d1c6}
.btn-ghost-light{color:#0b57d0;background:#fff;border-color:#c4c7c5}.btn-ghost-light:hover{background:#eef3fd;color:#0842a0}
.btn-white{background:#fff;color:#b42318}
.btn-text{color:#0f766e;padding:0 6px}
.btn-lg{height:48px;padding:0 20px;font-size:16px}
.card{background:#fff;border:1px solid #efefef;border-radius:28px;box-shadow:rgba(0,0,0,0.04) 0 0 20px 0}
.line-b{border-bottom:1px solid #e4e1d8}.line-t{border-top:1px solid #e4e1d8}
.icon{flex-shrink:0}
.tr{display:grid;align-items:center;padding:14px 20px;border-bottom:1px solid #eeebe4;gap:16px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 12px;border-radius:9999px;background:#f3f1ec;border:1px solid #e4e1d8;font-size:13px;line-height:20px;color:#3b4751;text-decoration:none}
"""

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600&amp;family=Roboto+Mono:wght@500&amp;display=swap" rel="stylesheet">'


def ic(name, size=18, color="currentColor", sw="1.8"):
    paths = {
        "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
        "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
        "alert": '<path d="M12 4 2.8 19.5h18.4Z"/><path d="M12 10v4.5M12 17.2v.3"/>',
        "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
        "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
        "stop": '<rect x="7" y="7" width="10" height="10" rx="2"/>',
        "send": '<path d="M4 12 20 4l-4 16-4-6.5Z"/><path d="M12 13.5 20 4"/>',
        "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15Z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
        "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
        "flask": '<path d="M9.5 3.5h5M10 3.5v6L4.8 18.3A1.6 1.6 0 0 0 6.2 20.7h11.6a1.6 1.6 0 0 0 1.4-2.4L14 9.5v-6"/><path d="M7.5 15h9"/>',
        "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
        "user": '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
        "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
        "edit": '<path d="M4 20h4L19 9l-4-4L4 16Z"/>',
        "chev": '<path d="M9 6l6 6-6 6"/>',
        "door": '<path d="M6 20V6.5a6 6 0 0 1 12 0V20"/><path d="M4 20h16"/><circle cx="14.5" cy="13.5" r="0.9" fill="currentColor"/>',
        "wave": '',
    }
    return f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>'


def wave(bars=38, h=28, color="#0f766e"):
    import math
    rects = []
    for i in range(bars):
        v = 0.25 + 0.75 * abs(math.sin(i * 0.55) * math.cos(i * 0.17))
        bh = max(3, round(h * v))
        rects.append(f'<rect x="{i * 5}" y="{(h - bh) / 2}" width="3" height="{bh}" rx="1.5" fill="{color}"/>')
    return f'<svg width="{bars * 5}" height="{h}" viewBox="0 0 {bars * 5} {h}" aria-hidden="true">{"".join(rects)}</svg>'


THEME = [
    ("#0b1f2e", "#1f1f1f"), ("#16324a", "#ffffff"), ("#2c4a61", "#dcdada"), ("#9fb1bf", "#444746"), ("#e8eef2", "#1f1f1f"),
    ("#0f766e", "#0b57d0"), ("#0b5a54", "#0842a0"), ("#e3f2ef", "#d3e3fd"), ("#b9ddd6", "#a8c7fa"), ("#1f3a36", "#041e49"), ("#eef7f5", "#eef3fd"),
    ("#111c26", "#1f1f1f"), ("#5b6670", "#444746"), ("#3b4751", "#444746"), ("#9aa3ab", "#747775"),
    ("#e4e1d8", "#e3e3e3"), ("#eeebe4", "#efefef"), ("#d5d1c6", "#c4c7c5"), ("#c9c4b8", "#c4c7c5"),
    ("#f3f1ec", "#faf9f9"), ("#faf9f6", "#f2f0f0"), ("#ecebe6", "#f2f0f0"),
    ("#b42318", "#b3261e"), ("#fdecea", "#f9dedc"), ("#fff5f4", "#fcefee"), ("#ffd9d4", "#f9dedc"), ("#f1b5ae", "#f2b8b5"),
    ("#8a4b05", "#7a4f00"), ("#a15c07", "#8c5a00"), ("#fdf3e1", "#fff3dc"), ("#efd6a3", "#f3dca8"), ("#fffaf0", "#fffbf3"), ("#d9a441", "#e6c47a"),
    ("#146c40", "#146c2e"), ("#e6f4ec", "#e6f4ea"), ("#155e75", "#0842a0"), ("#e5f1f6", "#d3e3fd"),
    ("rgba(11,31,46,0.06)", "rgba(0,0,0,0.04)"), ("rgba(11,31,46,0.05)", "rgba(0,0,0,0.04)"),
    ("border-radius: 8px;", "border-radius: 9999px;"), ("border-radius: 10px;", "border-radius: 20px;"), ("border-radius: 12px;", "border-radius: 24px;"), ("border-radius: 14px;", "border-radius: 28px;"),
]


def themed(html):
    for a, b in THEME:
        html = html.replace(a, b)
    return html


def page(title, w, h, body, logic=""):
    logic = logic or "class Component extends DCLogic {\n  renderVals() { return {}; }\n}"
    props = json.dumps({"$preview": {"width": w, "height": h}})
    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
{FONTS}
<style>{themed(CSS)}</style>
</helmet>
<div class="screen" style="width: {w}px; height: {h}px;">
{themed(body)}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{props}'>
{themed(logic)}
</script>
</body>
</html>
"""


BRAND = f'<span class="row" style="gap: 10px;"><span class="row" style="width: 30px; height: 30px; border-radius: 8px; background: #0f766e; justify-content: center;">{ic("door", 18, "#fff", "2")}</span><span class="display" style="font-size: 17px; color: #1f1f1f;">Front Door</span></span>'


# ---------- Nurse ----------
def nurse_topbar(compact=False):
    case = '<span class="mono" style="color: #1f1f1f; font-size: 14px;">demo-014</span>'
    info = "" if compact else '<span class="meta">ชาย 58 ปี</span><span class="meta">·</span><span class="row meta" style="gap: 4px;">' + ic("clock", 15, "#444746") + 'มาถึง 09:10 · รอ 12 นาที</span>'
    proto = "" if compact else '<span class="pill p-proto">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span>'
    return f"""<header class="chrome row" style="height: 60px; padding: 0 24px; gap: 16px; flex-shrink: 0;">{BRAND}<span style="width: 1px; height: 24px; background: #2c4a61;"></span>
<span class="meta" style="color: #9fb1bf;">Nurse Intake</span><span class="row" style="gap: 10px; padding: 6px 12px; border-radius: 8px; background: #16324a;">{case}{info}</span>
<span class="grow"></span>{proto}<a class="btn btn-ghost-light" href="Platform-Queue.dc.html">Central Platform</a>
<span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: #e3f2ef; color: #0b5a54; justify-content: center; font-size: 14px;">NA</span></header>"""


def urgency_band(compact=False):
    more = "" if compact else '<span style="opacity: 0.9;">· ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ แพทย์ต้องประเมินเอง</span>'
    btn = "" if compact else f'<button class="btn btn-white" type="button">{ic("bell", 17, "#b42318")}แจ้งแพทย์เวร</button>'
    return f"""<div class="row" style="background: #b42318; color: #fff; padding: {10 if compact else 12}px {16 if compact else 24}px; gap: 14px; flex-shrink: 0;">{ic("alert", 22, "#fff", "2")}
<div class="{'col' if compact else 'row'} grow" style="gap: {2 if compact else 10}px; {'' if compact else 'flex-wrap: wrap;'}"><span class="display" style="font-size: {16 if compact else 18}px;">ต้องให้แพทย์ดูโดยเร็ว</span><span style="{'font-size: 14px; line-height: 20px;' if compact else ''}">ข้อมูลที่จำเป็นยังไม่ครบ: ขาดสัญญาณชีพ</span>{more}</div>{btn}</div>"""


def msg_nurse(t, text):
    return f"""<div class="row" style="align-items: flex-start; gap: 14px;"><span class="row display" style="width: 32px; height: 32px; border-radius: 999px; background: #0b1f2e; color: #fff; justify-content: center; font-size: 12px; flex-shrink: 0;">NA</span>
<div class="col grow" style="gap: 2px;"><span class="row" style="gap: 8px;"><span class="strong" style="font-size: 14px;">พยาบาล</span><span class="mono" style="color: #5b6670;">{t}</span></span><p style="margin: 0; font-size: 16px; line-height: 26px;">{text}</p></div></div>"""


def msg_assistant(t, text, chips):
    c = "".join(f'<a class="chip" href="#pending" style="background: #fff; border-color: #b9ddd6; color: #0b5a54;">{ic("list", 14, "#0f766e")}{x}</a>' for x in chips)
    return f"""<div class="row" style="align-items: flex-start; gap: 14px;"><span class="row" style="width: 32px; height: 32px; border-radius: 999px; background: #e3f2ef; justify-content: center; flex-shrink: 0;">{ic("list", 16, "#0f766e")}</span>
<div class="col grow" style="gap: 8px; background: #e3f2ef; border-radius: 4px 12px 12px 12px; padding: 12px 14px;"><span class="row" style="gap: 8px;"><span class="strong" style="font-size: 14px; color: #0b5a54;">ผู้ช่วย · ข้อเสนอรอตรวจ</span><span class="mono" style="color: #5b6670;">{t}</span></span>
<p style="margin: 0; color: #1f3a36;">{text}</p><div class="row" style="gap: 6px; flex-wrap: wrap;">{c}</div></div></div>"""


CONVO = [
    msg_nurse("09:12", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกตั้งแต่เช้า ร้าวไปแขนซ้าย"),
    msg_assistant("09:12", "บันทึกอาการสำคัญเป็นข้อเสนอแล้ว · ควรถามต่อ: เริ่มเจ็บกี่โมง มีเหงื่อแตกหรือหายใจลำบากหรือไม่", ["อาการสำคัญ"]),
    msg_nurse("09:14", "เริ่มประมาณ 7 โมงเช้า มีเหงื่อออก ไม่มีหายใจลำบาก"),
    msg_assistant("09:14", "เสนอข้อมูล 2 รายการ · ยังไม่มีสัญญาณชีพ ควรวัดก่อนส่งต่อ", ["เวลาเริ่มอาการ 07:00", "อาการร่วม: เหงื่อออก"]),
]


def recorder(compact=False):
    return f"""<div class="col" style="background: #fff; border: 1px solid #e4e1d8; border-radius: 14px; box-shadow: 0 8px 24px rgba(11,31,46,0.06); padding: {12 if compact else 16}px; gap: 12px;">
<div class="row" style="gap: 12px;"><span class="row" style="gap: 8px; color: #b42318; font-weight: 600;"><span style="width: 9px; height: 9px; border-radius: 999px; background: #b42318;"></span>กำลังฟัง</span><span class="mono" style="color: #5b6670;">00:14</span>
<span class="grow" style="overflow: hidden;">{wave(24 if compact else 60)}</span></div>
<p style="margin: 0; color: #3b4751; font-style: italic;">“…วัดความดันแล้วได้ 150 ต่อ 90 ชีพจร…”</p>
<div class="row" style="gap: 10px;"><button class="btn btn-ink btn-lg" type="button" aria-label="หยุดบันทึก">{ic("stop", 18, "#fff", "2")}{'' if compact else 'หยุดบันทึก'}</button>
<span class="meta grow">{'' if compact else 'ถอดเสียงแล้วแก้ข้อความได้ก่อนส่ง · ไม่บันทึกข้อมูลระบุตัวผู้ป่วยจริง'}</span><button class="btn btn-primary btn-lg" type="button">{ic("send", 18, "#fff", "2")}ส่งให้ผู้ช่วย</button></div></div>"""


def progress(filled=3, pending=2, total=6, dark=False):
    seg = []
    for i in range(total):
        color = "#0f766e" if i < filled else "#e8b04b" if i < filled + pending else "#e4e1d8"
        seg.append(f'<span style="flex-grow: 1; height: 8px; border-radius: 4px; background: {color};"></span>')
    return f"""<div class="col" style="gap: 10px;"><div class="row" style="align-items: baseline; gap: 8px;"><span class="display" style="font-size: 32px; line-height: 36px;">{filled}<span style="color: #9aa3ab; font-size: 20px;">/{total}</span></span><span class="meta">ข้อมูลจำเป็นยืนยันแล้ว</span></div>
<div class="row" style="gap: 4px;">{''.join(seg)}</div><div class="row meta" style="gap: 14px;"><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #0f766e;"></span>ยืนยัน {filled}</span><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #e8b04b;"></span>รอยืนยัน {pending}</span><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #e4e1d8;"></span>ยังขาด {total - filled - pending}</span></div></div>"""


def pending_card(label, value, src):
    return f"""<div class="col" style="border: 1px solid #efd6a3; background: #fffaf0; border-radius: 10px; padding: 12px 14px; gap: 8px;"><div class="col" style="gap: 0;"><span class="meta">{label} · {src}</span><span class="strong" style="font-size: 16px;">{value}</span></div>
<div class="row" style="gap: 8px;"><button class="btn btn-primary" type="button" style="height: 36px;">{ic("check", 16, "#fff", "2.2")}ยืนยัน</button><button class="btn btn-text" type="button" style="height: 36px;">{ic("edit", 15, "#0f766e")}แก้ไข</button></div></div>"""


def done_row(label, value, who):
    return f'<div class="row line-t" style="gap: 12px; padding: 10px 0; align-items: flex-start;"><span class="row" style="width: 22px; height: 22px; border-radius: 999px; background: #e6f4ec; justify-content: center; margin-top: 2px;">{ic("check", 14, "#146c40", "2.4")}</span><div class="col grow"><span class="meta">{label}</span><span class="strong">{value}</span></div><span class="mono" style="color: #9aa3ab;">{who}</span></div>'


def missing_row(label, value):
    return f'<div class="row line-t" style="gap: 12px; padding: 10px 0; align-items: flex-start;"><span class="row" style="width: 22px; height: 22px; border-radius: 999px; background: #fdecea; justify-content: center; margin-top: 2px;">{ic("alert", 13, "#b42318", "2.2")}</span><div class="col grow"><span class="meta">{label}</span><span class="strong">{value}</span></div><button class="btn btn-text" type="button" style="height: 32px;">ถามต่อ</button></div>'


def rail(sent=False, pad=24):
    pending = "" if sent else f'<section id="pending" class="col" style="gap: 10px;"><div class="row"><span class="eyebrow">รอคุณยืนยัน · 2</span></div>{pending_card("เวลาเริ่มอาการ", "07:00 น. วันนี้", "จากข้อความ 09:14")}{pending_card("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "จากข้อความ 09:14")}</section>'
    confirmed = [done_row("อาการสำคัญ", "เจ็บแน่นหน้าอก ร้าวไปแขนซ้าย", "09:12"), done_row("อายุ · เพศ", "58 ปี · ชาย", "เคส")]
    if sent:
        confirmed += [done_row("เวลาเริ่มอาการ", "07:00 น. วันนี้", "09:16"), done_row("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "09:16")]
    return f"""<aside class="col" style="padding: {pad}px; gap: 24px; overflow: hidden; background: #fff;">
<section class="col" style="gap: 6px;"><span class="eyebrow">ความครบของข้อมูล</span>{progress(5 if sent else 3, 0 if sent else 2)}</section>
{pending}
<section class="col"><span class="eyebrow" style="padding-bottom: 6px;">ยืนยันแล้ว · {len(confirmed)}</span>{''.join(confirmed)}</section>
<section class="col"><span class="eyebrow" style="padding-bottom: 6px;">ยังขาด · 1</span>{missing_row("สัญญาณชีพ", "ความดัน ชีพจร อัตราการหายใจ SpO₂")}</section></aside>"""


def handoff(sent=False):
    if sent:
        steps = [("ส่งให้แพทย์", "09:20", "done"), ("แพทย์เปิดดู", "09:22", "done"), ("แพทย์ตัดสินใจ", "รอ", "now")]
        s = []
        for i, (a, b, st) in enumerate(steps):
            dot = {"done": f'<span class="row" style="width: 24px; height: 24px; border-radius: 999px; background: #0f766e; justify-content: center;">{ic("check", 14, "#fff", "2.6")}</span>',
                   "now": '<span style="width: 24px; height: 24px; box-sizing: border-box; border-radius: 999px; border: 3px solid #e8b04b; background: #fff;"></span>'}[st]
            s.append(f'<span class="row" style="gap: 10px;">{dot}<span class="col"><span class="strong" style="color: #1f1f1f;">{a}</span><span class="mono" style="color: #9fb1bf;">{b}</span></span></span>')
            if i < len(steps) - 1:
                s.append('<span style="width: 48px; height: 2px; background: #2c4a61;"></span>')
        return f"""<footer class="chrome row" style="height: 80px; padding: 0 24px; gap: 18px; flex-shrink: 0;">{''.join(s)}<span class="grow"></span>
<span class="meta" style="max-width: 300px;">ได้ข้อมูลเพิ่มบันทึกต่อได้ ร่างจะถูกทำเครื่องหมายให้สร้างใหม่</span><a class="btn btn-ghost-light" href="Platform-Review.dc.html">ดูในแพลตฟอร์ม</a><button class="btn btn-primary" type="button">รับเคสถัดไป{ic("arrow", 17, "#fff", "2")}</button></footer>"""
    return f"""<footer class="row" style="height: 80px; padding: 0 24px; gap: 16px; flex-shrink: 0; background: #fff; border-top: 1px solid #e4e1d8; box-shadow: 0 -8px 24px rgba(11,31,46,0.05);">
<div class="col"><span class="strong" style="font-size: 16px;">พร้อมส่งให้แพทย์ด้วยข้อมูลที่ยืนยันแล้ว 3 รายการ</span><span class="row meta" style="gap: 6px; color: #8a4b05;">{ic("alert", 14, "#a15c07", "2")}ยังขาดสัญญาณชีพ แพทย์จะเห็นว่าข้อมูลนี้ขาด · รอยืนยันอีก 2 รายการ</span></div>
<span class="grow"></span><button class="btn btn-text" type="button">บันทึกไว้ก่อน</button><a class="btn btn-primary btn-lg" href="Nurse-Handoff.dc.html">ส่งให้แพทย์ตรวจ{ic("arrow", 18, "#fff", "2")}</a></footer>"""


def nurse(stacked=False, sent=False):
    convo_head = f"""<div class="row" style="gap: 12px;"><h1 class="display" style="margin: 0; font-size: 22px;">ซักประวัติ</h1><span class="grow"></span>
<div class="row" role="group" aria-label="โหมดรับข้อมูล" style="background: #ecebe6; border-radius: 8px; padding: 3px;"><button type="button" class="btn" aria-pressed="true" style="height: 32px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08);">{ic("mic", 15)}เสียง</button><button type="button" class="btn" aria-pressed="false" style="height: 32px; color: #5b6670;">ข้อความ</button></div></div>"""
    main = f"""<main class="col grow" style="padding: 24px {24 if stacked else 40}px; gap: 20px; min-height: 0;">{convo_head}
<div class="col {'' if stacked else 'grow'}" style="gap: 18px; overflow: hidden;">{''.join(CONVO)}</div>{recorder(compact=stacked)}</main>"""
    side = rail(sent)
    if stacked:
        body = f'<div class="col grow" style="min-height: 0; overflow: hidden;">{main}<div style="border-top: 1px solid #e4e1d8;">{side}</div></div>'
    else:
        body = f'<div class="row grow" style="align-items: stretch; min-height: 0;">{main}<div style="width: 420px; flex-shrink: 0; border-left: 1px solid #e4e1d8; display: flex; flex-direction: column;">{side}</div></div>'
    return nurse_topbar(stacked) + urgency_band(stacked) + body + handoff(sent)


MOBILE_LOGIC = """class Component extends DCLogic {
  constructor(props) { super(props); this.state = { tab: 'chat' }; }
  renderVals() {
    const on = 'background: #fff; color: #111c26; box-shadow: 0 1px 2px rgba(0,0,0,0.08);';
    const off = 'background: transparent; color: #5b6670;';
    const tab = this.state.tab;
    return {
      chat: tab === 'chat', facts: tab === 'facts',
      showChat: () => this.setState({ tab: 'chat' }), showFacts: () => this.setState({ tab: 'facts' }),
      chatTab: tab === 'chat' ? on : off, factsTab: tab === 'facts' ? on : off,
    };
  }
}"""


def mobile():
    tb = "flex-grow: 1; height: 40px; border: none; border-radius: 8px; font: 600 15px/24px 'Noto Sans Thai',sans-serif; cursor: pointer;"
    chat = "".join(CONVO[2:])
    body = f"""<header class="chrome row" style="height: 56px; padding: 0 16px; gap: 10px; flex-shrink: 0;"><span class="row" style="width: 28px; height: 28px; border-radius: 8px; background: #0f766e; justify-content: center;">{ic("door", 16, "#fff", "2")}</span>
<span class="col"><span class="mono" style="color: #1f1f1f;">demo-014</span><span class="meta" style="font-size: 12px; line-height: 16px;">ชาย 58 · รอ 12 นาที</span></span><span class="grow"></span><button class="btn btn-ghost-light" type="button" style="height: 44px;">เปลี่ยนเคส</button></header>
{urgency_band(compact=True)}
<div class="row" role="tablist" aria-label="มุมมองเคส" style="margin: 12px 16px 0; background: #ecebe6; border-radius: 10px; padding: 4px; gap: 4px;"><button type="button" role="tab" style="{tb} @@chatTab@@" onClick="@@showChat@@">บทสนทนา</button><button type="button" role="tab" style="{tb} @@factsTab@@" onClick="@@showFacts@@">ข้อมูล · <span style="color: #a15c07;">2 รอ</span></button></div>
<sc-if value="@@chat@@" hint-placeholder-val="@@true@@">
<div class="col grow" style="padding: 16px; gap: 16px; overflow: hidden;">{chat}</div>
<div class="col" style="background: #fff; border-top: 1px solid #e4e1d8; padding: 12px 16px 20px; gap: 10px;">
<div class="row" style="gap: 8px;"><span style="width: 8px; height: 8px; border-radius: 999px; background: #b42318;"></span><span class="strong" style="color: #b42318; font-size: 14px;">กำลังฟัง</span><span class="mono" style="color: #5b6670;">00:14</span><span class="grow" style="overflow: hidden;">{wave(26, 22)}</span></div>
<div class="row" style="gap: 12px; justify-content: center;"><button class="btn btn-secondary" type="button" style="height: 48px;">ข้อความ</button><button type="button" aria-label="หยุดบันทึก" class="row" style="width: 64px; height: 64px; border-radius: 999px; background: #0b1f2e; border: 4px solid #e3f2ef; justify-content: center; cursor: pointer;">{ic("stop", 22, "#fff", "2.2")}</button><button class="btn btn-primary" type="button" style="height: 48px;">ส่ง</button></div></div>
</sc-if>
<sc-if value="@@facts@@" hint-placeholder-val="@@false@@">
<div class="col grow" style="padding: 16px; gap: 18px; overflow: hidden;">{progress()}<section class="col" style="gap: 10px;"><span class="eyebrow">รอคุณยืนยัน · 2</span>{pending_card("เวลาเริ่มอาการ", "07:00 น. วันนี้", "09:14")}{pending_card("อาการร่วม", "เหงื่อออก", "09:14")}</section></div>
<div class="col" style="background: #fff; border-top: 1px solid #e4e1d8; padding: 12px 16px 20px; gap: 6px;"><span class="meta" style="text-align: center;">ยืนยันข้อมูลที่รออยู่ก่อน จึงจะส่งให้แพทย์ได้</span><button class="btn btn-primary btn-lg" type="button" disabled="disabled" style="opacity: 0.45;">ส่งให้แพทย์ตรวจ</button></div>
</sc-if>"""
    return body.replace("@@", "{{").replace("{{chatTab{{", "{{chatTab}}")


def fix_holes(s):
    import re
    return re.sub(r"\{\{(\w+)\{\{", r"{{\1}}", s)


# ---------- Platform ----------
def platform_shell(active, main):
    items = [("คิวเคส", "list", "Platform-Queue.dc.html", "4"), ("การทดลอง Agent", "flask", "#", None), ("สถานะระบบ", "gauge", "#", None)]
    nav = []
    for label, icon, href, count in items:
        on = label == active
        badge = f'<span class="pill" style="background: #0f766e; color: #fff; padding: 0 8px;">{count}</span>' if count else ""
        nav.append(f'<a href="{href}" class="row" style="gap: 12px; padding: 10px 12px; border-radius: 8px; text-decoration: none; {"background: #d3e3fd; color: #041e49;" if on else "color: #444746;"}">{ic(icon, 18, "#041e49" if on else "#444746")}<span class="grow" style="font-weight: 600;">{label}</span>{badge}</a>')
    return f"""<div class="row grow" style="align-items: stretch; min-height: 0;">
<nav class="chrome col" aria-label="เมนูหลัก" style="width: 240px; flex-shrink: 0; padding: 20px 14px; gap: 4px;">
<div style="padding: 0 8px 24px;">{BRAND}<div class="meta" style="padding-top: 4px; padding-left: 40px;">Central Platform</div></div>
{''.join(nav)}<span class="grow"></span>
<div class="col" style="margin: 0 4px; padding: 12px; border-radius: 10px; background: #16324a; gap: 10px;"><div class="row" style="gap: 10px;"><span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: #e3f2ef; color: #0b5a54; justify-content: center; font-size: 13px;">SC</span><span class="col"><span class="strong" style="color: #1f1f1f; font-size: 14px;">dr.somchai</span><span class="meta" style="font-size: 12px;">แพทย์ผู้ตรวจ · เวรเช้า</span></span></div>
<a class="btn btn-ghost-light" href="Main.dc.html" style="height: 36px;">{ic("mic", 16, "#0b57d0")}Nurse Intake</a></div>
</nav><div class="col grow" style="min-height: 0;">{main}</div></div>"""


def kpi(value, unit, label, color="#111c26", note=""):
    return f"""<div class="card col" style="flex: 1 1 0; padding: 18px 20px; gap: 4px;"><span class="eyebrow">{label}</span><span class="row" style="align-items: baseline; gap: 6px;"><span class="display" style="font-size: 36px; line-height: 44px; color: {color};">{value}</span><span class="meta">{unit}</span></span><span class="meta">{note}</span></div>"""


QROWS = [
    ("demo-014", "ชาย 58", "urgent", "ดูโดยเร็ว", "ข้อมูลที่จำเป็นยังไม่ครบ", "ขาดสัญญาณชีพ", 12, "NA", ("p-info", "รอตรวจ"), True),
    ("demo-012", "ชาย 71", "urgent", "ดูโดยเร็ว", "ข้อมูลที่จำเป็นยังไม่ครบ", "ขาดประวัติยา", 19, "NB", ("p-warn", "ต้องตรวจใหม่"), False),
    ("demo-011", "หญิง 45", "warn", "ข้อมูลยังไม่พอ", "นอกขอบเขตที่ประเมินไว้", "", 23, "NA", ("p-neutral", "ยังไม่มีร่าง"), False),
    ("demo-013", "หญิง 34", "neutral", "ตามคิวปกติ", "ไม่พบเงื่อนไข", "", 8, "NC", ("p-ok", "ยืนยันแล้ว"), False),
    ("demo-010", "ชาย 29", "neutral", "ตามคิวปกติ", "ไม่พบเงื่อนไข", "", 31, "NB", ("p-urgent", "ถูกปฏิเสธ"), False),
]
QCOLS = "grid-template-columns: 120px 92px 150px minmax(0, 1fr) 150px 60px 130px 24px;"


def queue():
    head = "".join(f'<span class="eyebrow">{h}</span>' for h in ["เคส", "ผู้ป่วย", "ความเร่งด่วน", "ผลคัดกรองก่อนใช้โมเดล", "รอแล้ว", "พยาบาล", "ร่างส่งต่อ", ""])
    rows = []
    for cid, pt, lvl, ulab, flag, fsub, wait, nurse, (dcls, dlab), sel in QROWS:
        u = {"urgent": f'<span class="pill p-urgent">{ic("alert", 13, "#fff", "2.4")}{ulab}</span>', "warn": f'<span class="pill p-warn">{ulab}</span>', "neutral": f'<span class="pill p-neutral">{ulab}</span>'}[lvl]
        fcol = "#b42318" if lvl == "urgent" else "#8a4b05" if lvl == "warn" else "#5b6670"
        barw = min(100, wait * 3)
        barc = "#b42318" if wait >= 20 else "#e8b04b" if wait >= 10 else "#0f766e"
        sub = f'<span class="meta">{fsub}</span>' if fsub else ""
        cid_el = f'<a href="Platform-Review.dc.html" class="mono strong" style="color: #111c26; font-size: 14px;">{cid}</a>' if sel else f'<span class="mono" style="font-size: 14px;">{cid}</span>'
        rows.append(f"""<div class="tr" style="{QCOLS} {'background: #eef7f5; box-shadow: inset 3px 0 0 #0f766e;' if sel else ''}">{cid_el}<span>{pt}</span><span>{u}</span>
<span class="col"><span style="color: {fcol}; font-weight: 500;">{flag}</span>{sub}</span>
<span class="col" style="gap: 4px;"><span class="mono">{wait} นาที</span><span style="height: 4px; border-radius: 2px; background: #eeebe4;"><span style="display: block; width: {barw}%; height: 4px; border-radius: 2px; background: {barc};"></span></span></span>
<span class="row display" style="width: 30px; height: 30px; border-radius: 999px; background: #ecebe6; color: #3b4751; justify-content: center; font-size: 12px;">{nurse}</span><span><span class="pill {dcls}">{dlab}</span></span>{ic("chev", 18, "#9aa3ab")}</div>""")
    filters = "".join(f'<button type="button" class="btn" style="height: 34px; border-radius: 999px; {"background: #0b1f2e; color: #fff;" if i == 0 else "background: #fff; border: 1px solid #e4e1d8; color: #3b4751;"}">{f}</button>' for i, f in enumerate(["ทั้งหมด 12", "ด่วน 2", "รอตรวจ 4", "ต้องตรวจใหม่ 1", "ยืนยันแล้ว 6"]))
    main = f"""<div class="col grow" style="padding: 28px 36px; gap: 22px; min-height: 0;">
<div class="row" style="gap: 14px;"><div class="col"><span class="meta">วันเสาร์ 19 ก.ย. 2569 · ED first contact</span><h1 class="display" style="margin: 0; font-size: 30px; line-height: 38px;">คิวเคสวันนี้</h1></div><span class="grow"></span><span class="pill p-proto-light">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span><span class="pill p-neutral">Offline · mock provider</span><button class="btn btn-primary" type="button">เริ่มเคสจำลอง</button></div>
<div class="row" style="gap: 16px; align-items: stretch;">{kpi("4", "เคส", "รอแพทย์ตรวจ", note="เก่าสุดรอ 23 นาที")}{kpi("2", "เคส", "ต้องดูโดยเร็ว", "#b42318", "ทั้งคู่ขาดข้อมูลจำเป็น")}{kpi("14", "นาที", "เวลารอเฉลี่ย", note="ตั้งแต่ส่งถึงแพทย์เปิดดู")}{kpi("6", "เคส", "ยืนยันแล้ววันนี้", "#146c40", "ถูกปฏิเสธ 1 · แก้ไข 2")}</div>
<div class="row" style="gap: 8px;"><div class="row" style="width: 300px; height: 40px; box-sizing: border-box; border: 1px solid #d5d1c6; border-radius: 8px; background: #fff; padding: 0 12px; gap: 8px; color: #9aa3ab;"><svg class="icon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#9aa3ab" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/></svg>ค้นหารหัสเคส</div>{filters}</div>
<div class="card col" style="overflow: hidden;"><div class="tr" style="{QCOLS} background: #faf9f6; padding-top: 10px; padding-bottom: 10px;">{head}</div>{''.join(rows)}</div>
</div>"""
    return platform_shell("คิวเคส", main)


def case_header(active):
    tabs = [("ข้อมูลเคส", "#"), ("ร่างและตัดสินใจ", "Platform-Review.dc.html"), ("Audit และ trace", "Platform-Audit.dc.html")]
    t = "".join(f'<a href="{h}" style="padding: 14px 2px; text-decoration: none; font-weight: 600; {"color: #111c26; box-shadow: inset 0 -3px 0 #0f766e;" if l == active else "color: #5b6670;"}">{l}</a>' for l, h in tabs)
    facts = "".join(f'<span class="col"><span class="eyebrow">{a}</span><span class="strong">{b}</span></span>' for a, b in [("ผู้ป่วย", "ชาย 58 ปี"), ("มาถึง", "09:10"), ("รอแล้ว", "12 นาที"), ("ข้อมูลรุ่น", "6"), ("พยาบาล", "nurse.a")])
    return f"""<header class="col" style="background: #fff; border-bottom: 1px solid #e4e1d8; padding: 20px 36px 0; gap: 14px; flex-shrink: 0;">
<div class="row" style="gap: 14px;"><a class="btn btn-text" href="Platform-Queue.dc.html" style="padding: 0;">{ic("arrow", 16, "#0f766e", "2")}<span>คิวเคส</span></a></div>
<div class="row" style="gap: 16px;"><h1 class="mono" style="margin: 0; font-size: 26px; line-height: 32px; font-weight: 500;">demo-014</h1><span class="pill p-urgent">{ic("alert", 13, "#fff", "2.4")}ต้องให้แพทย์ดูโดยเร็ว</span><span class="pill p-proto-light">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span><span class="grow"></span><div class="row" style="gap: 28px;">{facts}</div></div>
<nav class="row" style="gap: 28px;">{t}</nav></header>"""


def review():
    ev = lambda code, label: f'<a class="chip" href="#"><span class="mono" style="color: #0f766e;">{code}</span>{label}</a>'
    sections = [
        ("สรุป", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกร้าวไปแขนซ้ายตั้งแต่ 07:00 น. มีเหงื่อออก ไม่มีหายใจลำบาก <mark style=\"background: #fdecea; color: #b42318; padding: 0 4px; border-radius: 4px;\">ยังไม่มีสัญญาณชีพ</mark>", [ev("E-0912", "อาการสำคัญ"), ev("E-0916a", "เวลาเริ่มอาการ"), ev("E-0916b", "อาการร่วม")]),
        ("เส้นทางที่เสนอให้พิจารณา", "<span class=\"display\" style=\"font-size: 18px;\">ประเมินฉุกเฉิน</span> <span class=\"meta\">· ข้อเสนอเพื่อให้แพทย์ตรวจ ไม่ใช่คำสั่ง</span>", []),
        ("ข้อมูลที่ควรได้เพิ่ม", "ความดัน ชีพจร อัตราการหายใจ SpO₂ · ประวัติโรคประจำตัว · ยาที่ใช้", [ev("REQ", "รายการข้อมูลจำเป็น ED first contact")]),
    ]
    secs = "".join(f'<div class="col line-t" style="padding: 16px 0; gap: 8px;"><span class="eyebrow">{a}</span><p style="margin: 0; font-size: 16px; line-height: 27px;">{b}</p><div class="row" style="gap: 6px; flex-wrap: wrap;">{"".join(c)}</div></div>' for a, b, c in sections)
    options = [("check", "ยืนยัน", "ใช้ร่างนี้ตามที่เป็น", False, "#146c40"), ("edit", "แก้ไขแล้วยืนยัน", "บันทึกเป็นฉบับใหม่ ฉบับเดิมยังอยู่", False, "#155e75"),
               ("bell", "ส่งต่อด่วน · ESCALATE", "ต้องให้แพทย์ประเมินทันที", True, "#b42318"), ("stop", "ปฏิเสธ", "ร่างนี้ใช้ไม่ได้", False, "#5b6670")]
    opts = "".join(
        f'<button type="button" aria-pressed="{"true" if on else "false"}" class="row" style="gap: 12px; text-align: left; font: inherit; color: #111c26; padding: 12px 14px; border-radius: 10px; cursor: pointer; {"border: 2px solid #b42318; background: #fff5f4;" if on else "border: 1px solid #e4e1d8; background: #fff;"}"><span class="row" style="width: 34px; height: 34px; border-radius: 9px; justify-content: center; background: {c}1a;">{ic(i, 18, c, "2")}</span><span class="col grow"><span class="strong">{a}</span><span class="meta">{b}</span></span><span style="width: 18px; height: 18px; box-sizing: border-box; border-radius: 999px; {"border: 5px solid #b42318;" if on else "border: 2px solid #c9c4b8;"}"></span></button>'
        for i, a, b, on, c in options)
    main = f"""{case_header("ร่างและตัดสินใจ")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<div class="col grow" style="padding: 24px 36px; gap: 22px; overflow: hidden;">
<section class="card" style="border-color: #f1b5ae; overflow: hidden;" aria-label="ผลคัดกรองก่อนใช้โมเดล">
<div class="row" style="background: #b42318; color: #fff; padding: 10px 16px; gap: 10px;">{ic("alert", 18, "#fff", "2.2")}<span class="strong">ผลคัดกรองก่อนใช้โมเดล</span><span class="grow"></span><span class="mono" style="color: #ffd9d4;">URGENT_REVIEW · rule-based</span></div>
<div class="row" style="padding: 14px 16px; gap: 28px; align-items: flex-start;"><div class="col grow" style="gap: 4px;"><span class="strong" style="color: #b42318; font-size: 16px;">ข้อมูลที่จำเป็นยังไม่ครบ — เข้าเงื่อนไข</span><span>ขาด: สัญญาณชีพ</span></div>
<div class="col" style="max-width: 360px; gap: 2px;"><span class="eyebrow">ข้อจำกัด</span><span class="meta" style="color: #3b4751;">ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ ผลนี้ไม่แทนการประเมินของแพทย์</span></div></div></section>
<section class="col"><div class="row" style="gap: 12px; padding-bottom: 6px;"><h2 class="display" style="margin: 0; font-size: 22px;">ร่างส่งต่อ ฉบับที่ 1</h2><span class="pill p-info">รอตรวจ</span><span class="grow"></span><span class="mono" style="color: #5b6670;">09:20 · mock-v2 · design fixed</span></div>{secs}</section>
</div>
<aside class="col" style="width: 400px; flex-shrink: 0; border-left: 1px solid #e4e1d8; background: #faf9f6; padding: 24px; gap: 14px;">
<div class="col" style="gap: 4px;"><h2 class="display" style="margin: 0; font-size: 20px;">การตัดสินใจของแพทย์</h2><span class="row meta" style="gap: 6px;">{ic("lock", 14, "#5b6670")}ยังไม่มีผลต่อการดูแลจนกว่าคุณจะบันทึก</span></div>
<div class="col" role="group" aria-label="การตัดสินใจ" style="gap: 8px;">{opts}</div>
<label class="eyebrow" for="reason" style="padding-top: 4px;">เหตุผล · จำเป็น</label>
<div class="col" style="background: #fff; border: 1px solid #d5d1c6; border-radius: 10px; padding: 10px 12px; gap: 2px;"><select id="reason" style="border: none; font: 500 15px/24px 'Noto Sans Thai',sans-serif; color: #111c26; background: none; padding: 0;"><option>ข้อมูลที่ขาดทำให้ต้องประเมินทันที</option></select><span class="mono" style="color: #9aa3ab;">MISSING_INFORMATION</span></div>
<span class="grow"></span>
<button class="btn btn-lg" type="button" style="background: #b42318; color: #fff;">บันทึก ESCALATE{ic("arrow", 18, "#fff", "2")}</button><span class="meta" style="text-align: center;">บันทึกพร้อมชื่อผู้ตรวจ dr.somchai · แก้ย้อนไม่ได้</span>
</aside></div>"""
    return platform_shell("คิวเคส", main)


ACTORS = {"physician": ("#0b1f2e", "SC"), "nurse": ("#0f766e", "NA"), "system": ("#9aa3ab", "SYS")}
EVENTS = [
    ("09:24:10", "physician", "dr.somchai", "บันทึกการตัดสินใจ · ESCALATE", "HUMAN_REVIEW_RECORDED", "MISSING_INFORMATION · ร่างฉบับที่ 1"),
    ("09:20:02", "system", "ระบบ", "สร้างร่างส่งต่อ ฉบับที่ 1", "DRAFT_CREATED", "ข้อมูลรุ่น 6 · mock-v2 · design fixed"),
    ("09:20:01", "system", "ระบบ", "คัดกรองก่อนใช้โมเดล → URGENT_REVIEW", "SAFETY_SCREEN_APPLIED", "SCR-001 REQUIRED_INFORMATION_INCOMPLETE · ขาด VITAL"),
    ("09:16:40", "nurse", "nurse.a", "ยืนยันข้อเสนอ 2 รายการ", "PROPOSALS_ACCEPTED", "run 7f3c · ข้อมูลรุ่น 4 → 6"),
    ("09:14:05", "system", "ระบบ", "ผู้ช่วยตอบเสร็จ", "AGENT_RUN_COMPLETED", "run 7f3c · 3 calls · 2 proposals"),
    ("09:12:30", "nurse", "nurse.a", "บันทึกอาการสำคัญ", "FACT_RECORDED", "CHIEF_COMPLAINT · STAFF_CONFIRMED"),
    ("09:11:58", "nurse", "nurse.a", "เปิดเคส demo-014", "ENCOUNTER_CREATED", "workspace pilot"),
]


def dag():
    nodes = [("SNAPSHOT", "อ่านข้อมูลรุ่น 4", "ณ 09:14:02", "#155e75"), ("MODEL_CALL", "mock-v2", "412 ms", "#0b1f2e"), ("SCHEMA_CHECK", "ตรวจรูปแบบ", "ผ่าน", "#146c40"), ("PROPOSE", "ข้อเสนอ 2", "รอบุคลากร", "#a15c07"), ("HUMAN_ACCEPT", "nurse.a ยืนยัน", "09:16:40", "#0f766e")]
    w, h, gap, x0 = 300, 58, 26, 18
    parts = []
    for i, (typ, a, b, c) in enumerate(nodes):
        y = 10 + i * (h + gap)
        parts.append(f'<rect x="{x0}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fff" stroke="#e4e1d8"/><rect x="{x0}" y="{y}" width="6" height="{h}" rx="3" fill="{c}"/>')
        parts.append(f'<text x="{x0 + 20}" y="{y + 22}" font-family="Roboto Mono, monospace" font-size="11" fill="{c}" font-weight="500">{typ}</text>')
        parts.append(f'<text x="{x0 + 20}" y="{y + 43}" font-family="Noto Sans Thai, sans-serif" font-size="15" font-weight="600" fill="#111c26">{a}</text>')
        parts.append(f'<text x="{x0 + w - 14}" y="{y + 43}" text-anchor="end" font-family="Roboto Mono, monospace" font-size="12" fill="#5b6670">{b}</text>')
        if i < len(nodes) - 1:
            yy = y + h
            parts.append(f'<path d="M{x0 + 40} {yy + 2} V{yy + gap - 4}" stroke="#9aa3ab" stroke-width="1.6"/><path d="M{x0 + 35} {yy + gap - 9} L{x0 + 40} {yy + gap - 3} L{x0 + 45} {yy + gap - 9}" fill="none" stroke="#9aa3ab" stroke-width="1.6"/>')
    total = 10 + len(nodes) * (h + gap)
    return f'<svg width="336" height="{total}" viewBox="0 0 336 {total}" role="img" aria-label="กราฟขั้นตอนที่ระบบรันจริงของ run 7f3c">{"".join(parts)}</svg>'


def audit():
    items = []
    for i, (t, kind, who, title, code, refs) in enumerate(EVENTS):
        color, init = ACTORS[kind]
        last = i == len(EVENTS) - 1
        items.append(f"""<div class="row" style="align-items: stretch; gap: 16px;"><span class="mono" style="width: 70px; flex-shrink: 0; padding-top: 6px; color: #5b6670; text-align: right;">{t}</span>
<span class="col" style="align-items: center; width: 34px; flex-shrink: 0;"><span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: {color}; color: #fff; justify-content: center; font-size: 11px; flex-shrink: 0;">{init}</span>{'' if last else '<span style="width: 2px; flex-grow: 1; background: #e4e1d8;"></span>'}</span>
<div class="col grow" style="padding: 4px 0 18px; gap: 2px;"><span class="row" style="gap: 10px;"><span class="strong" style="font-size: 16px;">{title}</span><span class="meta">{who}</span></span><span class="row" style="gap: 8px;"><span class="mono" style="color: #0f766e;">{code}</span><span class="meta">{refs}</span></span></div></div>""")
    legend = "".join(f'<span class="row meta" style="gap: 6px;"><span style="width: 10px; height: 10px; border-radius: 999px; background: {c};"></span>{l}</span>' for c, l in [("#0b1f2e", "แพทย์"), ("#0f766e", "พยาบาล"), ("#9aa3ab", "ระบบ")])
    main = f"""{case_header("Audit และ trace")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<section class="col grow" style="padding: 24px 36px; gap: 18px; overflow: hidden;"><div class="row" style="gap: 14px;"><h2 class="display" style="margin: 0; font-size: 22px;">Audit</h2><span class="meta">เพิ่มต่อท้ายเท่านั้น · เก็บการอ้างอิง ไม่เก็บข้อความทางคลินิก</span><span class="grow"></span>{legend}</div>
<div class="col">{''.join(items)}</div></section>
<aside class="col" style="width: 400px; flex-shrink: 0; border-left: 1px solid #e4e1d8; background: #faf9f6; padding: 24px 28px; gap: 12px;">
<div class="col" style="gap: 2px;"><span class="eyebrow">Executed DAG</span><h2 class="display" style="margin: 0; font-size: 20px;">run 7f3c · design single</h2><span class="meta">ขั้นตอนที่ระบบรันจริง ส่งออกและ replay ได้ ไม่ใช่ความคิดของโมเดล</span></div>
{dag()}
<div class="row" style="gap: 8px; flex-wrap: wrap;"><span class="chip"><span class="mono">contract</span>synthetic_intake_v1</span><span class="chip"><span class="mono">provider</span>mock-v2 offline</span><span class="chip"><span class="mono">calls</span>3 / 8</span></div>
</aside></div>"""
    return platform_shell("คิวเคส", main)


def before():
    fig = lambda src, cap: f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 10px; width: 660px;"><img src="{src}" alt="{cap}" style="width: 660px; border: 1px solid #e4e1d8; border-radius: 12px;"><figcaption class="meta">{cap}</figcaption></figure>'
    return f"""<div class="col" style="padding: 36px 40px; gap: 16px;">
<span class="eyebrow">19 ก.ย. 2569 · ก่อน redesign</span><h1 class="display" style="margin: 0; font-size: 30px;">หน้าจอเดิม</h1>
<p class="meta" style="margin: 0; font-size: 15px;">ทุกส่วนเป็นการ์ดแบบเดียวกัน · orb เป็นจุดเด่นของหน้าพยาบาล · ความเร่งด่วนไม่เด่นกว่าส่วนอื่น</p>
<div class="row" style="gap: 40px; align-items: flex-start;">{fig("/_blob/7b0431ce443da6ff23a8176a984323eb", "Nurse Intake เดิม")}{fig("/_blob/d85e847031b0ce010471e0da75d2b023", "Central Platform เดิม")}</div></div>"""


boards = {
    "Before.dc.html": ("ก่อน redesign", 1440, 720, before(), "", 0, 0, False),
    "Main.dc.html": ("Nurse Intake · Desktop", 1440, 900, nurse(), "", 0, 1143, True),
    "Nurse-Tablet.dc.html": ("Nurse Intake · Tablet", 768, 1024, nurse(stacked=True), "", 1520, 1143, True),
    "Nurse-Mobile.dc.html": ("Nurse Intake · Mobile", 390, 844, fix_holes(mobile()), MOBILE_LOGIC, 2368, 1143, True),
    "Nurse-Handoff.dc.html": ("Nurse Intake · ส่งต่อแล้ว", 1440, 900, nurse(sent=True), "", 2838, 1143, True),
    "Platform-Queue.dc.html": ("Platform · คิวเคส", 1440, 900, queue(), "", 0, 2590, True),
    "Platform-Review.dc.html": ("Platform · ตรวจเคส", 1440, 900, review(), "", 1520, 2590, True),
    "Platform-Audit.dc.html": ("Platform · Audit และ trace", 1440, 900, audit(), "", 3040, 2590, True),
}

if __name__ == "__main__":
    existing = json.loads((ROOT / "canvas.json").read_text()) if (ROOT / "canvas.json").exists() else {}
    index = {"v": 3, "createdOnFiles": existing.get("createdOnFiles", {"v": 1, "at": "2026-09-19T12:30:00Z"}), "title": "Front Door Redesign",
             "launch": {"view": "canvas"}, "pages": [], "boards": {}, "order": [], "designSystems": [],
             "notes": {
                 "before": {"x": 0, "y": -300, "text": "ก่อน redesign", "kind": "title1", "maxW": 1440},
                 "nurse": {"x": 0, "y": 843, "text": "Nurse Intake — /nurse", "kind": "title1", "maxW": 4278},
                 "platform": {"x": 0, "y": 2290, "text": "Central Platform — /platform", "kind": "title1", "maxW": 4480},
             }}
    for name, (title, w, h, body, logic, x, y, interactive) in boards.items():
        (ROOT / name).write_text(page(title, w, h, body, logic))
        entry = {"x": x, "y": y, "w": w, "h": h, "title": title}
        if interactive:
            entry["is_interactive"] = True
        index["boards"][name] = entry
        index["order"].append(name)
    (ROOT / "canvas.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print("built", len(boards))
