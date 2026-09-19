"""Builds the Front Door redesign canvas: one .dc.html per screen plus canvas.json."""
import json
from pathlib import Path

ROOT = Path(__file__).parent / "project"
ROOT.mkdir(parents=True, exist_ok=True)

CSS = """
body{margin:0;font-family:'Prompt',sans-serif;color:#17212b;background:#f4f3ef}
a{color:#0f766e}a:hover{color:#094f4a}
.screen{box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;background:#f4f3ef;font-size:15px;line-height:24px}
.row{display:flex;align-items:center}
.col{display:flex;flex-direction:column}
.grow{flex-grow:1;min-width:0}
.bar{min-height:56px;background:#fff;border-bottom:1px solid #dde2e1;gap:16px;padding:0 24px;flex-shrink:0}
.flag{background:#fceceb;border-bottom:1px solid #dd9995;padding:12px 24px;gap:16px;color:#9f2d2d;font-weight:500;flex-shrink:0}
.meta{font-size:13px;line-height:20px;color:#52606d}
.strong{font-weight:500}
.label{font-size:13px;line-height:20px;color:#52606d;font-weight:500}
.h-section{font-size:17px;line-height:26px;font-weight:600;margin:0}
.h-page{font-size:20px;line-height:28px;font-weight:600;margin:0}
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:6px;font-size:13px;line-height:20px;font-weight:500;white-space:nowrap}
.b-neutral{background:#eef0ee;color:#334155}.b-info{background:#eaf3f8;color:#164e63}.b-success{background:#e9f5ef;color:#176b4d}
.b-warning{background:#fff6df;color:#7c4a03}.b-danger{background:#fceceb;color:#9f2d2d}
.btn{box-sizing:border-box;height:40px;padding:0 16px;border-radius:6px;font:500 15px/24px 'Prompt',sans-serif;display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid transparent;background:none;color:#17212b;cursor:pointer;white-space:nowrap;text-decoration:none}
.btn-primary{background:#0f766e;color:#fff}.btn-primary:hover{background:#0c625c;color:#fff}
.btn-secondary{background:#fff;border-color:#c9d0d3}
.btn-text{color:#0f766e;padding:0 4px}
.btn-lg{height:44px}
.rule-b{border-bottom:1px solid #dde2e1}
.rule-t{border-top:1px solid #dde2e1}
.panel{background:#fff}
.input{box-sizing:border-box;border:1px solid #c9d0d3;border-radius:6px;background:#fff;padding:12px;color:#52606d}
.tr{display:grid;align-items:center;padding:14px 16px;border-bottom:1px solid #dde2e1;gap:12px}
.th{background:#f7f7f4;padding:10px 16px}
.sel{background:#e7f3f0}
"""

MIC = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>'


def page(title, w, h, body, script="", interactive_state=None):
    logic = script or "class Component extends DCLogic {\n  renderVals() { return {}; }\n}"
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>{CSS}</style>
</helmet>
<div class="screen" style="width: {w}px; height: {h}px;">
{body}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{props}'>
{logic}
</script>
</body>
</html>
"""


PROTO = '<span class="badge b-warning">ต้นแบบวิจัย · ข้อมูลสังเคราะห์ · ต้องมีบุคลากรตรวจ</span>'
FLAG = """<div class="flag row"><span class="badge b-danger" style="background: #fff; border: 1px solid #dd9995;">ต้องให้แพทย์ดูโดยเร็ว</span>
<span>ข้อมูลที่จำเป็นยังไม่ครบ: ขาดสัญญาณชีพ — เข้าเงื่อนไข · ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ แพทย์ต้องประเมินเอง</span></div>"""

TRANSCRIPT = [
    ("พยาบาล", "09:12", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกตั้งแต่เช้า ร้าวไปแขนซ้าย", False),
    ("ผู้ช่วย", "09:12", "บันทึกอาการสำคัญเป็นข้อเสนอแล้ว รอคุณยืนยัน · ควรถามต่อ: เริ่มเจ็บกี่โมง มีเหงื่อแตกหรือหายใจลำบากหรือไม่", True),
    ("พยาบาล", "09:14", "เริ่มประมาณ 7 โมงเช้า มีเหงื่อออก ไม่มีหายใจลำบาก", False),
    ("ผู้ช่วย", "09:14", "เสนอข้อมูล 2 รายการ: เวลาเริ่มอาการ และอาการร่วม · ยังไม่มีสัญญาณชีพ", True),
]


def transcript_rows(meta_w=96):
    out = []
    for who, t, text, bot in TRANSCRIPT:
        color = "#0f766e" if bot else "#17212b"
        tcolor = "#334155" if bot else "#17212b"
        out.append(f"""<div class="row rule-b" style="align-items: flex-start; gap: 24px; padding: 16px 0;">
<div class="col" style="width: {meta_w}px; flex-shrink: 0;"><span class="label" style="color: {color};">{who}</span><span class="meta">{t}</span></div>
<p style="margin: 0; color: {tcolor};" class="grow">{text}</p></div>""")
    return "\n".join(out)


def composer(compact=False):
    hint = "" if compact else '<span class="meta">ถอดเสียงแล้วแก้ข้อความได้ก่อนส่ง</span>'
    return f"""<div class="col input" style="gap: 12px; color: #17212b;">
<label class="meta" for="msg">ข้อความถึงผู้ช่วย</label>
<textarea id="msg" rows="2" placeholder="พิมพ์หรืออัดเสียงสิ่งที่ผู้ป่วยเล่า…" style="border: none; resize: none; font: 15px/24px 'Prompt',sans-serif; color: #17212b; outline: none; padding: 0;"></textarea>
<div class="row" style="gap: 8px;"><button class="btn btn-secondary btn-lg" type="button">{MIC}อัดเสียง</button>{hint}<span class="grow"></span><button class="btn btn-primary btn-lg" type="button">ส่งให้ผู้ช่วย</button></div></div>"""


def fact(label, value, meta=None, actions=False):
    acts = '<div class="row" style="gap: 8px; padding-top: 8px;"><button class="btn btn-secondary" type="button">ยืนยัน</button><button class="btn btn-text" type="button">แก้ไข</button></div>' if actions else ""
    m = f'<span class="meta">{meta}</span>' if meta else ""
    return f'<div class="col rule-t" style="padding: 12px 0; gap: 2px;"><span class="meta">{label}</span><span class="strong">{value}</span>{m}{acts}</div>'


def rail_section(title, count, items):
    return f'<section class="col"><div class="row" style="gap: 8px; padding-bottom: 8px; align-items: baseline;"><h2 class="h-section">{title}</h2><span class="meta">{count}</span></div>{"".join(items)}</section>'


PENDING = [fact("เวลาเริ่มอาการ", "07:00 น. วันนี้", "จากข้อความ 09:14", True), fact("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "จากข้อความ 09:14", True)]
CONFIRMED = [fact("อาการสำคัญ", "เจ็บแน่นหน้าอก ร้าวไปแขนซ้าย", "พยาบาลยืนยัน 09:12"), fact("อายุ · เพศ", "58 ปี · ชาย", "ข้อมูลเคส")]
MISSING = [fact("สัญญาณชีพ", "ความดัน ชีพจร อัตราการหายใจ SpO₂")]


def case_bar(compact=False):
    extra = "" if compact else f'<span class="meta">ชาย 58 ปี · ข้อมูลรุ่น 6</span>{PROTO}'
    return f"""<header class="bar row"><span class="strong">Nurse Intake</span><span class="meta">/</span><span class="strong">demo-014</span>{extra}
<span class="grow"></span><button class="btn btn-secondary" type="button">เปลี่ยนเคส</button><a class="btn btn-text" href="Platform-Queue.dc.html">เปิด Central Platform</a></header>"""


def handoff_bar(sent=False):
    if sent:
        return """<footer class="bar row rule-t" style="min-height: 72px; border-bottom: none;"><span class="badge b-info">รอแพทย์ตรวจ</span>
<div class="col"><span class="strong">ส่งให้แพทย์แล้ว 09:20 · ร่างฉบับที่ 1 รอแพทย์ตรวจ</span><span class="meta">ถ้าได้ข้อมูลเพิ่ม บันทึกต่อได้ ร่างจะถูกทำเครื่องหมายว่าต้องสร้างใหม่</span></div>
<span class="grow"></span><a class="btn btn-text" href="Platform-Review.dc.html">ดูสถานะในแพลตฟอร์ม</a><button class="btn btn-secondary" type="button">รับเคสถัดไป</button></footer>"""
    return """<footer class="bar row rule-t" style="min-height: 72px; border-bottom: none;"><div class="col"><span class="strong">ร่างส่งต่อจะใช้ข้อมูลที่ยืนยันแล้ว 3 รายการ</span><span class="meta" style="color: #7c4a03;">ยังขาดสัญญาณชีพ — แพทย์จะเห็นว่าข้อมูลนี้ขาด</span></div>
<span class="grow"></span><button class="btn btn-text" type="button">บันทึกไว้ก่อน</button><a class="btn btn-primary" href="Nurse-Handoff.dc.html">ส่งให้แพทย์ตรวจ</a></footer>"""


def nurse(w, h, stacked=False, sent=False):
    rail_items = [] if sent else [rail_section("รอคุณยืนยัน", "2 รายการจากผู้ช่วย", PENDING)]
    confirmed = CONFIRMED + ([fact("เวลาเริ่มอาการ", "07:00 น. วันนี้", "พยาบาลยืนยัน 09:16"), fact("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "พยาบาลยืนยัน 09:16")] if sent else [])
    rail_items += [rail_section("ยืนยันแล้ว", f"{5 if sent else 3} รายการ", confirmed), rail_section("ยังขาด", "ต้องมีก่อนส่งต่อ", MISSING)]
    rail_style = "border-top: 1px solid #dde2e1;" if stacked else "width: 400px; flex-shrink: 0; border-left: 1px solid #dde2e1;"
    body_dir = "column" if stacked else "row"
    return f"""{case_bar(compact=stacked)}
{FLAG}
<div class="grow" style="display: flex; flex-direction: {body_dir}; min-height: 0; overflow: hidden;">
<main class="col grow" style="padding: 24px {24 if stacked else 32}px; gap: 16px; min-height: 0;">
<div class="row" style="align-items: baseline;"><h1 class="h-section">บทสนทนา</h1><span class="grow"></span><span class="meta">ตรวจ transcript ก่อนส่งทุกครั้ง</span></div>
<div class="col {'' if stacked else 'grow'}">{transcript_rows()}</div>
{composer(compact=stacked)}
</main>
<aside class="col panel" style="{rail_style} padding: 24px; gap: 32px; overflow: hidden;">{''.join(rail_items)}</aside>
</div>
{handoff_bar(sent)}"""


MOBILE_LOGIC = """class Component extends DCLogic {
  constructor(props) { super(props); this.state = { tab: 'chat' }; }
  renderVals() {
    const tab = this.state.tab;
    return {
      chat: tab === 'chat', facts: tab === 'facts',
      showChat: () => this.setState({ tab: 'chat' }), showFacts: () => this.setState({ tab: 'facts' }),
      chatTab: tab === 'chat' ? 'border-bottom: 2px solid #0f766e; color: #17212b;' : 'border-bottom: 2px solid transparent; color: #52606d;',
      factsTab: tab === 'facts' ? 'border-bottom: 2px solid #0f766e; color: #17212b;' : 'border-bottom: 2px solid transparent; color: #52606d;',
    };
  }
}"""


def mobile():
    tab_btn = "flex-grow: 1; height: 48px; background: none; border: none; font: 500 15px/24px 'Prompt',sans-serif; cursor: pointer;"
    return f"""<header class="bar row" style="padding: 0 16px; gap: 8px;"><span class="strong">demo-014</span><span class="meta">ชาย 58</span><span class="grow"></span><button class="btn btn-secondary btn-lg" type="button">เปลี่ยนเคส</button></header>
<div class="flag col" style="padding: 10px 16px; gap: 4px;"><span class="badge b-danger" style="align-self: flex-start; background: #fff; border: 1px solid #dd9995;">ต้องให้แพทย์ดูโดยเร็ว</span><span style="font-size: 14px; line-height: 22px;">ข้อมูลที่จำเป็นยังไม่ครบ: ขาดสัญญาณชีพ</span></div>
<div class="row panel rule-b" role="tablist" aria-label="มุมมองเคส"><button type="button" role="tab" style="{tab_btn} {{{{chatTab}}}}" onClick="{{{{showChat}}}}">บทสนทนา</button><button type="button" role="tab" style="{tab_btn} {{{{factsTab}}}}" onClick="{{{{showFacts}}}}">ข้อมูล · 2 รอยืนยัน</button></div>
<sc-if value="{{{{chat}}}}" hint-placeholder-val="{{{{true}}}}">
<div class="col grow" style="padding: 0 16px; overflow: hidden;">{transcript_rows(meta_w=56)}</div>
<div class="col panel rule-t" style="padding: 12px 16px; gap: 8px;"><label class="meta" for="m-msg">ข้อความถึงผู้ช่วย</label><textarea id="m-msg" rows="2" placeholder="พิมพ์หรืออัดเสียง…" style="border: 1px solid #c9d0d3; border-radius: 6px; padding: 10px; resize: none; font: 15px/24px 'Prompt',sans-serif;"></textarea>
<div class="row" style="gap: 8px;"><button class="btn btn-secondary btn-lg grow" type="button">{MIC}อัดเสียง</button><button class="btn btn-primary btn-lg grow" type="button">ส่งให้ผู้ช่วย</button></div></div>
</sc-if>
<sc-if value="{{{{facts}}}}" hint-placeholder-val="{{{{false}}}}">
<div class="col grow panel" style="padding: 16px; gap: 24px; overflow: hidden;">{rail_section("รอคุณยืนยัน", "2 รายการ", PENDING)}{rail_section("ยังขาด", "ต้องมีก่อนส่งต่อ", MISSING)}</div>
<div class="col panel rule-t" style="padding: 12px 16px; gap: 4px;"><span class="meta">ยืนยันข้อมูลที่รออยู่ก่อน จึงจะส่งให้แพทย์ได้</span><button class="btn btn-primary btn-lg" type="button" disabled="disabled" style="opacity: 0.5;">ส่งให้แพทย์ตรวจ</button></div>
</sc-if>"""


def platform_shell(active, main):
    items = [("คิวเคส", "Platform-Queue.dc.html"), ("การทดลอง Agent", None), ("สถานะระบบ", None)]
    nav = "".join(
        f'<a href="{href or "#"}" style="display: block; padding: 8px; border-radius: 6px; text-decoration: none; color: #17212b; {"background: #e7f3f0; font-weight: 500;" if label == active else "color: #334155;"}">{label}</a>'
        for label, href in items)
    return f"""<div class="row grow" style="align-items: stretch; min-height: 0;">
<nav class="col panel" aria-label="เมนูหลัก" style="width: 220px; flex-shrink: 0; padding: 20px 16px; gap: 4px; border-right: 1px solid #dde2e1;">
<div class="col" style="padding: 0 8px 20px;"><span class="strong">Clinical Front Door</span><span class="meta">Central Platform</span></div>
{nav}<span class="grow"></span>
<div class="col" style="padding: 0 8px;"><span class="strong">dr.somchai</span><span class="meta">แพทย์ผู้ตรวจ</span><a class="btn btn-text" style="align-self: flex-start;" href="Main.dc.html">เปิด Nurse Intake</a></div>
</nav>
<div class="col grow" style="min-height: 0;">{main}</div></div>"""


QUEUE_ROWS = [
    ("demo-014", "ชาย 58", ("b-danger", "ต้องให้แพทย์ดูโดยเร็ว"), ("ข้อมูลที่จำเป็นยังไม่ครบ", "ขาดสัญญาณชีพ", "#9f2d2d"), ("5 ยืนยัน", "รอยืนยัน 0"), ("b-info", "รอตรวจ", ""), ("09:20", "nurse.a")),
    ("demo-013", "หญิง 34", ("b-neutral", "ให้แพทย์ดูตามคิวปกติ"), ("ไม่พบเงื่อนไข", "", "#17212b"), ("7 ยืนยัน", ""), ("b-success", "ยืนยันแล้ว", ""), ("08:55", "dr.somchai")),
    ("demo-012", "ชาย 71", ("b-danger", "ต้องให้แพทย์ดูโดยเร็ว"), ("ข้อมูลที่จำเป็นยังไม่ครบ", "ขาดประวัติยา", "#9f2d2d"), ("4 ยืนยัน", "รอยืนยัน 2"), ("b-warning", "ต้องตรวจใหม่", "ข้อมูลเปลี่ยนหลังสร้างร่าง"), ("08:41", "nurse.b")),
    ("demo-011", "หญิง 45", ("b-warning", "ข้อมูลยังไม่พอสรุป"), ("เคสอยู่นอกขอบเขตที่ประเมินไว้", "", "#7c4a03"), ("2 ยืนยัน", ""), ("b-neutral", "ยังไม่มีร่าง", ""), ("08:30", "nurse.a")),
    ("demo-010", "ชาย 29", ("b-neutral", "ให้แพทย์ดูตามคิวปกติ"), ("ไม่พบเงื่อนไข", "", "#17212b"), ("6 ยืนยัน", ""), ("b-danger", "ถูกปฏิเสธ", "เหตุผล: ข้อมูลไม่สอดคล้อง"), ("08:12", "dr.somchai")),
]
COLS = "grid-template-columns: 110px 90px 200px minmax(0, 1fr) 110px 190px 100px;"


def queue():
    head = "".join(f'<span class="label">{h}</span>' for h in ["เคส", "ผู้ป่วยสมมติ", "ความเร่งด่วนขั้นต่ำ", "ผลคัดกรองก่อนใช้โมเดล", "ข้อมูล", "ร่างส่งต่อ", "อัปเดต"])
    rows = []
    for i, (cid, pt, (ucls, ulab), (flag, fmeta, fcol), (facts, fsub), (dcls, dlab, dsub), (upd, who)) in enumerate(QUEUE_ROWS):
        link = f'<a href="Platform-Review.dc.html" class="strong" style="color: #17212b;">{cid}</a>' if i == 0 else f'<span class="strong">{cid}</span>'
        sub = lambda s: f'<span class="meta">{s}</span>' if s else ""
        rows.append(f"""<div class="tr {'sel' if i == 0 else ''}" style="{COLS}">{link}<span>{pt}</span><span><span class="badge {ucls}">{ulab}</span></span>
<span class="col"><span style="color: {fcol};">{flag}</span>{sub(fmeta)}</span><span class="col"><span>{facts}</span>{sub(fsub)}</span>
<span class="col" style="align-items: flex-start;"><span class="badge {dcls}">{dlab}</span>{sub(dsub)}</span><span class="col"><span>{upd}</span>{sub(who)}</span></div>""")
    chips = "".join(f'<button class="btn {"btn-secondary" if i == 0 else "btn-text"}" type="button">{c}</button>' for i, c in enumerate(["ทั้งหมด 12", "รอตรวจ 4", "ต้องตรวจใหม่ 1", "ยืนยันแล้ว 6"]))
    main = f"""<div class="col" style="padding: 24px 32px; gap: 16px;">
<div class="row" style="gap: 12px;"><h1 class="h-page">คิวเคส</h1>{PROTO}<span class="badge b-neutral">Offline · mock provider</span><span class="grow"></span><button class="btn btn-primary" type="button">เริ่มเคสจำลอง</button></div>
<div class="row" style="gap: 8px;"><label class="input" style="width: 320px; padding: 8px 12px;">ค้นหารหัสเคส</label>{chips}</div>
<div class="col panel" style="border: 1px solid #dde2e1; border-radius: 8px; overflow: hidden;"><div class="tr th" style="{COLS}">{head}</div>{''.join(rows)}</div>
</div>"""
    return platform_shell("คิวเคส", main)


def case_header(active):
    tabs = [("ร่างและตัดสินใจ", "Platform-Review.dc.html"), ("Audit และ trace", "Platform-Audit.dc.html")]
    t = "".join(f'<a class="btn {"btn-secondary" if l == active else "btn-text"}" href="{h}">{l}</a>' for l, h in tabs)
    return f"""<header class="row panel rule-b" style="padding: 16px 32px; gap: 12px;"><a class="btn btn-text" href="Platform-Queue.dc.html">← คิวเคส</a><h1 class="h-page">demo-014</h1>
<span class="meta">ชาย 58 ปี · ข้อมูลรุ่น 6 · ร่างฉบับที่ 1</span><span class="badge b-warning">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span><span class="grow"></span>{t}</header>"""


def review():
    sections = [
        ("สรุป", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกร้าวไปแขนซ้ายตั้งแต่ 07:00 น. มีเหงื่อออก ไม่มีหายใจลำบาก ยังไม่มีสัญญาณชีพ", "อ้างอิง: อาการสำคัญ 09:12 · เวลาเริ่มอาการ 09:16 · อาการร่วม 09:16"),
        ("เส้นทางที่เสนอให้พิจารณา", "ประเมินฉุกเฉิน", "ข้อเสนอเพื่อให้แพทย์ตรวจ ไม่ใช่คำสั่ง"),
        ("ข้อมูลที่ควรได้เพิ่ม", "ความดัน ชีพจร อัตราการหายใจ SpO₂ · ประวัติโรคประจำตัว · ยาที่ใช้", "จากรายการข้อมูลจำเป็นของ ED first contact"),
    ]
    secs = "".join(f'<div class="col rule-t" style="padding: 14px 0; gap: 4px;"><span class="label">{a}</span><p style="margin: 0;">{b}</p><span class="meta" style="color: #0f766e;">{c}</span></div>' for a, b, c in sections)
    options = [("ยืนยัน", "ใช้ร่างนี้ตามที่เป็น", False), ("แก้ไขแล้วยืนยัน", "บันทึกเป็นฉบับใหม่ ฉบับเดิมยังอยู่", False), ("ส่งต่อด่วน (ESCALATE)", "ต้องให้แพทย์ประเมินทันที", True), ("ปฏิเสธ", "ร่างนี้ใช้ไม่ได้", False)]
    opts = "".join(
        f'<button type="button" aria-pressed="{"true" if on else "false"}" class="col" style="align-items: flex-start; text-align: left; font: inherit; color: #17212b; padding: 10px 12px; border-radius: 6px; cursor: pointer; {"border: 2px solid #0f766e; background: #e7f3f0;" if on else "border: 1px solid #c9d0d3; background: #fff;"}"><span class="strong">{a}</span><span class="meta">{b}</span></button>'
        for a, b, on in options)
    main = f"""{case_header("ร่างและตัดสินใจ")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<div class="col grow" style="padding: 24px 32px; gap: 24px;">
<section class="col" style="background: #fceceb; border: 1px solid #dd9995; border-radius: 6px; padding: 12px 16px; gap: 6px;" aria-label="ผลคัดกรองก่อนใช้โมเดล">
<div class="row" style="gap: 12px;"><h2 class="strong" style="margin: 0; font-size: 15px; color: #9f2d2d;">ผลคัดกรองก่อนใช้โมเดล</h2><span class="badge b-danger" style="background: #fff; border: 1px solid #dd9995;">ต้องให้แพทย์ดูโดยเร็ว · URGENT_REVIEW</span></div>
<span style="color: #9f2d2d;">ข้อมูลที่จำเป็นยังไม่ครบ — เข้าเงื่อนไข · ขาด: สัญญาณชีพ</span>
<span class="meta" style="color: #334155;">ข้อจำกัด: ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ ผลนี้ไม่แทนการประเมินของแพทย์</span></section>
<section class="col"><div class="row" style="gap: 12px; padding-bottom: 12px;"><h2 class="h-section">ร่างส่งต่อฉบับที่ 1</h2><span class="badge b-info">รอตรวจ</span><span class="grow"></span><span class="meta">สร้าง 09:20 · mock-v2 · design fixed</span></div>{secs}</section>
</div>
<aside class="col panel" style="width: 380px; flex-shrink: 0; border-left: 1px solid #dde2e1; padding: 24px; gap: 16px;">
<h2 class="h-section">การตัดสินใจของแพทย์</h2><p class="meta" style="margin: 0;">ร่างนี้ยังไม่มีผลต่อการดูแลผู้ป่วยจนกว่าคุณจะยืนยัน ทุกการตัดสินใจถูกบันทึกพร้อมชื่อผู้ตรวจ</p>
<div class="col" role="group" aria-label="การตัดสินใจ" style="gap: 8px;">{opts}</div>
<label class="label" for="reason" style="color: #334155;">เหตุผล (จำเป็น)</label>
<div class="col input" style="gap: 2px;"><select id="reason" style="border: none; font: 15px/24px 'Prompt',sans-serif; color: #17212b; background: none; padding: 0;"><option>ข้อมูลที่ขาดทำให้ต้องประเมินทันที</option></select><span class="meta">รหัสเหตุผล: MISSING_INFORMATION</span></div>
<button class="btn btn-primary" type="button">บันทึกการตัดสินใจ</button>
</aside></div>"""
    return platform_shell("คิวเคส", main)


EVENTS = [
    ("09:24:10", "dr.somchai · แพทย์ผู้ตรวจ", "HUMAN_REVIEW_RECORDED", "บันทึกการตัดสินใจของแพทย์", "ESCALATE · MISSING_INFORMATION · ร่างฉบับที่ 1", "b-info"),
    ("09:20:02", "ระบบ", "DRAFT_CREATED", "สร้างร่างส่งต่อ", "ร่างฉบับที่ 1 · ข้อมูลรุ่น 6 · mock-v2 · design fixed", "b-neutral"),
    ("09:20:01", "ระบบ", "SAFETY_SCREEN_APPLIED", "คัดกรองก่อนใช้โมเดล", "SCR-001 REQUIRED_INFORMATION_INCOMPLETE TRIGGERED · ขาด VITAL → URGENT_REVIEW", "b-danger"),
    ("09:16:40", "nurse.a · ผู้รับข้อมูล", "PROPOSALS_ACCEPTED", "ยืนยันข้อเสนอจากผู้ช่วย", "2 รายการ · run 7f3c · ข้อมูลรุ่น 4 → 6", "b-neutral"),
    ("09:14:05", "ระบบ", "AGENT_RUN_COMPLETED", "ผู้ช่วยตอบเสร็จ", "run 7f3c · design single · 3 calls · 2 proposals", "b-neutral"),
    ("09:12:30", "nurse.a · ผู้รับข้อมูล", "FACT_RECORDED", "บันทึกข้อมูลเคส", "CHIEF_COMPLAINT · STAFF_CONFIRMED · ข้อมูลรุ่น 1", "b-neutral"),
    ("09:11:58", "nurse.a · ผู้รับข้อมูล", "ENCOUNTER_CREATED", "เปิดเคส", "demo-014 · workspace pilot", "b-neutral"),
]
TRACE = [
    ("1", "อ่าน snapshot ข้อมูลรุ่น 4", "ข้อมูลที่ใช้ได้ ณ 09:14:02 เท่านั้น"),
    ("2", "เรียกโมเดล · mock-v2", "412 ms · สถานะ ok"),
    ("3", "ตรวจรูปแบบคำตอบ", "ผ่าน schema · 2 proposals"),
    ("4", "ส่งข้อเสนอให้บุคลากร", "ยังไม่เป็นข้อมูลเคสจนกว่าจะยืนยัน"),
]


def audit():
    rows = "".join(f"""<div class="row rule-t" style="align-items: flex-start; gap: 24px; padding: 12px 0;"><span class="meta" style="width: 72px; flex-shrink: 0;">{t}</span>
<span class="label" style="width: 200px; flex-shrink: 0; color: #334155;">{who}</span>
<div class="col grow" style="gap: 2px;"><div class="row" style="gap: 8px;"><span class="strong">{th}</span><span class="badge {cls}">{ev}</span></div><span class="meta" style="color: #334155;">{refs}</span></div></div>""" for t, who, ev, th, refs, cls in EVENTS)
    steps = "".join(f'<li class="row rule-t" style="align-items: flex-start; gap: 12px; padding: 12px 0;"><span class="badge b-neutral">{n}</span><span class="col"><span class="strong">{a}</span><span class="meta">{b}</span></span></li>' for n, a, b in TRACE)
    main = f"""{case_header("Audit และ trace")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<section class="col grow" style="padding: 24px 32px;"><div class="row" style="gap: 12px; padding-bottom: 12px; align-items: baseline;"><h2 class="h-section">Audit</h2><span class="meta">บันทึกแบบเพิ่มต่อท้ายเท่านั้น · เก็บการอ้างอิง ไม่เก็บข้อความทางคลินิก</span></div>{rows}</section>
<aside class="col panel" style="width: 380px; flex-shrink: 0; border-left: 1px solid #dde2e1; padding: 24px; gap: 8px;">
<h2 class="h-section">Agent trace · run 7f3c</h2><p class="meta" style="margin: 0;">ขั้นตอนที่ระบบทำจริง ไม่ใช่ความคิดของโมเดล</p>
<ol style="list-style: none; margin: 0; padding: 0;">{steps}</ol>
<div class="col rule-t" style="padding-top: 12px; gap: 2px;"><span class="meta">รุ่นสัญญา API · synthetic_intake_v1</span><span class="meta">provider · mock-v2 (offline)</span></div>
</aside></div>"""
    return platform_shell("คิวเคส", main)


def before():
    fig = lambda src, cap: f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px; width: 660px;"><img src="{src}" alt="{cap}" style="width: 660px; border: 1px solid #dde2e1; border-radius: 8px;"><figcaption class="meta">{cap}</figcaption></figure>'
    return f"""<div class="col" style="padding: 32px 40px; gap: 16px;">
<h1 class="h-page">ก่อน redesign · 19 ก.ย. 2569</h1>
<p class="meta" style="margin: 0;">ทุกส่วนเป็นการ์ดแบบเดียวกัน · orb เป็นจุดเด่นของหน้าพยาบาล · persona, อีโมจิ และ sparkle เป็นการตกแต่ง</p>
<div class="row" style="gap: 40px; align-items: flex-start;">{fig("/_blob/7b0431ce443da6ff23a8176a984323eb", "Nurse Intake เดิม (1440 × 900)")}{fig("/_blob/d85e847031b0ce010471e0da75d2b023", "Central Platform เดิม (1440 × 1084)")}</div></div>"""


boards = {
    "Before.dc.html": ("ก่อน redesign", 1440, 700, before(), "", 0, 0, False),
    "Main.dc.html": ("Nurse Intake · Desktop", 1440, 900, nurse(1440, 900), "", 0, 1123, True),
    "Nurse-Tablet.dc.html": ("Nurse Intake · Tablet", 768, 1024, nurse(768, 1024, stacked=True), "", 1520, 1123, True),
    "Nurse-Mobile.dc.html": ("Nurse Intake · Mobile", 390, 844, mobile(), MOBILE_LOGIC, 2368, 1123, True),
    "Nurse-Handoff.dc.html": ("Nurse Intake · ส่งต่อแล้ว", 1440, 900, nurse(1440, 900, sent=True), "", 2838, 1123, True),
    "Platform-Queue.dc.html": ("Platform · คิวเคส", 1440, 900, queue(), "", 0, 2570, True),
    "Platform-Review.dc.html": ("Platform · ตรวจเคส", 1440, 900, review(), "", 1520, 2570, True),
    "Platform-Audit.dc.html": ("Platform · Audit และ trace", 1440, 900, audit(), "", 3040, 2570, True),
}
index = {"v": 3, "createdOnFiles": {"v": 1, "at": "2026-09-19T12:30:00Z"}, "title": "Front Door Redesign",
         "launch": {"view": "canvas"}, "pages": [], "boards": {}, "order": [], "designSystems": [],
         "notes": {
             "before": {"x": 0, "y": -300, "text": "ก่อน redesign", "kind": "title1", "maxW": 1440},
             "nurse": {"x": 0, "y": 823, "text": "Nurse Intake — /nurse", "kind": "title1", "maxW": 4278},
             "platform": {"x": 0, "y": 2270, "text": "Central Platform — /platform", "kind": "title1", "maxW": 4480},
         }}
for name, (title, w, h, body, logic, x, y, interactive) in boards.items():
    (ROOT / name).write_text(page(title, w, h, body, logic))
    entry = {"x": x, "y": y, "w": w, "h": h, "title": title}
    if interactive:
        entry["is_interactive"] = True
    index["boards"][name] = entry
    index["order"].append(name)
(ROOT / "canvas.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
print("\n".join(sorted(p.name for p in ROOT.iterdir())))
