'use strict';
const $=id=>document.getElementById(id), key=()=>crypto.randomUUID();
let current=null, recording=null, speechEnabled=false, pending=null;
const status=(s,error=false)=>{$('status').textContent=s;$('status').className=error?'error':'';};
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
async function request(path, options){
 let res;
 try{res=await fetch('/v2'+path,options);}catch(e){if(options.method!=='GET' && !path.startsWith('/speech/')){pending={path,options};$('retry').hidden=false;}throw Error('เครือข่ายขัดข้อง ข้อความยังอยู่ หากมีคำขอค้างให้ตรวจคำขอเดิม');}
 let data;try{data=await res.json();}catch(e){if(options.method!=='GET' && !path.startsWith('/speech/')){pending={path,options};$('retry').hidden=false;}throw Error('อ่านผลตอบกลับไม่ได้ ข้อความยังอยู่ กรุณาตรวจคำขอเดิม');}
 if(res.status>=500 && options.method!=='GET' && !path.startsWith('/speech/')){pending={path,options};$('retry').hidden=false;throw Error(data.error||'ระบบขัดข้อง กรุณาตรวจคำขอเดิม');}
 if(!res.ok){if(res.status===409 && data.error==='RUN_IN_PROGRESS'){pending={path,options};$('retry').hidden=false;}else if(pending?.path===path){pending=null;$('retry').hidden=true;}throw Error(data.error||JSON.stringify(data.detail));}
 if(pending?.path===path){pending=null;$('retry').hidden=true;}return data;
}
async function api(path,method='GET',body=null,headers={}){
 if(pending && method!=='GET')throw Error('ตรวจคำขอเดิมให้เสร็จก่อนบันทึกใหม่');
 if($('token').value)headers.Authorization=`Bearer ${$('token').value}`;
 if(body && !(body instanceof FormData)){headers['Content-Type']='application/json';body=JSON.stringify(body);}
 return request(path,{method,headers,body});
}
async function guarded(fn){document.querySelectorAll('button').forEach(b=>b.disabled=true);status('กำลังทำงาน…');try{await fn();status('พร้อม');}catch(e){status(e.message,true);}finally{document.querySelectorAll('button').forEach(b=>b.disabled=b.dataset.locked==='true');$('record').disabled=!speechEnabled;}}
function entry(f){const item=node('div',undefined,'entry');item.id='e-'+f.event_id;item.append(node('strong',f.kind+' · '+f.state),node('p',typeof f.value==='object'?JSON.stringify(f.value):String(f.value??'')),node('small',f.event_id+(f.supersedes_event_id?' → แก้แทน '+f.supersedes_event_id:'')));return item;}
function labelled(label,control){const container=node('label',label);container.append(control);return container;}
function speakButton(text){const button=node('button','อ่านคำตอบด้วยเสียงในเครื่อง');button.onclick=()=>{const voice=window.speechSynthesis?.getVoices().find(v=>v.localService && v.lang.toLowerCase().startsWith('th'));if(!voice){status('ไม่มีเสียงภาษาไทยในเครื่อง ใช้ข้อความต่อได้',true);return;}speechSynthesis.cancel();const out=new SpeechSynthesisUtterance(text);out.voice=voice;out.lang=voice.lang;out.onerror=()=>status('อ่านเสียงไม่ได้ ใช้ข้อความต่อได้',true);speechSynthesis.speak(out);};return button;}
async function refresh(){
 current=await api('/encounters/'+encodeURIComponent($('case-id').value));
 $('revision').textContent=`${current.encounter_id} · revision ${current.case_revision}`;
 const snapshot=await api(`/encounters/${current.encounter_id}/snapshot`);
 $('facts').replaceChildren(...snapshot.evidence.map(entry));
 $('fact-history').replaceChildren(...current.events.map(e=>{const item=entry(e.fact);item.removeAttribute('id');return item;}));
 const caps=await api('/capabilities');speechEnabled=caps.speech;$('capabilities').textContent=`${caps.provider} · ${caps.model} · ${caps.role} · ${caps.validation}`;
 const runs=await api(`/encounters/${current.encounter_id}/turns`);$('conversation').replaceChildren();$('proposals').replaceChildren();
 for(const r of runs){const item=node('div',undefined,'entry');item.append(node('p','คุณ: '+r.user_text),node('p',`ผู้ช่วย (${r.status}): ${r.response}`));if(r.status==='COMPLETED')item.append(speakButton(r.response));$('conversation').append(item);
  for(const proposal of r.proposals.filter(p=>p.proposal_id)){
   const box=node('div',undefined,'entry'), editor=node('textarea'), kind=node('select'), factState=node('select');
   for(const name of ['CHIEF_COMPLAINT','HISTORY','MEDICATION','ALLERGY','VITAL','LAB','REPORT'])kind.append(node('option',name));kind.value=proposal.fact.kind;
   for(const name of ['KNOWN','UNKNOWN','REFUSED','NOT_AVAILABLE'])factState.append(node('option',name));factState.value=proposal.fact.state;
   editor.value=typeof proposal.fact.value==='object'?JSON.stringify(proposal.fact.value):String(proposal.fact.value??'');editor.rows=3;
   box.append(labelled('ประเภทข้อมูลเสนอใหม่',kind),labelled('สถานะข้อมูล',factState),labelled('ค่าข้อมูลที่ตรวจแก้ได้',editor));
   if(proposal.fact.supersedes_event_id)box.append(node('small','เสนอแก้แทน '+proposal.fact.supersedes_event_id));
   const accept=node('button','ตรวจแล้ว ยืนยันข้อมูลนี้');
   accept.dataset.locked=String(r.case_revision!==current.case_revision || r.status!=='COMPLETED' || caps.role==='evaluator');
   accept.onclick=()=>guarded(async()=>{const fact={...proposal.fact,kind:kind.value,state:factState.value,value:factState.value==='KNOWN'?(typeof proposal.fact.value==='object'?JSON.parse(editor.value):typeof proposal.fact.value==='number'?Number(editor.value):editor.value):null};await api(`/runs/${r.run_id}/proposals/${proposal.proposal_id}/accept`,'POST',{expected_revision:current.case_revision,idempotency_key:key(),fact});await refresh();});box.append(accept);$('proposals').append(box);
  }
 }
 $('trace').textContent=runs.length?JSON.stringify(runs.at(-1).trace,null,2):'';
 const drafts=await api(`/encounters/${current.encounter_id}/drafts`);$('drafts').replaceChildren();
 for(const d of drafts.reverse()){
  const box=node('div',undefined,'entry');box.append(node('h3',`ร่าง v${d.draft_revision} · ${d.status} · ${d.effective?"ยืนยันแล้ว":"ยังใช้ไม่ได้"}`),node('p',d.content.summary));
  for(const id of d.content.evidence_ids){const a=node('a',id+' ');a.href='#e-'+id;a.onclick=e=>{e.preventDefault();guarded(async()=>{const fact=await api(`/drafts/${d.draft_id}/evidence/${encodeURIComponent(id)}`);const evidence=node('div');evidence.append(entry(fact));a.replaceWith(evidence);});};box.append(a);}
  box.append(node('p','งานค้าง / ข้อขัดแย้ง: '+d.content.outstanding.join(' / ')));
  for(const dx of d.content.differentials)box.append(node('p',`${dx.possibility}: ${dx.rationale}\nหลักฐาน: ${dx.evidence_ids.join(', ')}\nข้อขัดแย้ง: ${dx.contradictions.join(' / ')}\nข้อมูลขาด: ${dx.missing_information.join(' / ')}`));
  const history=node('details');history.append(node('summary','ประวัติร่างและการตรวจ'),node('pre',JSON.stringify({versions:d.versions,reviews:d.reviews},null,2)));box.append(history);
  if(caps.role==='physician'){
   const editor=node('textarea');editor.value=d.content.summary;editor.rows=5;
   const reason=node('textarea');reason.rows=2;const outstanding=node('textarea');outstanding.value=d.content.outstanding.join('\n');
   const panel=node('details');panel.append(node('summary','แก้เนื้อหาและระบุเหตุผล'),labelled('สรุปฉบับแก้ไข',editor),labelled('งานค้าง (หนึ่งรายการต่อบรรทัด)',outstanding),labelled('เหตุผลแก้ไขหรือปฏิเสธ',reason));box.append(panel);
   for(const action of ['CONFIRM','MODIFY','REJECT']){const b=node('button',({CONFIRM:'ยืนยันร่างนี้',MODIFY:'บันทึกร่างแก้ไข',REJECT:'ปฏิเสธ'})[action]);b.dataset.locked=String(d.status==='STALE');b.onclick=()=>guarded(async()=>{
    if(action==='CONFIRM' && (editor.value!==d.content.summary || outstanding.value!==d.content.outstanding.join('\n'))){panel.open=true;throw Error('มีการแก้ไขที่ยังไม่บันทึก กรุณาบันทึกร่างแก้ไข แล้วตรวจฉบับใหม่ก่อนยืนยัน');}
    if(action!=='CONFIRM' && !reason.value.trim()){panel.open=true;throw Error('กรุณาระบุเหตุผล');}
    const content=action==='MODIFY'?{...d.content,summary:editor.value,outstanding:outstanding.value.split('\n').filter(Boolean)}:null;
    await api(`/drafts/${d.draft_id}/reviews`,'POST',{expected_revision:current.case_revision,idempotency_key:key(),draft_revision:d.draft_revision,expected_review_sequence:d.review_sequence,action,reason:action==='CONFIRM'?null:reason.value,content});await refresh();
   });box.append(b);}
  }
  $('drafts').append(box);
 }
}
$('retry').onclick=()=>guarded(async()=>{if(pending){await request(pending.path,pending.options);await refresh();}});
$('create').onclick=()=>guarded(async()=>{await api('/encounters','POST',{encounter_id:$('case-id').value,age:Number($('age').value)},{'Idempotency-Key':key()});await refresh();});
$('load').onclick=()=>guarded(refresh);
$('fact-form').onsubmit=e=>{e.preventDefault();guarded(async()=>{if(!current)throw Error('เปิดเคสก่อน');const time=$('available').value?new Date($('available').value).toISOString():new Date().toISOString();await api(`/encounters/${current.encounter_id}/events`,'POST',{expected_revision:current.case_revision,idempotency_key:key(),fact:{event_id:key(),kind:$('kind').value,state:$('fact-state').value,value:$('fact-state').value==='KNOWN'?$('fact-value').value:null,observed_at:time,available_at_time:time,supersedes_event_id:$('supersedes').value||null}});$('supersedes').value='';await refresh();});};
$('send').onclick=()=>guarded(async()=>{if(!current)throw Error('เปิดเคสก่อน');const run=await api(`/encounters/${current.encounter_id}/turns`,'POST',{expected_revision:current.case_revision,idempotency_key:key(),text:$('message').value,decision_time:new Date().toISOString(),design_id:$('design').value,intent:'conversation'});await refresh();if(run.status!=='COMPLETED')throw Error(run.error_code);$('message').value='';});
$('draft').onclick=()=>guarded(async()=>{if(!current)throw Error('เปิดเคสก่อน');const d=await api(`/encounters/${current.encounter_id}/drafts`,'POST',{expected_revision:current.case_revision,idempotency_key:key(),decision_time:new Date().toISOString()});await refresh();if(d.error_code)throw Error(d.error_code);});
$('record').disabled=true;
$('record').onclick=async()=>{
 if(recording){recording.stop();return;}
 let stream;
 try{stream=await navigator.mediaDevices.getUserMedia({audio:true});const recorder=new MediaRecorder(stream), chunks=[];recording=recorder;
 recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{recording=null;stream.getTracks().forEach(t=>t.stop());$('record').textContent='เริ่มอัดเสียงจำลอง';guarded(async()=>{const form=new FormData();form.append('file',new Blob(chunks,{type:recorder.mimeType}),'synthetic-audio');const out=await api('/speech/transcriptions','POST',form);$('message').value=[$('message').value,out.text].filter(Boolean).join('\n');});};
 recorder.start();$('record').textContent='หยุดอัดและถอดเสียง';const timer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},60000);recorder.addEventListener('stop',()=>clearTimeout(timer),{once:true});
 }catch(e){stream?.getTracks().forEach(t=>t.stop());recording=null;status('ใช้เสียงไม่ได้ กรุณาพิมพ์ข้อความ: '+e.message,true);}
};
