const $=id=>document.getElementById(id);
const messages=$("messages"),stream=$("stream"),input=$("input"),form=$("chatForm");
let executions=0;
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function addMessage(role,text){
 const row=document.createElement("div");row.className="msg "+role;
 row.innerHTML=role==="user"?'<div class="avatar user-avatar">Y</div><div class="bubble"><p>'+esc(text)+'</p></div>':'<div class="avatar">S</div><div class="bubble">'+esc(text).replace(/\n/g,"<br>")+'</div>';
 messages.appendChild(row);messages.scrollTop=messages.scrollHeight;
}
function typing(){
 const row=document.createElement("div");row.id="typing";row.className="msg bot";
 row.innerHTML='<div class="avatar">S</div><div class="bubble typing"><i></i><i></i><i></i></div>';messages.appendChild(row);messages.scrollTop=messages.scrollHeight;
}
function removeTyping(){const t=$("typing");if(t)t.remove();}
function eventLine(e){
 if(stream.querySelector(".empty"))stream.innerHTML="";
 const el=document.createElement("div");el.className="event "+(e.type||"");
 let title=e.type==="execution"?e.skill:e.type==="verification"?"Verification":e.type==="plan"?"Plan":"Reasoning";
 el.innerHTML='<span class="event-icon">'+(e.type==="execution"?"✓":e.type==="plan"?"◆":"•")+'</span><div><b>'+esc(title)+'</b><small>'+esc(e.text||((e.status||"").toUpperCase())+(e.verified?" · verified":""))+'</small></div>';
 stream.prepend(el);
}
async function api(path,body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json();}
async function refresh(){
 try{const r=await fetch("/api/ai/status"),a=await r.json();$("aiModel").textContent=a.selected_model||a.model||"auto";$("aiState").textContent=a.configured?"Ready":"API key required";$("gateway").textContent=a.configured?"NVIDIA / ready":"NVIDIA / not configured";$("systemState").textContent=a.configured?"healthy":"needs key";$("sideStatus").textContent=a.configured?"Online":"Needs key";}catch(e){$("systemState").textContent="offline";}
 try{const r=await fetch("/api/snapshot"),d=await r.json();$("metricSkills").textContent=(d.skills||1500).toLocaleString();$("metricBrowser").textContent=(d.browser_events||[]).length;}catch(e){}
}
form.onsubmit=async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;addMessage("user",text);input.value="";input.style.height="auto";typing();$("send").disabled=true;
 try{const r=await api("/api/chat",{messages:[{role:"user",content:text}]});removeTyping();addMessage("bot",r.reply||"Não consegui obter uma resposta.");(r.events||[]).forEach(eventLine);executions+=(r.results||[]).length;$("metricExec").textContent=executions;}catch(err){removeTyping();addMessage("bot","Não consegui concluir esta etapa: "+err.message);eventLine({type:"verification",text:"A execução foi interrompida e não foi declarada como concluída."});}finally{$("send").disabled=false;input.focus();}};
input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
input.addEventListener("input",()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,180)+"px";});
document.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{input.value=b.dataset.prompt;input.focus();});
refresh();setInterval(refresh,5000);
