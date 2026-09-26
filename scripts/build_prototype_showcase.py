"""Builds the standalone interactive prototype showcase in prototype/index.html."""
import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_HTML = ROOT / "prototype" / "index.html"

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
    }
    return f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths.get(name, "")}</svg>'

def wave(bars=38, h=28, color="#0b57d0", animated=True):
    rects = []
    for i in range(bars):
        v = 0.25 + 0.75 * abs(math.sin(i * 0.55) * math.cos(i * 0.17))
        bh = max(3, round(h * v))
        delay = (i % 7) * 0.15
        anim_style = f'animation: wavePulse 1.2s ease-in-out {delay:.2f}s infinite alternate;' if animated else ''
        rects.append(f'<rect class="wave-bar" x="{i * 5}" y="{(h - bh) / 2}" width="3" height="{bh}" rx="1.5" fill="{color}" style="{anim_style}"/>')
    return f'<svg class="wave-svg" width="{bars * 5}" height="{h}" viewBox="0 0 {bars * 5} {h}" aria-hidden="true">{"".join(rects)}</svg>'

def nurse_topbar(compact=False):
    case = '<span class="mono" style="color: #1f1f1f; font-size: 14px;">demo-014</span>'
    info = "" if compact else '<span class="meta">ชาย 58 ปี</span><span class="meta">·</span><span class="row meta" style="gap: 4px;">' + ic("clock", 15, "#444746") + 'มาถึง 09:10 · รอ 12 นาที</span>'
    proto = "" if compact else '<span class="pill p-proto">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span>'
    return f"""<header class="chrome row" style="height: 60px; padding: 0 24px; gap: 16px; flex-shrink: 0;"><span class="row" style="gap: 10px;"><span class="row" style="width: 30px; height: 30px; border-radius: 9999px; background: #0b57d0; justify-content: center;">{ic("door", 18, "#fff", "2")}</span><span class="col" style="gap: 0;"><span class="display" style="font-size: 17px; line-height: 20px; color: #1f1f1f;">Pratu</span><span style="font-size: 11px; line-height: 14px; color: #444746;">Clinical Front Door</span></span></span><span style="width: 1px; height: 24px; background: #dcdada;"></span>
<span class="meta" style="color: #444746;">Pratu Intake</span><span class="row" style="gap: 10px; padding: 6px 12px; border-radius: 9999px; background: #ffffff;">{case}{info}</span>
<span class="grow"></span>{proto}<button class="btn btn-ghost-light" type="button" onclick="navigateTo('platform-queue')">Pratu Console</button>
<span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: #d3e3fd; color: #0842a0; justify-content: center; font-size: 14px;">NA</span></header>"""

def urgency_band(compact=False):
    more = "" if compact else '<span style="opacity: 0.9;">· ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ แพทย์ต้องประเมินเอง</span>'
    btn = "" if compact else f'<button class="btn btn-white" type="button" onclick="triggerUrgentAlert()">{ic("bell", 17, "#b3261e")}แจ้งแพทย์เวร</button>'
    return f"""<div class="row" style="background: #b3261e; color: #fff; padding: {10 if compact else 12}px {16 if compact else 24}px; gap: 14px; flex-shrink: 0;">{ic("alert", 22, "#fff", "2")}
<div class="{'col' if compact else 'row'} grow" style="gap: {2 if compact else 10}px; {'' if compact else 'flex-wrap: wrap;'}"><span class="display" style="font-size: {16 if compact else 18}px; font-weight: 600;">ต้องให้แพทย์ดูโดยเร็ว</span><span style="{'font-size: 14px; line-height: 20px;' if compact else ''}">ข้อมูลที่จำเป็นยังไม่ครบ: ขาดสัญญาณชีพ</span>{more}</div>{btn}</div>"""

def msg_nurse(t, text):
    return f"""<div class="row" style="align-items: flex-start; gap: 14px;"><span class="row display" style="width: 32px; height: 32px; border-radius: 999px; background: #1f1f1f; color: #fff; justify-content: center; font-size: 12px; flex-shrink: 0;">NA</span>
<div class="col grow" style="gap: 2px;"><span class="row" style="gap: 8px;"><span class="strong" style="font-size: 14px;">พยาบาล</span><span class="mono" style="color: #444746;">{t}</span></span><p style="margin: 0; font-size: 16px; line-height: 26px;">{text}</p></div></div>"""

def msg_assistant(t, text, chips):
    c = "".join(f'<a class="chip" href="#pending" style="background: #fff; border-color: #a8c7fa; color: #0842a0;">{ic("list", 14, "#0b57d0")}{x}</a>' for x in chips)
    return f"""<div class="row" style="align-items: flex-start; gap: 14px;"><span class="row" style="width: 32px; height: 32px; border-radius: 999px; background: #d3e3fd; justify-content: center; flex-shrink: 0;">{ic("list", 16, "#0b57d0")}</span>
<div class="col grow" style="gap: 8px; background: #d3e3fd; border-radius: 4px 12px 12px 12px; padding: 12px 14px;"><span class="row" style="gap: 8px;"><span class="strong" style="font-size: 14px; color: #0842a0;">ผู้ช่วย · ข้อเสนอรอตรวจ</span><span class="mono" style="color: #444746;">{t}</span></span>
<p style="margin: 0; color: #041e49;">{text}</p><div class="row" style="gap: 6px; flex-wrap: wrap;">{c}</div></div></div>"""

CONVO = [
    msg_nurse("09:12", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกตั้งแต่เช้า ร้าวไปแขนซ้าย"),
    msg_assistant("09:12", "บันทึกอาการสำคัญเป็นข้อเสนอแล้ว · ควรถามต่อ: เริ่มเจ็บกี่โมง มีเหงื่อแตกหรือหายใจลำบากหรือไม่", ["อาการสำคัญ"]),
    msg_nurse("09:14", "เริ่มประมาณ 7 โมงเช้า มีเหงื่อออก ไม่มีหายใจลำบาก"),
    msg_assistant("09:14", "เสนอข้อมูล 2 รายการ · ยังไม่มีสัญญาณชีพ ควรวัดก่อนส่งต่อ", ["เวลาเริ่มอาการ 07:00", "อาการร่วม: เหงื่อออก"]),
]

def recorder(compact=False):
    return f"""<div class="col" style="background: #fff; border: 1px solid #e3e3e3; border-radius: 28px; box-shadow: 0 8px 24px rgba(0,0,0,0.04); padding: {12 if compact else 16}px; gap: 12px;">
<div class="row" style="gap: 12px;"><span id="recording-indicator" class="row" style="gap: 8px; color: #b3261e; font-weight: 600;"><span class="record-dot" style="width: 9px; height: 9px; border-radius: 999px; background: #b3261e;"></span><span id="recording-label">กำลังฟัง</span></span><span id="recording-time" class="mono" style="color: #444746;">00:14</span>
<span class="grow" style="overflow: hidden;">{wave(24 if compact else 60)}</span></div>
<p style="margin: 0; color: #444746; font-style: italic;">“…วัดความดันแล้วได้ 150 ต่อ 90 ชีพจร…”</p>
<div class="row" style="gap: 10px;"><button id="toggle-record-btn" class="btn btn-ink btn-lg" type="button" onclick="toggleRecording()" aria-label="หยุดบันทึก">{ic("stop", 18, "#fff", "2")}<span id="toggle-record-text">{'' if compact else 'หยุดบันทึก'}</span></button>
<span class="meta grow">{'' if compact else 'ถอดเสียงแล้วแก้ข้อความได้ก่อนส่ง · ไม่บันทึกข้อมูลระบุตัวผู้ป่วยจริง'}</span><button class="btn btn-primary btn-lg" type="button" onclick="sendToAssistant()">{ic("send", 18, "#fff", "2")}ส่งให้ผู้ช่วย</button></div></div>"""

def progress(filled=3, pending=2, total=6):
    seg = []
    for i in range(total):
        color = "#0b57d0" if i < filled else "#e8b04b" if i < filled + pending else "#e3e3e3"
        seg.append(f'<span id="prog-seg-{i}" style="flex-grow: 1; height: 8px; border-radius: 4px; background: {color}; transition: all 0.3s ease;"></span>')
    return f"""<div class="col" style="gap: 10px;"><div class="row" style="align-items: baseline; gap: 8px;"><span class="display" style="font-size: 32px; line-height: 36px;"><span id="progress-filled">{filled}</span><span style="color: #747775; font-size: 20px;">/{total}</span></span><span class="meta">ข้อมูลจำเป็นยืนยันแล้ว</span></div>
<div class="row" style="gap: 4px;">{''.join(seg)}</div><div class="row meta" style="gap: 14px;"><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #0b57d0;"></span>ยืนยัน <span id="count-filled">{filled}</span></span><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #e8b04b;"></span>รอยืนยัน <span id="count-pending">{pending}</span></span><span class="row" style="gap: 6px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: #e3e3e3;"></span>ยังขาด <span id="count-missing">{total - filled - pending}</span></span></div></div>"""

def pending_card(label, value, src, card_id):
    return f"""<div id="{card_id}" class="col pending-card" style="border: 1px solid #f3dca8; background: #fffbf3; border-radius: 20px; padding: 12px 14px; gap: 8px; transition: all 0.3s ease;"><div class="col" style="gap: 0;"><span class="meta">{label} · {src}</span><span class="strong" style="font-size: 16px;">{value}</span></div>
<div class="row" style="gap: 8px;"><button class="btn btn-primary" type="button" style="height: 36px;" onclick="confirmFact('{card_id}', '{label}', '{value}', '{src}')">{ic("check", 16, "#fff", "2.2")}ยืนยัน</button><button class="btn btn-text" type="button" style="height: 36px;" onclick="editFactPrompt('{label}', '{value}')">{ic("edit", 15, "#0b57d0")}แก้ไข</button></div></div>"""

def done_row(label, value, who):
    return f'<div class="row line-t" style="gap: 12px; padding: 10px 0; align-items: flex-start;"><span class="row" style="width: 22px; height: 22px; border-radius: 999px; background: #e6f4ea; justify-content: center; margin-top: 2px;">{ic("check", 14, "#146c2e", "2.4")}</span><div class="col grow"><span class="meta">{label}</span><span class="strong">{value}</span></div><span class="mono" style="color: #747775;">{who}</span></div>'

def missing_row(label, value):
    return f'<div class="row line-t" style="gap: 12px; padding: 10px 0; align-items: flex-start;"><span class="row" style="width: 22px; height: 22px; border-radius: 999px; background: #f9dedc; justify-content: center; margin-top: 2px;">{ic("alert", 13, "#b3261e", "2.2")}</span><div class="col grow"><span class="meta">{label}</span><span class="strong">{value}</span></div><button class="btn btn-text" type="button" style="height: 32px;" onclick="promptVitalSign()">ถามต่อ</button></div>'

def rail(sent=False, pad=24):
    pending = "" if sent else f"""<section id="pending-section" class="col" style="gap: 10px;"><div class="row"><span class="eyebrow" id="pending-header">รอคุณยืนยัน · 2</span></div>
{pending_card("เวลาเริ่มอาการ", "07:00 น. วันนี้", "จากข้อความ 09:14", "card-time")}
{pending_card("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "จากข้อความ 09:14", "card-associated")}
</section>"""
    confirmed = [done_row("อาการสำคัญ", "เจ็บแน่นหน้าอก ร้าวไปแขนซ้าย", "09:12"), done_row("อายุ · เพศ", "58 ปี · ชาย", "เคส")]
    if sent:
        confirmed += [done_row("เวลาเริ่มอาการ", "07:00 น. วันนี้", "09:16"), done_row("อาการร่วม", "เหงื่อออก · ไม่มีหายใจลำบาก", "09:16")]
    return f"""<aside class="col" style="padding: {pad}px; gap: 24px; overflow-y: auto; background: #fff;">
<section class="col" style="gap: 6px;"><span class="eyebrow">ความครบของข้อมูล</span>{progress(5 if sent else 3, 0 if sent else 2)}</section>
{pending}
<section class="col"><span class="eyebrow" style="padding-bottom: 6px;">ยืนยันแล้ว · <span id="confirmed-count-badge">{'4' if sent else '2'}</span></span><div id="confirmed-list" class="col">{''.join(confirmed)}</div></section>
<section class="col"><span class="eyebrow" style="padding-bottom: 6px;">ยังขาด · 1</span>{missing_row("สัญญาณชีพ", "ความดัน ชีพจร อัตราการหายใจ SpO₂")}</section></aside>"""

def handoff(sent=False):
    if sent:
        steps = [("ส่งให้แพทย์", "09:20", "done"), ("แพทย์เปิดดู", "09:22", "done"), ("แพทย์ตัดสินใจ", "รอ", "now")]
        s = []
        for i, (a, b, st) in enumerate(steps):
            dot = {"done": f'<span class="row" style="width: 24px; height: 24px; border-radius: 999px; background: #0b57d0; justify-content: center;">{ic("check", 14, "#fff", "2.6")}</span>',
                   "now": '<span style="width: 24px; height: 24px; box-sizing: border-box; border-radius: 999px; border: 3px solid #e8b04b; background: #fff;"></span>'}[st]
            s.append(f'<span class="row" style="gap: 10px;">{dot}<span class="col"><span class="strong" style="color: #1f1f1f;">{a}</span><span class="mono" style="color: #444746;">{b}</span></span></span>')
            if i < len(steps) - 1:
                s.append('<span style="width: 48px; height: 2px; background: #dcdada;"></span>')
        return f"""<footer class="chrome row" style="height: 80px; padding: 0 24px; gap: 18px; flex-shrink: 0; border-top: 1px solid #e3e3e3;">{''.join(s)}<span class="grow"></span>
<span class="meta" style="max-width: 300px;">ได้ข้อมูลเพิ่มบันทึกต่อได้ ร่างจะถูกทำเครื่องหมายให้สร้างใหม่</span><button class="btn btn-ghost-light" type="button" onclick="navigateTo('platform-review')">ดูในแพลตฟอร์ม</button><button class="btn btn-primary" type="button" onclick="resetNextCase()">รับเคสถัดไป{ic("arrow", 17, "#fff", "2")}</button></footer>"""
    return f"""<footer class="row" style="height: 80px; padding: 0 24px; gap: 16px; flex-shrink: 0; background: #fff; border-top: 1px solid #e3e3e3; box-shadow: 0 -8px 24px rgba(0,0,0,0.04);">
<div class="col"><span id="footer-ready-title" class="strong" style="font-size: 16px;">พร้อมส่งให้แพทย์ด้วยข้อมูลที่ยืนยันแล้ว 3 รายการ</span><span id="footer-ready-desc" class="row meta" style="gap: 6px; color: #7a4f00;">{ic("alert", 14, "#8c5a00", "2")}ยังขาดสัญญาณชีพ แพทย์จะเห็นว่าข้อมูลนี้ขาด · รอยืนยันอีก 2 รายการ</span></div>
<span class="grow"></span><button class="btn btn-text" type="button" onclick="saveDraftToast()">บันทึกไว้ก่อน</button><button id="btn-submit-nurse" class="btn btn-primary btn-lg" type="button" onclick="navigateTo('nurse-handoff')">ส่งให้แพทย์ตรวจ{ic("arrow", 18, "#fff", "2")}</button></footer>"""

def nurse(stacked=False, sent=False):
    convo_head = f"""<div class="row" style="gap: 12px;"><h1 class="display" style="margin: 0; font-size: 22px;">ซักประวัติ</h1><span class="grow"></span>
<div class="row" role="group" aria-label="โหมดรับข้อมูล" style="background: #f2f0f0; border-radius: 9999px; padding: 3px;"><button type="button" class="btn" aria-pressed="true" style="height: 32px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08);">{ic("mic", 15)}เสียง</button><button type="button" class="btn" aria-pressed="false" style="height: 32px; color: #444746;">ข้อความ</button></div></div>"""
    main = f"""<main class="col grow" style="padding: 24px {24 if stacked else 40}px; gap: 20px; min-height: 0;">{convo_head}
<div class="col {'' if stacked else 'grow'}" style="gap: 18px; overflow-y: auto;">{''.join(CONVO)}</div>{recorder(compact=stacked)}</main>"""
    side = rail(sent, pad=18 if stacked else 24)
    if stacked:
        body = f'<div class="col grow" style="min-height: 0; overflow-y: auto;">{main}<div style="border-top: 1px solid #e3e3e3;">{side}</div></div>'
    else:
        body = f'<div class="row grow" style="align-items: stretch; min-height: 0;">{main}<div style="width: 420px; flex-shrink: 0; border-left: 1px solid #e3e3e3; display: flex; flex-direction: column;">{side}</div></div>'
    return nurse_topbar(stacked) + urgency_band(stacked) + body + handoff(sent)

def mobile():
    tb = "flex-grow: 1; height: 40px; border: none; border-radius: 20px; font: 600 15px/24px 'Noto Sans Thai',sans-serif; cursor: pointer; transition: all 0.2s ease;"
    chat = "".join(CONVO[2:])
    body = f"""<header class="chrome row" style="height: 56px; padding: 0 16px; gap: 10px; flex-shrink: 0;"><span class="row" style="width: 28px; height: 28px; border-radius: 9999px; background: #0b57d0; justify-content: center;">{ic("door", 16, "#fff", "2")}</span>
<span class="col"><span class="mono" style="color: #1f1f1f; font-weight: 600;">demo-014</span><span class="meta" style="font-size: 12px; line-height: 16px;">ชาย 58 · รอ 12 นาที</span></span><span class="grow"></span><button class="btn btn-ghost-light" type="button" style="height: 36px;" onclick="showCaseInfoModal()">ข้อมูลเคส</button></header>
{urgency_band(compact=True)}
<div class="row" role="tablist" aria-label="มุมมองเคส" style="margin: 12px 16px 0; background: #f2f0f0; border-radius: 20px; padding: 4px; gap: 4px;">
<button id="mob-tab-chat" type="button" role="tab" style="{tb} background: #fff; color: #1f1f1f; box-shadow: 0 1px 2px rgba(0,0,0,0.08);" onclick="switchMobileTab('chat')">บทสนทนา</button>
<button id="mob-tab-facts" type="button" role="tab" style="{tb} background: transparent; color: #444746;" onclick="switchMobileTab('facts')">ข้อมูล · <span style="color: #8c5a00;">2 รอ</span></button>
</div>
<div id="mob-view-chat" class="col grow" style="min-height: 0;">
<div class="col grow" style="padding: 16px; gap: 16px; overflow-y: auto;">{chat}</div>
<div class="col" style="background: #fff; border-top: 1px solid #e3e3e3; padding: 12px 16px 20px; gap: 10px;">
<div class="row" style="gap: 8px;"><span style="width: 8px; height: 8px; border-radius: 999px; background: #b3261e;"></span><span class="strong" style="color: #b3261e; font-size: 14px;">กำลังฟัง</span><span class="mono" style="color: #444746;">00:14</span><span class="grow" style="overflow: hidden;">{wave(26, 22)}</span></div>
<div class="row" style="gap: 12px; justify-content: center;"><button class="btn btn-secondary" type="button" style="height: 48px;">ข้อความ</button><button type="button" aria-label="หยุดบันทึก" class="row" style="width: 64px; height: 64px; border-radius: 999px; background: #1f1f1f; border: 4px solid #d3e3fd; justify-content: center; cursor: pointer;" onclick="toggleRecording()">{ic("stop", 22, "#fff", "2.2")}</button><button class="btn btn-primary" type="button" style="height: 48px;" onclick="sendToAssistant()">ส่ง</button></div></div>
</div>
<div id="mob-view-facts" class="col grow" style="display: none; min-height: 0;">
<div class="col grow" style="padding: 16px; gap: 18px; overflow-y: auto;">{progress()}<section class="col" style="gap: 10px;"><span class="eyebrow">รอคุณยืนยัน · 2</span>{pending_card("เวลาเริ่มอาการ", "07:00 น. วันนี้", "09:14", "mob-card-time")}{pending_card("อาการร่วม", "เหงื่อออก", "09:14", "mob-card-sym")}</section></div>
<div class="col" style="background: #fff; border-top: 1px solid #e3e3e3; padding: 12px 16px 20px; gap: 6px;"><span class="meta" style="text-align: center;">ยืนยันข้อมูลที่รออยู่ก่อน จึงจะส่งให้แพทย์ได้</span><button id="mob-submit-btn" class="btn btn-primary btn-lg" type="button" onclick="navigateTo('nurse-handoff')">ส่งให้แพทย์ตรวจ</button></div>
</div>"""
    return body

def platform_shell(active, main):
    items = [("คิวเคส", "list", "platform-queue", "4"), ("การทดลอง Agent", "flask", "#", None), ("สถานะระบบ", "gauge", "#", None)]
    nav = []
    for label, icon, target, count in items:
        on = label == active
        badge = f'<span class="pill" style="background: #0b57d0; color: #fff; padding: 0 8px;">{count}</span>' if count else ""
        href = f"javascript:navigateTo('{target}')" if target != "#" else "javascript:showFeatureNotice('ส่วนนี้เปิดใช้งานใน Phase 2')"
        nav.append(f'<a href="{href}" class="row" style="gap: 12px; padding: 10px 12px; border-radius: 9999px; text-decoration: none; {"background: #d3e3fd; color: #041e49;" if on else "color: #444746;"}">{ic(icon, 18, "#041e49" if on else "#444746")}<span class="grow" style="font-weight: 600;">{label}</span>{badge}</a>')
    return f"""<div class="row grow" style="align-items: stretch; min-height: 0;">
<nav class="chrome col" aria-label="เมนูหลัก" style="width: 240px; flex-shrink: 0; padding: 20px 14px; gap: 4px; border-right: 1px solid #e3e3e3;">
<div style="padding: 0 8px 24px;"><span class="row" style="gap: 10px;"><span class="row" style="width: 30px; height: 30px; border-radius: 9999px; background: #0b57d0; justify-content: center;">{ic("door", 18, "#fff", "2")}</span><span class="col" style="gap: 0;"><span class="display" style="font-size: 17px; line-height: 20px; color: #1f1f1f;">Pratu</span><span style="font-size: 11px; line-height: 14px; color: #444746;">Clinical Front Door</span></span></span><div class="meta" style="padding-top: 6px; padding-left: 40px;">Pratu Console</div></div>
{''.join(nav)}<span class="grow"></span>
<div class="col" style="margin: 0 4px; padding: 12px; border-radius: 20px; background: #ffffff; gap: 10px; border: 1px solid #e3e3e3;"><div class="row" style="gap: 10px;"><span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: #d3e3fd; color: #0842a0; justify-content: center; font-size: 13px;">SC</span><span class="col"><span class="strong" style="color: #1f1f1f; font-size: 14px;">dr.somchai</span><span class="meta" style="font-size: 12px;">แพทย์ผู้ตรวจ · เวรเช้า</span></span></div>
<button class="btn btn-ghost-light" type="button" onclick="navigateTo('nurse-desktop')" style="height: 36px;">{ic("mic", 16, "#0b57d0")}Pratu Intake</button></div>
</nav><div class="col grow" style="min-height: 0; overflow-y: auto;">{main}</div></div>"""

def kpi(value, unit, label, color="#1f1f1f", note=""):
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
    for cid, pt, lvl, ulab, flag, fsub, wait, nurse_init, (dcls, dlab), sel in QROWS:
        u = {"urgent": f'<span class="pill p-urgent">{ic("alert", 13, "#fff", "2.4")}{ulab}</span>', "warn": f'<span class="pill p-warn">{ulab}</span>', "neutral": f'<span class="pill p-neutral">{ulab}</span>'}[lvl]
        fcol = "#b3261e" if lvl == "urgent" else "#7a4f00" if lvl == "warn" else "#444746"
        barw = min(100, wait * 3)
        barc = "#b3261e" if wait >= 20 else "#e8b04b" if wait >= 10 else "#0b57d0"
        sub = f'<span class="meta">{fsub}</span>' if fsub else ""
        cid_el = f'<a href="javascript:navigateTo(\'platform-review\')" class="mono strong" style="color: #0b57d0; font-size: 14px; text-decoration: underline;">{cid}</a>' if sel else f'<span class="mono" style="font-size: 14px;">{cid}</span>'
        click_action = "onclick=\"navigateTo('platform-review')\" style=\"cursor: pointer;\"" if sel else ""
        rows.append(f"""<div class="tr queue-row" data-lvl="{lvl}" {click_action} style="{QCOLS} {'background: #eef3fd; box-shadow: inset 3px 0 0 #0b57d0;' if sel else ''}">{cid_el}<span>{pt}</span><span>{u}</span>
<span class="col"><span style="color: {fcol}; font-weight: 500;">{flag}</span>{sub}</span>
<span class="col" style="gap: 4px;"><span class="mono">{wait} นาที</span><span style="height: 4px; border-radius: 2px; background: #efefef;"><span style="display: block; width: {barw}%; height: 4px; border-radius: 2px; background: {barc};"></span></span></span>
<span class="row display" style="width: 30px; height: 30px; border-radius: 999px; background: #f2f0f0; color: #444746; justify-content: center; font-size: 12px;">{nurse_init}</span><span><span class="pill {dcls}">{dlab}</span></span>{ic("chev", 18, "#747775")}</div>""")
    
    filters = "".join(f'<button type="button" class="btn queue-filter-btn" onclick="filterQueue(\'{k}\')" style="height: 34px; border-radius: 9999px; {"background: #1f1f1f; color: #fff;" if i == 0 else "background: #fff; border: 1px solid #e3e3e3; color: #444746;"}">{label}</button>' for i, (k, label) in enumerate([("all", "ทั้งหมด 12"), ("urgent", "ด่วน 2"), ("waiting", "รอตรวจ 4"), ("recheck", "ต้องตรวจใหม่ 1"), ("confirmed", "ยืนยันแล้ว 6")]))
    main = f"""<div class="col grow" style="padding: 28px 36px; gap: 22px; min-height: 0;">
<div class="row" style="gap: 14px;"><div class="col"><span class="meta">วันเสาร์ 19 ก.ย. 2569 · ED first contact</span><h1 class="display" style="margin: 0; font-size: 30px; line-height: 38px;">คิวเคสวันนี้</h1></div><span class="grow"></span><span class="pill p-proto-light">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span><span class="pill p-neutral">Offline · mock provider</span><button class="btn btn-primary" type="button" onclick="showNewSyntheticModal()">เริ่มเคสจำลองใหม่</button></div>
<div class="row" style="gap: 16px; align-items: stretch;">{kpi("4", "เคส", "รอแพทย์ตรวจ", note="เก่าสุดรอ 23 นาที")}{kpi("2", "เคส", "ต้องดูโดยเร็ว", "#b3261e", "ทั้งคู่ขาดข้อมูลจำเป็น")}{kpi("14", "นาที", "เวลารอเฉลี่ย", note="ตั้งแต่ส่งถึงแพทย์เปิดดู")}{kpi("6", "เคส", "ยืนยันแล้ววันนี้", "#146c2e", "ถูกปฏิเสธ 1 · แก้ไข 2")}</div>
<div class="row" style="gap: 8px;"><div class="row" style="width: 300px; height: 40px; box-sizing: border-box; border: 1px solid #c4c7c5; border-radius: 9999px; background: #fff; padding: 0 12px; gap: 8px; color: #747775;"><svg class="icon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#747775" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/></svg><input type="text" placeholder="ค้นหารหัสเคส (เช่น demo-014)" style="border: none; outline: none; background: transparent; font: inherit; width: 100%;" oninput="searchQueue(this.value)"></div>{filters}</div>
<div class="card col" style="overflow: hidden;"><div class="tr" style="{QCOLS} background: #f2f0f0; padding-top: 10px; padding-bottom: 10px;">{head}</div>{''.join(rows)}</div>
</div>"""
    return platform_shell("คิวเคส", main)

def case_header(active):
    tabs = [("ข้อมูลเคส", "javascript:showCaseInfoModal()"), ("ร่างและตัดสินใจ", "javascript:navigateTo('platform-review')"), ("Audit และ trace", "javascript:navigateTo('platform-audit')")]
    t = "".join(f'<a href="{h}" style="padding: 14px 2px; text-decoration: none; font-weight: 600; {"color: #1f1f1f; box-shadow: inset 0 -3px 0 #0b57d0;" if l == active else "color: #444746;"}">{l}</a>' for l, h in tabs)
    facts = "".join(f'<span class="col"><span class="eyebrow">{a}</span><span class="strong">{b}</span></span>' for a, b in [("ผู้ป่วย", "ชาย 58 ปี"), ("มาถึง", "09:10"), ("รอแล้ว", "12 นาที"), ("ข้อมูลรุ่น", "6"), ("พยาบาล", "nurse.a")])
    return f"""<header class="col" style="background: #fff; border-bottom: 1px solid #e3e3e3; padding: 20px 36px 0; gap: 14px; flex-shrink: 0;">
<div class="row" style="gap: 14px;"><button class="btn btn-text" type="button" onclick="navigateTo('platform-queue')" style="padding: 0;">{ic("arrow", 16, "#0b57d0", "2")}<span style="margin-left: 6px;">กลับคิวเคส</span></button></div>
<div class="row" style="gap: 16px;"><h1 class="mono" style="margin: 0; font-size: 26px; line-height: 32px; font-weight: 500;">demo-014</h1><span class="pill p-urgent">{ic("alert", 13, "#fff", "2.4")}ต้องให้แพทย์ดูโดยเร็ว</span><span class="pill p-proto-light">ต้นแบบวิจัย · ข้อมูลสังเคราะห์</span><span class="grow"></span><div class="row" style="gap: 28px;">{facts}</div></div>
<nav class="row" style="gap: 28px;">{t}</nav></header>"""

def review():
    ev = lambda code, label: f'<a class="chip" href="javascript:void(0)" onclick="inspectEvidence(\'{code}\', \'{label}\')"><span class="mono" style="color: #0b57d0; font-weight: 600;">{code}</span>{label}</a>'
    sections = [
        ("สรุป", "ผู้ป่วยชาย 58 ปี เจ็บแน่นหน้าอกร้าวไปแขนซ้ายตั้งแต่ 07:00 น. มีเหงื่อออก ไม่มีหายใจลำบาก <mark style=\"background: #f9dedc; color: #b3261e; padding: 0 4px; border-radius: 4px; font-weight: 600;\">ยังไม่มีสัญญาณชีพ</mark>", [ev("E-0912", "อาการสำคัญ"), ev("E-0916a", "เวลาเริ่มอาการ"), ev("E-0916b", "อาการร่วม")]),
        ("เส้นทางที่เสนอให้พิจารณา", "<span class=\"display\" style=\"font-size: 18px;\">ประเมินฉุกเฉิน</span> <span class=\"meta\">· ข้อเสนอเพื่อให้แพทย์ตรวจ ไม่ใช่คำสั่ง</span>", []),
        ("ข้อมูลที่ควรได้เพิ่ม", "ความดัน ชีพจร อัตราการหายใจ SpO₂ · ประวัติโรคประจำตัว · ยาที่ใช้", [ev("REQ", "รายการข้อมูลจำเป็น ED first contact")]),
    ]
    secs = "".join(f'<div class="col line-t" style="padding: 16px 0; gap: 8px;"><span class="eyebrow">{a}</span><p style="margin: 0; font-size: 16px; line-height: 27px;">{b}</p><div class="row" style="gap: 6px; flex-wrap: wrap;">{"".join(c)}</div></div>' for a, b, c in sections)
    options = [("check", "ยืนยัน", "ใช้ร่างนี้ตามที่เป็น", "CONFIRM", False, "#146c2e"), 
               ("edit", "แก้ไขแล้วยืนยัน", "บันทึกเป็นฉบับใหม่ ฉบับเดิมยังอยู่", "MODIFY", False, "#0842a0"),
               ("bell", "ส่งต่อด่วน · ESCALATE", "ต้องให้แพทย์ประเมินทันที", "ESCALATE", True, "#b3261e"), 
               ("stop", "ปฏิเสธ", "ร่างนี้ใช้ไม่ได้", "REJECT", False, "#444746")]
    opts = "".join(
        f'<button id="dec-opt-{code}" type="button" aria-pressed="{"true" if on else "false"}" onclick="selectDecision(\'{code}\', \'{a}\')" class="row decision-opt-btn" style="gap: 12px; text-align: left; font: inherit; color: #1f1f1f; padding: 12px 14px; border-radius: 20px; cursor: pointer; transition: all 0.2s ease; {"border: 2px solid #b3261e; background: #fcefee;" if on else "border: 1px solid #e3e3e3; background: #fff;"}"><span class="row" style="width: 34px; height: 34px; border-radius: 9px; justify-content: center; background: {c}1a;">{ic(i, 18, c, "2")}</span><span class="col grow"><span class="strong">{a}</span><span class="meta">{b}</span></span><span class="radio-indicator" style="width: 18px; height: 18px; box-sizing: border-box; border-radius: 999px; {"border: 5px solid #b3261e;" if on else "border: 2px solid #c4c7c5;"}"></span></button>'
        for i, a, b, code, on, c in options)
    main = f"""{case_header("ร่างและตัดสินใจ")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<div class="col grow" style="padding: 24px 36px; gap: 22px; overflow-y: auto;">
<section class="card" style="border-color: #f2b8b5; overflow: hidden;" aria-label="ผลคัดกรองก่อนใช้โมเดล">
<div class="row" style="background: #b3261e; color: #fff; padding: 10px 16px; gap: 10px;">{ic("alert", 18, "#fff", "2.2")}<span class="strong">ผลคัดกรองก่อนใช้โมเดล</span><span class="grow"></span><span class="mono" style="color: #f9dedc;">URGENT_REVIEW · rule-based</span></div>
<div class="row" style="padding: 14px 16px; gap: 28px; align-items: flex-start;"><div class="col grow" style="gap: 4px;"><span class="strong" style="color: #b3261e; font-size: 16px;">ข้อมูลที่จำเป็นยังไม่ครบ — เข้าเงื่อนไข</span><span>ขาด: สัญญาณชีพ</span></div>
<div class="col" style="max-width: 360px; gap: 2px;"><span class="eyebrow">ข้อจำกัด</span><span class="meta" style="color: #444746;">ระบบไม่ได้อ่านเนื้อหาอาการสำคัญ ผลนี้ไม่แทนการประเมินของแพทย์</span></div></div></section>
<section class="col"><div class="row" style="gap: 12px; padding-bottom: 6px;"><h2 class="display" style="margin: 0; font-size: 22px;">ร่างส่งต่อ ฉบับที่ 1</h2><span class="pill p-info">รอตรวจ</span><span class="grow"></span><span class="mono" style="color: #444746;">09:20 · mock-v2 · design fixed</span></div>{secs}</section>
</div>
<aside class="col" style="width: 400px; flex-shrink: 0; border-left: 1px solid #e3e3e3; background: #f2f0f0; padding: 24px; gap: 14px;">
<div class="col" style="gap: 4px;"><h2 class="display" style="margin: 0; font-size: 20px;">การตัดสินใจของแพทย์</h2><span class="row meta" style="gap: 6px;">{ic("lock", 14, "#444746")}ยังไม่มีผลต่อการดูแลจนกว่าคุณจะบันทึก</span></div>
<div class="col" role="group" aria-label="การตัดสินใจ" style="gap: 8px;">{opts}</div>
<label class="eyebrow" for="reason-select" style="padding-top: 4px;">เหตุผล · จำเป็น</label>
<div class="col" style="background: #fff; border: 1px solid #c4c7c5; border-radius: 20px; padding: 10px 12px; gap: 2px;"><select id="reason-select" style="border: none; font: 500 15px/24px 'Noto Sans Thai',sans-serif; color: #1f1f1f; background: none; padding: 0; width: 100%;"><option>ข้อมูลที่ขาดทำให้ต้องประเมินทันที</option><option>อาการทางคลินิกเข้าข่ายวิกฤต</option><option>ผลการคัดกรองขัดแย้งกับดุลยพินิจแพทย์</option></select><span class="mono" style="color: #747775;">MISSING_INFORMATION</span></div>
<span class="grow"></span>
<button id="btn-save-decision" class="btn btn-lg" type="button" style="background: #b3261e; color: #fff;" onclick="submitDoctorDecision()">บันทึก ESCALATE{ic("arrow", 18, "#fff", "2")}</button><span class="meta" style="text-align: center;">บันทึกพร้อมชื่อผู้ตรวจ dr.somchai · แก้ย้อนไม่ได้</span>
</aside></div>"""
    return platform_shell("คิวเคส", main)

ACTORS = {"physician": ("#1f1f1f", "SC"), "nurse": ("#0b57d0", "NA"), "system": ("#747775", "SYS")}
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
    nodes = [
        ("SNAPSHOT", "อ่านข้อมูลรุ่น 4", "ณ 09:14:02", "#0842a0", "ดึงสถานะข้อมูลที่มี available_at_time <= 09:14:02 ป้องกันข้อมูลอนาคตรั่วไหล"),
        ("MODEL_CALL", "mock-v2", "412 ms", "#1f1f1f", "ส่งคำขอผ่าน Model Gateway adapter ตามข้อกำหนด schema"),
        ("SCHEMA_CHECK", "ตรวจรูปแบบ", "ผ่าน", "#146c2e", "ตรวจสอบโครงสร้าง JSON Response ผลลัพธ์สมบูรณ์ตาม Contract"),
        ("PROPOSE", "ข้อเสนอ 2", "รอบุคลากร", "#8c5a00", "สกัดเวลาเริ่มอาการ 07:00 และอาการเหงื่อออกเป็นข้อเสนอใหม่"),
        ("HUMAN_ACCEPT", "nurse.a ยืนยัน", "09:16:40", "#0b57d0", "พยาบาลกดยืนยันข้อเสนอทั้งสองข้อกลายเป็นข้อเท็จจริงทางคลินิก"),
    ]
    w, h, gap, x0 = 300, 58, 26, 18
    parts = []
    for i, (typ, a, b, c, detail) in enumerate(nodes):
        y = 10 + i * (h + gap)
        click_action = f'onclick="showDagNodeDetail(\'{typ}\', \'{a}\', \'{b}\', \'{detail}\')"'
        parts.append(f'<g class="dag-node" {click_action} style="cursor: pointer;"><rect x="{x0}" y="{y}" width="{w}" height="{h}" rx="20" fill="#fff" stroke="#e3e3e3" style="transition: all 0.2s;"/><rect x="{x0}" y="{y}" width="6" height="{h}" rx="3" fill="{c}"/>')
        parts.append(f'<text x="{x0 + 20}" y="{y + 22}" font-family="Roboto Mono, monospace" font-size="11" fill="{c}" font-weight="500">{typ}</text>')
        parts.append(f'<text x="{x0 + 20}" y="{y + 43}" font-family="Noto Sans Thai, sans-serif" font-size="15" font-weight="600" fill="#1f1f1f">{a}</text>')
        parts.append(f'<text x="{x0 + w - 14}" y="{y + 43}" text-anchor="end" font-family="Roboto Mono, monospace" font-size="12" fill="#444746">{b}</text></g>')
        if i < len(nodes) - 1:
            yy = y + h
            parts.append(f'<path d="M{x0 + 40} {yy + 2} V{yy + gap - 4}" stroke="#747775" stroke-width="1.6"/><path d="M{x0 + 35} {yy + gap - 9} L{x0 + 40} {yy + gap - 3} L{x0 + 45} {yy + gap - 9}" fill="none" stroke="#747775" stroke-width="1.6"/>')
    total = 10 + len(nodes) * (h + gap)
    return f'<svg width="336" height="{total}" viewBox="0 0 336 {total}" role="img" aria-label="กราฟขั้นตอนที่ระบบรันจริงของ run 7f3c">{"".join(parts)}</svg>'

def audit():
    items = []
    for i, (t, kind, who, title, code, refs) in enumerate(EVENTS):
        color, init = ACTORS[kind]
        last = i == len(EVENTS) - 1
        items.append(f"""<div class="row" style="align-items: stretch; gap: 16px;"><span class="mono" style="width: 70px; flex-shrink: 0; padding-top: 6px; color: #444746; text-align: right;">{t}</span>
<span class="col" style="align-items: center; width: 34px; flex-shrink: 0;"><span class="row display" style="width: 34px; height: 34px; border-radius: 999px; background: {color}; color: #fff; justify-content: center; font-size: 11px; flex-shrink: 0;">{init}</span>{'' if last else '<span style="width: 2px; flex-grow: 1; background: #e3e3e3;"></span>'}</span>
<div class="col grow" style="padding: 4px 0 18px; gap: 2px;"><span class="row" style="gap: 10px;"><span class="strong" style="font-size: 16px;">{title}</span><span class="meta">{who}</span></span><span class="row" style="gap: 8px;"><span class="mono" style="color: #0b57d0;">{code}</span><span class="meta">{refs}</span></span></div></div>""")
    legend = "".join(f'<span class="row meta" style="gap: 6px;"><span style="width: 10px; height: 10px; border-radius: 999px; background: {c};"></span>{l}</span>' for c, l in [("#1f1f1f", "แพทย์"), ("#0b57d0", "พยาบาล"), ("#747775", "ระบบ")])
    main = f"""{case_header("Audit และ trace")}
<div class="row grow" style="align-items: stretch; min-height: 0;">
<section class="col grow" style="padding: 24px 36px; gap: 18px; overflow-y: auto;"><div class="row" style="gap: 14px;"><h2 class="display" style="margin: 0; font-size: 22px;">Audit</h2><span class="meta">เพิ่มต่อท้ายเท่านั้น · เก็บการอ้างอิง ไม่เก็บข้อความระบุตัวตน</span><span class="grow"></span>{legend}</div>
<div class="col">{''.join(items)}</div></section>
<aside class="col" style="width: 400px; flex-shrink: 0; border-left: 1px solid #e3e3e3; background: #f2f0f0; padding: 24px 28px; gap: 12px; overflow-y: auto;">
<div class="col" style="gap: 2px;"><span class="eyebrow">Executed DAG</span><h2 class="display" style="margin: 0; font-size: 20px;">run 7f3c · design single</h2><span class="meta">ขั้นตอนที่ระบบรันจริง ส่งออกและ replay ได้ ไม่ใช่ความคิดของโมเดล</span></div>
{dag()}
<div class="row" style="gap: 8px; flex-wrap: wrap;"><span class="chip"><span class="mono">contract</span>synthetic_intake_v1</span><span class="chip"><span class="mono">provider</span>mock-v2 offline</span><span class="chip"><span class="mono">calls</span>3 / 8</span></div>
</aside></div>"""
    return platform_shell("คิวเคส", main)

def before():
    return f"""<div class="col" style="padding: 36px 40px; gap: 24px; max-width: 1300px; margin: 0 auto; overflow-y: auto;">
<div class="row" style="gap: 16px; align-items: baseline;"><span class="pill p-proto-light">วิวัฒนาการการออกแบบ</span><span class="meta">Senior Project · Medical Decision Support</span></div>
<h1 class="display" style="margin: 0; font-size: 32px;">เปรียบเทียบก่อน-หลังการปรับปรุงดีไซน์ (Design Redesign)</h1>
<p class="meta" style="margin: 0; font-size: 16px; line-height: 28px;">
จากการทำ Formative Contextual Walkthrough กับบุคลากรทางการแพทย์ พบว่าเวอร์ชันเดิมมีจุดอ่อนเรื่องความโดดเด่นของสัญญาณฉุกเฉิน (Red Flags) และการแบ่งบทบาทที่ยังไม่แยกกันชัดเจนระหว่างพยาบาลและแพทย์ ทางทีมจึงทำการ Redesign ครั้งใหญ่ตามข้อกำหนด DEC-0017 และ DEC-0018
</p>

<div class="row" style="gap: 24px; align-items: stretch; flex-wrap: wrap;">
<div class="card col grow" style="flex: 1 1 500px; padding: 24px; gap: 14px; border: 2px solid #e3e3e3;">
<span class="pill p-neutral">หน้าจอเดิม (ก่อน Redesign)</span>
<ul style="margin: 0; padding-left: 20px; line-height: 28px; color: #444746;">
<li>ใช้ธีมมืดและมี Animation Orb ซึ่งดึงความสนใจของพยาบาลออกจากข้อมูลผู้ป่วย</li>
<li>การ์ดทุกส่วนมีน้ำหนักสายตาเท่ากันหมด ทำให้มองข้ามระดับความเร่งด่วน (Urgency Under-triage)</li>
<li>หน้าจอพยาบาลและแพทย์ปะปนกันใน URL เดียว ไม่แยกบทบาทการทำงาน</li>
<li>ไม่ได้แยกแยะชัดเจนระหว่าง 'ข้อความถอดเสียง' กับ 'ข้อเท็จจริงที่ยืนยันแล้ว'</li>
</ul>
<img src="assets/workspace-preview.png" alt="ก่อน Redesign" style="width: 100%; border-radius: 16px; border: 1px solid #e3e3e3;" onerror="this.style.display='none'">
</div>

<div class="card col grow" style="flex: 1 1 500px; padding: 24px; gap: 14px; border: 2px solid #0b57d0; background: #fff;">
<span class="pill p-info">หน้าจอใหม่: Pratu (ปัจจุบัน)</span>
<ul style="margin: 0; padding-left: 20px; line-height: 28px; color: #1f1f1f;">
<li><strong>ธีมสว่างคลีน (Gemini-inspired):</strong> ตัวอักษรคมชัด ผ่านมาตรฐาน WCAG AA 8.95:1</li>
<li><strong>Red Flags Banner เด่นชัด:</strong> แถบสีแดงพร้อมไอคอนเตือนฉุกเฉินด้านบนสุด ห้ามโมเดลลดทอน</li>
<li><strong>แยก 2 บทบาทชัดเจน:</strong> <code>Pratu Intake (/nurse)</code> สำหรับพยาบาล และ <code>Pratu Console (/platform)</code> สำหรับแพทย์</li>
<li><strong>Human Confirmation Gate:</strong> มีกระบวนการ Review และยืนยันก่อนข้อมูลจะกลายเป็น Fact ทุกครั้ง</li>
<li><strong>Transparent Executed DAG:</strong> แสดงขั้นตอนการคำนวณที่ Replay ได้อย่างโปร่งใส</li>
</ul>
<img src="assets/workspace-case-preview.png" alt="หลัง Redesign" style="width: 100%; border-radius: 16px; border: 1px solid #e3e3e3;" onerror="this.style.display='none'">
</div>
</div>
</div>"""

CSS = """
:root {
  --bg-canvas: #faf9f9;
  --text-main: #1f1f1f;
  --text-muted: #444746;
  --text-dim: #747775;
  --primary: #0b57d0;
  --primary-hover: #0842a0;
  --primary-container: #d3e3fd;
  --urgent: #b3261e;
  --urgent-container: #f9dedc;
  --warn: #7a4f00;
  --warn-container: #fff3dc;
  --success: #146c2e;
  --success-container: #e6f4ea;
  --border: #e3e3e3;
  --surface: #ffffff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg-canvas);
  color: var(--text-main);
  font: 400 15px/24px 'Noto Sans Thai', sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--primary); text-decoration: none; }
a:hover { color: var(--primary-hover); }

/* Global Switcher Toolbar */
#global-toolbar {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: #111c26;
  color: #fff;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  font-size: 13px;
  flex-wrap: wrap;
}
#global-toolbar .brand-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #fff;
  letter-spacing: -0.01em;
}
#global-toolbar .nav-pills {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
#global-toolbar .nav-pill {
  padding: 4px 12px;
  border-radius: 9999px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(255,255,255,0.06);
  color: #d1d5db;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s ease;
  white-space: nowrap;
}
#global-toolbar .nav-pill:hover {
  background: rgba(255,255,255,0.18);
  color: #fff;
}
#global-toolbar .nav-pill.active {
  background: #0b57d0;
  color: #fff;
  border-color: #0b57d0;
  font-weight: 600;
}
#global-toolbar .toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
#global-toolbar .btn-tool {
  background: rgba(255,255,255,0.1);
  color: #fff;
  border: 1px solid rgba(255,255,255,0.2);
  padding: 4px 10px;
  border-radius: 9999px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
#global-toolbar .btn-tool:hover {
  background: rgba(255,255,255,0.25);
}

/* Screens Stage */
#stage-container {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: calc(100vh - 52px);
  padding: 16px;
  background: #ecebe6;
  overflow: auto;
}
.screen-wrapper {
  display: none;
  background: #faf9f9;
  box-shadow: 0 12px 40px rgba(0,0,0,0.08);
  overflow: hidden;
  position: relative;
  transition: all 0.3s ease;
}
.screen-wrapper.active {
  display: flex;
  flex-direction: column;
}

/* Device Mockup Frames */
.frame-desktop {
  width: 1440px;
  min-height: 900px;
  height: 900px;
  border-radius: 12px;
}
.frame-tablet {
  width: 768px;
  min-height: 1024px;
  height: 1024px;
  border-radius: 28px;
  border: 12px solid #1f1f1f;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
.frame-mobile {
  width: 390px;
  min-height: 844px;
  height: 844px;
  border-radius: 44px;
  border: 12px solid #1f1f1f;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
}
.device-notch {
  width: 120px;
  height: 24px;
  background: #1f1f1f;
  border-bottom-left-radius: 14px;
  border-bottom-right-radius: 14px;
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 50;
  display: none;
}
.frame-mobile .device-notch {
  display: block;
}

/* UI Elements */
.screen {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #faf9f9;
  color: #1f1f1f;
  width: 100%;
  height: 100%;
}
.row { display: flex; align-items: center; }
.col { display: flex; flex-direction: column; }
.grow { flex-grow: 1; min-width: 0; }
.display { font-family: 'Noto Sans Thai', sans-serif; font-weight: 500; letter-spacing: -0.01em; }
.mono { font-family: 'Roboto Mono', monospace; font-size: 13px; letter-spacing: 0; }
.meta { font-size: 13px; line-height: 20px; color: #444746; }
.strong { font-weight: 600; }
.eyebrow { font-size: 12px; line-height: 16px; letter-spacing: 0.06em; text-transform: uppercase; color: #444746; font-weight: 600; }
.chrome { background: #f2f0f0; color: #1f1f1f; }
.chrome .meta { color: #444746; }

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  white-space: nowrap;
}
.p-urgent { background: #b3261e; color: #fff; }
.p-warn { background: #fff3dc; color: #7a4f00; }
.p-ok { background: #e6f4ea; color: #146c2e; }
.p-info { background: #d3e3fd; color: #0842a0; }
.p-neutral { background: #f2f0f0; color: #444746; }
.p-proto { border: 1px solid #e6c47a; color: #7a4f00; background: #fff3dc; }
.p-proto-light { border: 1px solid #e6c47a; color: #7a4f00; background: #fff3dc; }

.btn {
  box-sizing: border-box;
  height: 40px;
  padding: 0 16px;
  border-radius: 9999px;
  font: 500 15px/24px 'Noto Sans Thai', sans-serif;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid transparent;
  background: none;
  color: #1f1f1f;
  cursor: pointer;
  white-space: nowrap;
  text-decoration: none;
  transition: all 0.15s ease;
}
.btn-primary { background: #0b57d0; color: #fff; }
.btn-primary:hover { background: #0842a0; color: #fff; }
.btn-ink { background: #1f1f1f; color: #fff; }
.btn-ink:hover { background: #3c3c3c; color: #fff; }
.btn-secondary { background: #fff; border-color: #c4c7c5; }
.btn-secondary:hover { background: #f2f0f0; }
.btn-ghost-light { color: #0b57d0; background: #fff; border-color: #c4c7c5; }
.btn-ghost-light:hover { background: #eef3fd; color: #0842a0; }
.btn-white { background: #fff; color: #b3261e; font-weight: 600; }
.btn-white:hover { background: #f9dedc; }
.btn-text { color: #0b57d0; padding: 0 6px; }
.btn-text:hover { color: #0842a0; text-decoration: underline; }
.btn-lg { height: 48px; padding: 0 20px; font-size: 16px; }

.card { background: #fff; border: 1px solid #efefef; border-radius: 28px; box-shadow: rgba(0,0,0,0.04) 0 0 20px 0; }
.line-b { border-bottom: 1px solid #e3e3e3; }
.line-t { border-top: 1px solid #e3e3e3; }
.icon { flex-shrink: 0; }
.tr { display: grid; align-items: center; padding: 14px 20px; border-bottom: 1px solid #efefef; gap: 16px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  border-radius: 9999px;
  background: #faf9f9;
  border: 1px solid #e3e3e3;
  font-size: 13px;
  line-height: 20px;
  color: #444746;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}
.chip:hover {
  background: #eef3fd;
  border-color: #a8c7fa;
  color: #0842a0;
}

@keyframes wavePulse {
  0% { transform: scaleY(0.4); opacity: 0.6; }
  100% { transform: scaleY(1.1); opacity: 1; }
}

/* Modals & Toasts */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: none;
  align-items: center;
  justify-content: center;
}
.modal-box {
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 24px 60px rgba(0,0,0,0.25);
  max-width: 640px;
  width: 90%;
  padding: 28px;
  position: relative;
  max-height: 90vh;
  overflow-y: auto;
}
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: #1f1f1f;
  color: #fff;
  padding: 12px 20px;
  border-radius: 9999px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  z-index: 3000;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 500;
  transform: translateY(100px);
  opacity: 0;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.toast.show {
  transform: translateY(0);
  opacity: 1;
}

/* Mobile responsive stage */
@media (max-width: 1480px) {
  .frame-desktop {
    width: 100%;
    min-height: 800px;
    height: auto;
  }
}
"""

JAVASCRIPT = """
let currentScreen = 'nurse-desktop';
let isDeviceFrameActive = true;
let isRecording = true;
let confirmedCount = 2;
let selectedDecision = 'ESCALATE';

function navigateTo(screenId) {
  const wrappers = document.querySelectorAll('.screen-wrapper');
  wrappers.forEach(w => w.classList.remove('active'));
  
  const target = document.getElementById('screen-' + screenId);
  if (target) {
    target.classList.add('active');
    currentScreen = screenId;
    window.location.hash = screenId;
    
    // update toolbar pills
    document.querySelectorAll('.nav-pill').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-target') === screenId);
    });
    
    // scroll stage to top
    document.getElementById('stage-container').scrollTop = 0;
  }
}

function toggleDeviceFrame() {
  isDeviceFrameActive = !isDeviceFrameActive;
  const tablet = document.getElementById('screen-nurse-tablet');
  const mobile = document.getElementById('screen-nurse-mobile');
  
  if (isDeviceFrameActive) {
    tablet.classList.add('frame-tablet');
    tablet.classList.remove('frame-desktop');
    mobile.classList.add('frame-mobile');
    mobile.classList.remove('frame-desktop');
  } else {
    tablet.classList.remove('frame-tablet');
    tablet.classList.add('frame-desktop');
    mobile.classList.remove('frame-mobile');
    mobile.classList.add('frame-desktop');
  }
  showToast(isDeviceFrameActive ? 'เปิดโหมดกรอบอุปกรณ์จำลอง (Device Frame)' : 'เปิดโหมดขยายเต็มพื้นที่');
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

function confirmFact(cardId, label, value, src) {
  const card = document.getElementById(cardId);
  if (card) {
    card.style.opacity = '0';
    card.style.transform = 'translateX(20px)';
    setTimeout(() => {
      card.remove();
      confirmedCount++;
      
      // Add to confirmed list
      const list = document.getElementById('confirmed-list');
      if (list) {
        const item = document.createElement('div');
        item.className = 'row line-t';
        item.style.cssText = 'gap: 12px; padding: 10px 0; align-items: flex-start; animation: fadeIn 0.3s ease;';
        item.innerHTML = `<span class="row" style="width: 22px; height: 22px; border-radius: 999px; background: #e6f4ea; justify-content: center; margin-top: 2px;">
          <svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#146c2e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
        </span>
        <div class="col grow"><span class="meta">${label}</span><span class="strong">${value}</span></div>
        <span class="mono" style="color: #747775;">09:16</span>`;
        list.appendChild(item);
      }
      
      // Update progress
      updateProgress();
      showToast(`ยืนยันข้อมูล "${label}" สำเร็จ`);
    }, 250);
  }
}

function updateProgress() {
  const total = 6;
  const remainingPending = document.querySelectorAll('#pending-section .pending-card').length - 1;
  const filled = confirmedCount;
  
  const filledEl = document.getElementById('progress-filled');
  if (filledEl) filledEl.textContent = filled;
  
  const countFilled = document.getElementById('count-filled');
  if (countFilled) countFilled.textContent = filled;
  
  const countPending = document.getElementById('count-pending');
  if (countPending) countPending.textContent = Math.max(0, remainingPending);
  
  const headerPending = document.getElementById('pending-header');
  if (headerPending) headerPending.textContent = `รอคุณยืนยัน · ${Math.max(0, remainingPending)}`;
  
  const badgeConfirmed = document.getElementById('confirmed-count-badge');
  if (badgeConfirmed) badgeConfirmed.textContent = filled;
  
  // Update segment bars
  for (let i = 0; i < total; i++) {
    const seg = document.getElementById(`prog-seg-${i}`);
    if (seg) {
      if (i < filled) seg.style.background = '#0b57d0';
      else if (i < filled + remainingPending) seg.style.background = '#e8b04b';
      else seg.style.background = '#e3e3e3';
    }
  }
  
  if (remainingPending <= 0) {
    const pendingSec = document.getElementById('pending-section');
    if (pendingSec) pendingSec.style.display = 'none';
    
    const footerTitle = document.getElementById('footer-ready-title');
    if (footerTitle) footerTitle.textContent = `พร้อมส่งให้แพทย์ด้วยข้อมูลที่ยืนยันแล้ว ${filled} รายการ`;
    
    const footerDesc = document.getElementById('footer-ready-desc');
    if (footerDesc) footerDesc.innerHTML = `<span style="color: #146c2e;">✓ ยืนยันข้อมูลครบตามข้อเสนอ · ส่งต่อให้แพทย์ตรวจได้ทันที</span>`;
  }
}

function toggleRecording() {
  isRecording = !isRecording;
  const label = document.getElementById('recording-label');
  const dot = document.querySelector('.record-dot');
  const text = document.getElementById('toggle-record-text');
  const bars = document.querySelectorAll('.wave-bar');
  
  if (isRecording) {
    if (label) label.textContent = 'กำลังฟัง';
    if (dot) dot.style.background = '#b3261e';
    if (text) text.textContent = 'หยุดบันทึก';
    bars.forEach(b => b.style.animationPlayState = 'running');
    showToast('กำลังรับเสียงซักประวัติ...');
  } else {
    if (label) label.textContent = 'หยุดชั่วคราว';
    if (dot) dot.style.background = '#747775';
    if (text) text.textContent = 'บันทึกต่อ';
    bars.forEach(b => b.style.animationPlayState = 'paused');
    showToast('หยุดบันทึกเสียงชั่วคราว');
  }
}

function sendToAssistant() {
  showToast('ส่งข้อความซักประวัติไปยังผู้ช่วย AI กำลังประมวลผล...');
  setTimeout(() => {
    showToast('ผู้ช่วย AI เสนอข้อเท็จจริงใหม่ 2 รายการ');
  }, 1000);
}

function triggerUrgentAlert() {
  showModal('แจ้งเตือนแพทย์เวรฉุกเฉิน', `
    <div class="col" style="gap: 14px;">
      <div class="row" style="gap: 12px; color: #b3261e;">
        <svg class="icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#b3261e" stroke-width="2"><path d="M12 4 2.8 19.5h18.4Z"/><path d="M12 10v4.5M12 17.2v.3"/></svg>
        <span class="display" style="font-size: 20px; font-weight: 600;">ส่งสัญญาณแจ้งแพทย์เวรแล้ว</span>
      </div>
      <p style="margin: 0; line-height: 26px;">ระบบได้ส่งข้อความด่วนไปยังแดชบอร์ดของแพทย์เวรฉุกเฉิน (dr.somchai) ระบุเคส <strong>demo-014</strong> เนื่องจากมีภาวะเจ็บแน่นหน้าอกร้าวไปแขนซ้าย และยังขาดสัญญาณชีพ</p>
      <div class="row" style="justify-content: flex-end; gap: 8px; margin-top: 10px;">
        <button class="btn btn-primary" onclick="closeModal()">รับทราบ</button>
      </div>
    </div>
  `);
}

function promptVitalSign() {
  showModal('วัดสัญญาณชีพเพิ่มเติม', `
    <div class="col" style="gap: 14px;">
      <h3 class="display" style="margin: 0; font-size: 20px;">บันทึกสัญญาณชีพเคส demo-014</h3>
      <p class="meta" style="margin: 0;">สัญญาณชีพเป็นข้อมูลจำเป็น (Required Minimum Intake at T0) ที่ต้องมีก่อนการประเมินความเร่งด่วน</p>
      <div class="row" style="gap: 12px; flex-wrap: wrap;">
        <input type="text" placeholder="ความดัน เช่น 135/85" style="padding: 10px 14px; border: 1px solid #c4c7c5; border-radius: 9999px; flex: 1 1 140px;">
        <input type="text" placeholder="ชีพจร เช่น 88 bpm" style="padding: 10px 14px; border: 1px solid #c4c7c5; border-radius: 9999px; flex: 1 1 140px;">
        <input type="text" placeholder="SpO₂ เช่น 98%" style="padding: 10px 14px; border: 1px solid #c4c7c5; border-radius: 9999px; flex: 1 1 140px;">
      </div>
      <div class="row" style="justify-content: flex-end; gap: 8px; margin-top: 10px;">
        <button class="btn btn-secondary" onclick="closeModal()">ยกเลิก</button>
        <button class="btn btn-primary" onclick="closeModal(); showToast('บันทึกสัญญาณชีพจำลองเรียบร้อย')">บันทึก</button>
      </div>
    </div>
  `);
}

function editFactPrompt(label, value) {
  showModal(`แก้ไข ${label}`, `
    <div class="col" style="gap: 14px;">
      <h3 class="display" style="margin: 0; font-size: 20px;">แก้ไขข้อมูล: ${label}</h3>
      <input type="text" value="${value}" style="padding: 10px 14px; border: 1px solid #c4c7c5; border-radius: 12px; font: inherit;">
      <div class="row" style="justify-content: flex-end; gap: 8px; margin-top: 10px;">
        <button class="btn btn-secondary" onclick="closeModal()">ยกเลิก</button>
        <button class="btn btn-primary" onclick="closeModal(); showToast('แก้ไขข้อมูลเรียบร้อย')">บันทึกการแก้ไข</button>
      </div>
    </div>
  `);
}

function switchMobileTab(tab) {
  const chatView = document.getElementById('mob-view-chat');
  const factsView = document.getElementById('mob-view-facts');
  const chatTab = document.getElementById('mob-tab-chat');
  const factsTab = document.getElementById('mob-tab-facts');
  
  if (tab === 'chat') {
    chatView.style.display = 'flex';
    factsView.style.display = 'none';
    chatTab.style.background = '#fff';
    chatTab.style.color = '#1f1f1f';
    factsTab.style.background = 'transparent';
    factsTab.style.color = '#444746';
  } else {
    chatView.style.display = 'none';
    factsView.style.display = 'flex';
    factsTab.style.background = '#fff';
    factsTab.style.color = '#1f1f1f';
    chatTab.style.background = 'transparent';
    chatTab.style.color = '#444746';
  }
}

function selectDecision(code, label) {
  selectedDecision = code;
  const btns = document.querySelectorAll('.decision-opt-btn');
  btns.forEach(b => {
    b.style.border = '1px solid #e3e3e3';
    b.style.background = '#fff';
    const indicator = b.querySelector('.radio-indicator');
    if (indicator) indicator.style.border = '2px solid #c4c7c5';
  });
  
  const activeBtn = document.getElementById('dec-opt-' + code);
  if (activeBtn) {
    const isEscalate = code === 'ESCALATE';
    activeBtn.style.border = isEscalate ? '2px solid #b3261e' : '2px solid #0b57d0';
    activeBtn.style.background = isEscalate ? '#fcefee' : '#eef3fd';
    const ind = activeBtn.querySelector('.radio-indicator');
    if (ind) ind.style.border = isEscalate ? '5px solid #b3261e' : '5px solid #0b57d0';
  }
  
  const submitBtn = document.getElementById('btn-save-decision');
  if (submitBtn) {
    submitBtn.innerHTML = `บันทึก ${label} <svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`;
    submitBtn.style.background = code === 'ESCALATE' ? '#b3261e' : '#0b57d0';
  }
}

function submitDoctorDecision() {
  showToast(`บันทึกคำสั่ง ${selectedDecision} โดย dr.somchai เรียบร้อยแล้ว (ลง Audit Trail)`);
  setTimeout(() => {
    navigateTo('platform-audit');
  }, 1000);
}

function inspectEvidence(code, label) {
  showModal(`หลักฐานอ้างอิง ${code}`, `
    <div class="col" style="gap: 12px;">
      <div class="row" style="gap: 8px;">
        <span class="mono pill p-info">${code}</span>
        <span class="strong" style="font-size: 18px;">${label}</span>
      </div>
      <p class="meta" style="margin: 0; line-height: 24px;">
        บันทึกเวลาที่ได้รับข้อมูล (available_at_time): 09:12:30 น.<br>
        แหล่งที่มา: พยาบาลซักประวัติ (STAFF_CONFIRMED)<br>
        ความคงเส้นคงวาของเวลา: ผ่านการตรวจสอบ Temporal Leakage Audit
      </p>
      <div class="row" style="justify-content: flex-end; margin-top: 12px;">
        <button class="btn btn-primary" onclick="closeModal()">ปิด</button>
      </div>
    </div>
  `);
}

function showDagNodeDetail(typ, name, time, desc) {
  showModal(`ขั้นตอนใน Executed DAG: ${typ}`, `
    <div class="col" style="gap: 14px;">
      <div class="row" style="gap: 10px;">
        <span class="mono pill p-info">${typ}</span>
        <span class="strong" style="font-size: 20px;">${name}</span>
        <span class="meta mono" style="margin-left: auto;">${time}</span>
      </div>
      <p style="margin: 0; font-size: 15px; line-height: 26px;">${desc}</p>
      <div class="card col" style="padding: 12px; background: #faf9f9; font-size: 13px; font-family: monospace;">
        <div>status: COMPLETED</div>
        <div>deterministic: true</div>
        <div>replayable: true</div>
      </div>
      <div class="row" style="justify-content: flex-end; margin-top: 10px;">
        <button class="btn btn-primary" onclick="closeModal()">ตกลง</button>
      </div>
    </div>
  `);
}

function showCaseInfoModal() {
  showModal('ข้อมูลเคสจำลอง (Synthetic Case Study)', `
    <div class="col" style="gap: 16px;">
      <div class="row" style="gap: 10px;">
        <span class="mono strong" style="font-size: 22px;">demo-014</span>
        <span class="pill p-urgent">ต้องให้แพทย์ดูโดยเร็ว</span>
        <span class="pill p-proto-light">ข้อมูลสังเคราะห์</span>
      </div>
      <div class="col" style="gap: 8px; line-height: 26px; color: #1f1f1f;">
        <div><strong>ผู้ป่วย:</strong> ชาย อายุ 58 ปี (Non-trauma, Non-obstetric)</div>
        <div><strong>อาการสำคัญ:</strong> เจ็บแน่นหน้าอกร้าวไปแขนซ้ายตั้งแต่ 07:00 น. มีเหงื่อแตก ไม่มีหายใจลำบาก</div>
        <div><strong>ประเด็นทางคลินิก (Key Clinical Rationale):</strong>
          <ul style="margin: 6px 0; padding-left: 20px;">
            <li><strong>จังหวะ T0:</strong> แรกรับยังไม่มีการวัดสัญญาณชีพ (Missing Vitals)</li>
            <li><strong>Safety Gate ทำงาน:</strong> Rule-based Safety Screening ดักจับทันทีว่าขาดข้อมูลวิกฤต จึงติดป้าย <code>URGENT_REVIEW</code> โดยที่โมเดล AI ไม่มีสิทธิ์ลดระดับความเร่งด่วนนี้</li>
            <li><strong>Human-in-the-loop:</strong> เสียงซักประวัติจะต้องผ่านการกดยืนยัน (Confirm) จากพยาบาลก่อนเข้าสู่สถานะ Fact</li>
            <li><strong>Auditability:</strong> ทุกขั้นตอนถูกบันทึกเป็น Executed DAG ตรวจสอบย้อนหลังได้ 100%</li>
          </ul>
        </div>
      </div>
      <div class="row" style="justify-content: flex-end; margin-top: 10px;">
        <button class="btn btn-primary" onclick="closeModal()">เข้าใจแล้ว</button>
      </div>
    </div>
  `);
}

function showNewSyntheticModal() {
  showModal('เริ่มเคสจำลองใหม่', `
    <div class="col" style="gap: 14px;">
      <h3 class="display" style="margin: 0; font-size: 20px;">สร้างเคสจำลองทางคลินิก (Synthetic Case)</h3>
      <p class="meta" style="margin: 0;">เลือกสถานการณ์จำลองตาม multi-system scenarios ใน PRODUCT_SPEC.md:</p>
      <div class="col" style="gap: 8px;">
        <button class="btn btn-secondary" style="text-align: left; justify-content: flex-start;" onclick="closeModal(); showToast('โหลดเคส: Chest Pain with Urgent Pattern')">🫀 Chest Pain (เจ็บแน่นหน้าอก / High Risk)</button>
        <button class="btn btn-secondary" style="text-align: left; justify-content: flex-start;" onclick="closeModal(); showToast('โหลดเคส: Shortness of Breath / Cardiopulmonary')">🫁 Shortness of Breath (เหนื่อยหอบฉับพลัน)</button>
        <button class="btn btn-secondary" style="text-align: left; justify-content: flex-start;" onclick="closeModal(); showToast('โหลดเคส: Acute Abdominal Pain')">🩺 Acute Abdominal Pain (ปวดท้องเฉียบพลัน)</button>
        <button class="btn btn-secondary" style="text-align: left; justify-content: flex-start;" onclick="closeModal(); showToast('โหลดเคส: Low-acuity Routine Case')">🟢 Low Acuity Routine Presentation (คิวปกติ)</button>
      </div>
      <div class="row" style="justify-content: flex-end; margin-top: 10px;">
        <button class="btn btn-text" onclick="closeModal()">ยกเลิก</button>
      </div>
    </div>
  `);
}

function resetNextCase() {
  showToast('โหลดเคสจำลองใหม่ (demo-015: Acute Dyspnea) เรียบร้อย');
  setTimeout(() => {
    navigateTo('nurse-desktop');
  }, 800);
}

function saveDraftToast() {
  showToast('บันทึกร่างข้อมูลซักประวัติชั่วคราวแล้ว');
}

function showFeatureNotice(msg) {
  showToast(msg);
}

function showModal(title, htmlContent) {
  const modal = document.getElementById('global-modal');
  const body = document.getElementById('modal-content');
  if (modal && body) {
    body.innerHTML = htmlContent;
    modal.style.display = 'flex';
  }
}

function closeModal() {
  const modal = document.getElementById('global-modal');
  if (modal) modal.style.display = 'none';
}

function showToast(msg) {
  const toast = document.getElementById('global-toast');
  if (toast) {
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 3000);
  }
}

// Filter queue
function filterQueue(type) {
  const buttons = document.querySelectorAll('.queue-filter-btn');
  buttons.forEach(b => {
    b.style.background = '#fff';
    b.style.color = '#444746';
    b.style.border = '1px solid #e3e3e3';
  });
  if (event && event.target) {
    event.target.style.background = '#1f1f1f';
    event.target.style.color = '#fff';
  }
  
  const rows = document.querySelectorAll('.queue-row');
  rows.forEach(r => {
    if (type === 'all') r.style.display = 'grid';
    else if (type === 'urgent' && r.getAttribute('data-lvl') === 'urgent') r.style.display = 'grid';
    else if (type === 'waiting' && r.getAttribute('data-lvl') !== 'neutral') r.style.display = 'grid';
    else if (type === 'recheck' && r.textContent.includes('ต้องตรวจใหม่')) r.style.display = 'grid';
    else if (type === 'confirmed' && r.textContent.includes('ยืนยันแล้ว')) r.style.display = 'grid';
    else r.style.display = 'none';
  });
}

function searchQueue(query) {
  const q = query.toLowerCase().trim();
  const rows = document.querySelectorAll('.queue-row');
  rows.forEach(r => {
    r.style.display = r.textContent.toLowerCase().includes(q) ? 'grid' : 'none';
  });
}

// Close modal on click outside
window.addEventListener('click', (e) => {
  const modal = document.getElementById('global-modal');
  if (e.target === modal) closeModal();
});

// Hash navigation on load
window.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash.replace('#', '');
  if (hash && document.getElementById('screen-' + hash)) {
    navigateTo(hash);
  }
});
"""

def generate():
    screens = [
        ("nurse-desktop", "Pratu Intake · Desktop", "frame-desktop", nurse(stacked=False, sent=False)),
        ("nurse-tablet", "Pratu Intake · Tablet", "frame-tablet", nurse(stacked=True, sent=False)),
        ("nurse-mobile", "Pratu Intake · Mobile", "frame-mobile", mobile()),
        ("nurse-handoff", "Pratu Intake · ส่งต่อแล้ว", "frame-desktop", nurse(stacked=False, sent=True)),
        ("platform-queue", "Pratu Console · คิวเคส", "frame-desktop", queue()),
        ("platform-review", "Pratu Console · ตรวจเคส", "frame-desktop", review()),
        ("platform-audit", "Pratu Console · Audit และ trace", "frame-desktop", audit()),
        ("before", "ก่อน Redesign", "frame-desktop", before()),
    ]
    
    screen_elements = []
    for sid, title, frame_cls, body_html in screens:
        active = 'active' if sid == 'nurse-desktop' else ''
        notch = '<div class="device-notch"></div>' if 'mobile' in sid else ''
        screen_elements.append(f"""
        <section id="screen-{sid}" class="screen-wrapper {frame_cls} {active}" data-title="{title}">
          {notch}
          <div class="screen">
            {body_html}
          </div>
        </section>
        """)

    nav_pills = [
        ("nurse-desktop", "Intake (Desktop)"),
        ("nurse-tablet", "iPad (Tablet)"),
        ("nurse-mobile", "iPhone (Mobile)"),
        ("nurse-handoff", "ส่งต่อแล้ว"),
        ("platform-queue", "Console (คิวเคส)"),
        ("platform-review", "ตรวจเคส (Review)"),
        ("platform-audit", "Audit & DAG"),
        ("before", "ก่อน Redesign"),
    ]
    pills_html = "".join(f'<button class="nav-pill {"active" if sid == "nurse-desktop" else ""}" data-target="{sid}" onclick="navigateTo(\'{sid}\')">{label}</button>' for sid, label in nav_pills)

    html = f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pratu (ประตู) · Clinical Front Door Showcase Prototype</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@300;400;500;600;700&family=Roboto+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{CSS}
</style>
</head>
<body>

<!-- Persistent Control Toolbar -->
<header id="global-toolbar">
  <div class="brand-tag">
    <span style="width: 24px; height: 24px; border-radius: 999px; background: #0b57d0; display: inline-flex; align-items: center; justify-content: center;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 20V6.5a6 6 0 0 1 12 0V20"/><path d="M4 20h16"/><circle cx="14.5" cy="13.5" r="0.9" fill="currentColor"/></svg>
    </span>
    <span>Pratu · Senior Project Prototype</span>
  </div>
  
  <div class="nav-pills">
    {pills_html}
  </div>

  <div class="toolbar-actions">
    <button class="btn-tool" onclick="showCaseInfoModal()">ℹ️ ข้อมูลเคส (demo-014)</button>
    <button class="btn-tool" onclick="toggleDeviceFrame()">📱 กรอบอุปกรณ์</button>
    <button class="btn-tool" onclick="toggleFullscreen()">⛶ เต็มจอ</button>
  </div>
</header>

<!-- Interactive Stage -->
<main id="stage-container">
  {''.join(screen_elements)}
</main>

<!-- Global Modal -->
<div id="global-modal" class="modal-backdrop">
  <div class="modal-box">
    <div id="modal-content"></div>
  </div>
</div>

<!-- Global Toast -->
<div id="global-toast" class="toast">การกระทำสำเร็จ</div>

<script>
{JAVASCRIPT}
</script>
</body>
</html>"""

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Generated standalone prototype at {OUTPUT_HTML} ({len(html)} bytes)")

if __name__ == "__main__":
    generate()
