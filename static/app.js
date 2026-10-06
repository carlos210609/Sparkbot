const $=id=>document.getElementById(id);
const messages=$("messages"),stream=$("stream"),input=$("input"),form=$("chatForm");
const history=[];let executions=0;let currentPage="command";

function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function addMessage(role,text){
 const row=document.createElement("div");row.className="msg "+role;
 row.innerHTML=role==="user"?'<div class="avatar user-avatar">Y</div><div class="bubble"><p>'+esc(text)+'</p></div>':'<div class="avatar">S</div><div class="bubble">'+esc(text).replace(/\n/g,"<br>")+'</div>';
 messages.appendChild(row);messages.scrollTop=messages.scrollHeight;
}
function typing(){const row=document.createElement("div");row.id="typing";row.className="msg bot";row.innerHTML='<div class="avatar">S</div><div class="bubble typing"><i></i><i></i><i></i></div>';messages.appendChild(row);messages.scrollTop=messages.scrollHeight;}
function removeTyping(){const t=$("typing");if(t)t.remove();}
function eventLine(e){
 if(stream.querySelector(".empty"))stream.innerHTML="";
 const el=document.createElement("div");el.className="event";
 const title=e.type==="execution"?(e.skill||e.skill_id):e.type==="verification"?"Verification":e.type==="plan"?"Plan":e.type==="recruit"?"Agent mesh":e.type==="critique"?"Critic":e.type==="observe"?"Observe":"Agent";
 const detail=e.type==="execution"?((e.status||"").toUpperCase()+(e.verified?" · verified":"")):(e.message||e.text||"");
 el.innerHTML='<span class="event-icon">'+(e.type==="execution"?"✓":e.type==="plan"?"◆":e.type==="recruit"?"◈":"•")+'</span><div><b>'+esc(title)+'</b><small>'+esc(detail)+'</small></div>';
 stream.prepend(el);
}

const pages={
 command:["COMMAND CENTER / LIVE","What should SparkBot do?","Converse with the agent, inspect its runtime and follow verified execution."],
 skills:["SKILLS / REGISTRY","Operational skills","Browse, search and inspect SparkBot's capability registry."],
 browser:["BROWSER / MONITOR","Browser Monitor","Audit browser navigation and actions without inventing execution."],
 social:["SOCIAL / OPERATIONS","Social Operations","Open official platforms, prepare content and stage verified publications."],
 approvals:["CONTROL / APPROVALS","Approval Center","Review external actions before they become public."],
 learning:["INTELLIGENCE / LEARNING","Operational Learning","See what worked, what failed and what SparkBot is using to improve."],
 activity:["SYSTEM / ACTIVITY","Activity","Inspect the chronological operational audit trail."]
};
function showPage(name){
 currentPage=name;
 document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("active",n.dataset.page===name));
 document.querySelectorAll(".page").forEach(p=>p.classList.toggle("active",p.id==="page-"+name));
 const p=pages[name];$("pageEyebrow").textContent=p[0];$("pageTitle").textContent=p[1];$("pageDescription").textContent=p[2];
 if(name==="skills")loadSkills();
 if(name==="browser")loadBrowser();
 if(name==="social")loadSocial(); if(name==="approvals")loadApprovals(); if(name==="learning")loadLearning(); if(name==="activity")loadActivity();
}
document.querySelectorAll(".nav").forEach(n=>n.onclick=()=>showPage(n.dataset.page));

async function refresh(){
 try{
  const a=await (await fetch("/api/ai/status")).json();
  $("aiModel").textContent=a.model||"—";$("aiState").textContent=a.configured?"Ready":"API key required";
  $("sideStatus").textContent=a.configured?"Online":"Needs key";$("modelSide").textContent=a.configured?(a.provider+" / "+a.model):"AI not configured";
  $("systemState").textContent=a.configured?"healthy":"needs key";
 }catch(e){$("systemState").textContent="offline";}
 try{
  const d=await (await fetch("/api/snapshot")).json();
  const skills=d.skills||1500; $("metricSkills").textContent=skills.toLocaleString();$("skillCount").textContent=skills.toLocaleString();
  const browsers=d.browser_events||[];$("metricBrowser").textContent=browsers.length;
  const agentCount=d.agents?.total||700; $("metricAgents").textContent=agentCount.toLocaleString();
 }catch(e){}
 try{
  const r=await (await fetch("/api/runtime")).json();
  $("runtimeTools").innerHTML=(r.tools||[]).map(t=>'<div class="tool-row"><span class="tool-dot '+(t.available?"on":"off")+'"></span><div><b>'+esc(t.name)+'</b><small>'+esc(t.description)+'</small></div><em>'+esc(t.available?"AVAILABLE":"OFFLINE")+'</em></div>').join("");
 }catch(e){}
}

async function sendText(text){
 addMessage("user",text);history.push({role:"user",content:text});typing();$("send").disabled=true;
 try{
  const r=await (await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:history})})).json();
  removeTyping();
  if(r.reply){addMessage("bot",r.reply);history.push({role:"assistant",content:r.reply});}
  (r.events||[]).forEach(eventLine);
  const mission=r.mission||{};executions+=(mission.results||[]).length;$("metricExec").textContent=executions;
 }catch(err){removeTyping();addMessage("bot","Não consegui concluir esta etapa: "+err.message);eventLine({type:"verification",text:"A execução foi interrompida."});}
 finally{$("send").disabled=false;input.focus();}
}
form.onsubmit=e=>{e.preventDefault();const text=input.value.trim();if(!text)return;input.value="";input.style.height="auto";sendText(text);};
input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
input.addEventListener("input",()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,180)+"px";});
document.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{showPage("command");input.value=b.dataset.prompt;input.focus();});

async function loadSkills(){
 const q=encodeURIComponent(($("skillSearch").value||"").trim());
 const d=await (await fetch("/api/skills?limit=1500"+(q?"&q="+q:""))).json();
 $("skillsSubtitle").textContent=(d.count||0).toLocaleString()+" registered capabilities";
 $("skillsGrid").innerHTML=(d.skills||[]).map(s=>'<article class="skill-card"><div class="skill-top"><span>'+esc(s.id)+'</span><em class="risk '+esc(s.risk_level)+'">'+esc(s.risk_level)+'</em></div><b>'+esc(s.name)+'</b><p>'+esc(s.description)+'</p><div class="skill-meta"><span>'+esc(s.category)+'</span><span>v'+esc(s.version)+'</span></div></article>').join("")||'<div class="empty">Nenhuma skill encontrada.</div>';
}
let skillTimer; $("skillSearch").addEventListener("input",()=>{clearTimeout(skillTimer);skillTimer=setTimeout(loadSkills,220);});

async function browserStatus(){ try{const d=await (await fetch("/api/browser/status")).json(); const badge=$("browserStatus"); const btn=$("browserStart"); if(badge) badge.textContent=d.started?"RUNNING":(d.installed?"READY":"PLAYWRIGHT REQUIRED"); if(btn) btn.textContent=d.started?"Parar browser":"Iniciar browser"; return d;}catch(e){return null;} }
$("browserStart")?.addEventListener("click",async()=>{const d=await browserStatus(); const url=d?.started?"/api/browser/stop":"/api/browser/start"; await fetch(url); await browserStatus(); loadBrowser();});

async function loadBrowser(){
 const d=await (await fetch("/api/browser")).json(),events=d.events||[]; browserStatus();
 $("browserTotal").textContent=d.count||events.length;$("browserCount").textContent=d.count||events.length;
 $("browserLastUrl").textContent=events[0]?.url||"—";$("browserLastAction").textContent=events[0]?.action||"—";
 $("browserTable").innerHTML=events.length?'<div class="table-head"><span>TIME</span><span>ACTION</span><span>URL / TARGET</span><span>STATUS</span></div>'+events.map(e=>'<div class="table-row"><span>'+esc(e.created_at||"")+'</span><b>'+esc(e.action)+'</b><span>'+esc(e.url||e.target||"—")+'</span><em class="status '+esc(e.status)+'">'+esc(e.status)+'</em></div>').join(""):'<div class="empty">Nenhum evento de browser registrado ainda.</div>';
}
async function loadActivity(){
 const d=await (await fetch("/api/activity?limit=100")).json(),rows=d.activity||[];
 $("activityTable").innerHTML=rows.length?'<div class="table-head"><span>TIME</span><span>TYPE</span><span>MESSAGE</span><span>ID</span></div>'+rows.map(a=>'<div class="table-row"><span>'+esc(a.created_at||"")+'</span><b>'+esc(a.event_type)+'</b><span>'+esc(a.message)+'</span><em>'+esc(a.id)+'</em></div>').join(""):'<div class="empty">Nenhuma atividade registrada.</div>';
}
$("refreshActivity").onclick=loadActivity;

refresh();setInterval(refresh,5000);setInterval(()=>{if(currentPage==="browser")loadBrowser();if(currentPage==="approvals")loadApprovals();if(currentPage==="learning")loadLearning();if(currentPage==="activity")loadActivity();},4000);

async function loadSocial(){
 const d=await (await fetch("/api/social")).json();
 $("socialPlatforms").innerHTML=(d.platforms||[]).map(p=>'<article class="skill-card"><div class="skill-top"><span>'+esc(p.id)+'</span><em class="risk LOW">READY</em></div><b>'+esc(p.name)+'</b><p>'+esc((p.capabilities||[]).join(" · "))+'</p><div class="skill-meta"><button class="small-btn" onclick="openSocial(\''+esc(p.id)+'\',\'home\')">Abrir</button><button class="small-btn" onclick="openSocial(\''+esc(p.id)+'\',\'signup\')">Cadastro</button></div></article>').join("");
}
async function openSocial(platform,purpose){ await fetch("/api/social/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({platform,purpose})}); showPage("browser"); loadBrowser(); }
async function loadApprovals(){
 const d=await (await fetch("/api/approvals")).json(), rows=d.approvals||[];
 const pending=rows.filter(r=>r.value?.status==="PENDING").length; $("approvalCount").textContent=pending;
 $("approvalTable").innerHTML=rows.length?'<div class="table-head"><span>TIME</span><span>ACTION</span><span>REASON</span><span>STATUS</span></div>'+rows.map(r=>'<div class="table-row"><span>'+esc(r.created_at||"")+'</span><b>'+esc(r.value?.action||"")+'</b><span>'+esc(r.value?.reason||"")+'</span><em>'+esc(r.value?.status||"")+((r.value?.status==="PENDING")?'<br><button class="small-btn" onclick="approveAction(\''+esc(r.key)+'\')">Approve</button> <button class="small-btn" onclick="rejectAction(\''+esc(r.key)+'\')">Reject</button>':'')+'</em></div>').join(""):'<div class="empty">Nenhuma ação aguardando aprovação.</div>';
}
async function approveAction(id){await fetch("/api/approvals/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});loadApprovals();loadBrowser();}
async function rejectAction(id){await fetch("/api/approvals/reject",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});loadApprovals();}
async function loadLearning(){
 const d=await (await fetch("/api/learning")).json(), rows=d.events||[];
 $("learningTable").innerHTML=rows.length?'<div class="table-head"><span>TIME</span><span>SUBJECT</span><span>ACTION</span><span>RESULT</span></div>'+rows.map(r=>'<div class="table-row"><span>'+esc(r.created_at||"")+'</span><b>'+esc(r.key||"")+'</b><span>memory</span><em>'+esc(r.value?.score??"")+'</em></div>').join(""):'<div class="empty">Ainda não há eventos de aprendizagem.</div>';
}
