const $=id=>document.getElementById(id);
const messages=$("messages"),stream=$("stream"),input=$("input"),form=$("chatForm");
const history=[];let executions=0;

function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function addMessage(role,text){
 const row=document.createElement("div");row.className="msg "+role;
 row.innerHTML=role==="user"?
 '<div class="avatar user-avatar">Y</div><div class="bubble"><p>'+esc(text)+'</p></div>':
 '<div class="avatar">S</div><div class="bubble">'+esc(text).replace(/\n/g,"<br>")+'</div>';
 messages.appendChild(row);messages.scrollTop=messages.scrollHeight;
}
function typing(){const row=document.createElement("div");row.id="typing";row.className="msg bot";row.innerHTML='<div class="avatar">S</div><div class="bubble typing"><i></i><i></i><i></i></div>';messages.appendChild(row);messages.scrollTop=messages.scrollHeight;}
function removeTyping(){const t=$("typing");if(t)t.remove();}
function eventLine(e){
 if(stream.querySelector(".empty"))stream.innerHTML="";
 const el=document.createElement("div");el.className="event";
 const title=e.type==="execution"?(e.skill||e.skill_id):e.type==="verification"?"Verification":e.type==="plan"?"Plan":e.type==="recruit"?"Agent mesh":e.type==="critique"?"Critic":"Reasoning";
 const detail=e.type==="execution"?((e.status||"").toUpperCase()+(e.verified?" · verified":"")):(e.message||e.text||"");
 el.innerHTML='<span class="event-icon">'+(e.type==="execution"?"✓":e.type==="plan"?"◆":e.type==="recruit"?"◈":"•")+'</span><div><b>'+esc(title)+'</b><small>'+esc(detail)+'</small></div>';
 stream.prepend(el);
}
async function refresh(){
 try{
  const a=await (await fetch("/api/ai/status")).json();
  $("aiModel").textContent=a.model||"auto";
  $("aiState").textContent=a.configured?"Ready":"API key required";
  $("gateway").textContent=a.configured?"NVIDIA / ready":"NVIDIA / not configured";
  $("systemState").textContent=a.configured?"healthy":"needs key";
  $("sideStatus").textContent=a.configured?"Online":"Needs key";
 }catch(e){$("systemState").textContent="offline";}
 try{
  const d=await (await fetch("/api/snapshot")).json();
  $("metricSkills").textContent=(d.skills||1500).toLocaleString();
  $("skillCount").textContent=(d.skills||1500).toLocaleString();
  $("metricBrowser").textContent=(d.browser_events||[]).length;
  const agentCount=d.agents?.total||700;
  const agentMetric=$("metricAgents");
  if(agentMetric)agentMetric.textContent=agentCount.toLocaleString();
 }catch(e){}
}
async function sendText(text){
 addMessage("user",text);history.push({role:"user",content:text});typing();$("send").disabled=true;
 try{
  const r=await (await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:history})})).json();
  removeTyping();
  if(r.reply){addMessage("bot",r.reply);history.push({role:"assistant",content:r.reply});}
  (r.events||[]).forEach(eventLine);
  const mission=r.mission||{};
  executions+=(mission.results||[]).length;
  $("metricExec").textContent=executions;
 }catch(err){
  removeTyping();
  addMessage("bot","Não consegui concluir esta etapa: "+err.message);
  eventLine({type:"verification",text:"A execução foi interrompida e não foi declarada como concluída."});
 }finally{$("send").disabled=false;input.focus();}
}
form.onsubmit=e=>{e.preventDefault();const text=input.value.trim();if(!text)return;input.value="";input.style.height="auto";sendText(text);};
input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
input.addEventListener("input",()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,180)+"px";});
document.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{input.value=b.dataset.prompt;input.focus();});
refresh();setInterval(refresh,5000);
