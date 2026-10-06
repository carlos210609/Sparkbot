const $ = (id) => document.getElementById(id);
const key = sessionStorage.getItem("sparkbot_api_key") || prompt("SparkBot API key (leave blank only for explicitly enabled local development):") || "";
if (key) sessionStorage.setItem("sparkbot_api_key", key);
async function api(path, options={}) {
 const headers = Object.assign({"Content-Type":"application/json","Authorization":"Bearer "+key}, options.headers||{});
 const res = await fetch(path, Object.assign({}, options, {headers}));
 if (!res.ok) throw new Error(await res.text());
 return res.json();
}
async function refresh() {
 try {
  const health = await fetch("/health"); $("health").textContent = health.ok ? "● Online" : "● Offline"; $("health").className = "status ok";
  const data = await api("/api/snapshot"); const open = data.tasks.filter(t => !["COMPLETED","CANCELLED"].includes(t.status));
  $("goalCount").textContent = data.goals.filter(g => g.status === "ACTIVE").length; $("taskCount").textContent = open.length; $("priorityCount").textContent = open.filter(t => ["P0","P1"].includes(t.priority)).length;
  $("tasks").innerHTML = open.length ? open.map(t => '<div class="item '+t.priority.toLowerCase()+'"><strong>'+escapeHtml(t.title)+'</strong><div class="meta">'+t.priority+' · '+t.status+' · '+t.tool+'</div></div>').join("") : "<div class='meta'>No open tasks.</div>";
  $("activity").innerHTML = data.activity.length ? data.activity.map(a => '<div class="item"><strong>'+escapeHtml(a.message)+'</strong><div class="meta">'+a.event_type+' · '+a.created_at+'</div></div>').join("") : "<div class='meta'>No activity yet.</div>";
  const ai=data.ai||{}; $("aiProvider").textContent=(ai.provider||"—").toUpperCase(); $("aiModel").textContent=ai.model||"auto"; $("aiMode").textContent=ai.configured?"READY":"CONFIGURE"; $("aiStatus").textContent=ai.configured?"AI: "+(ai.provider||"nvidia")+" ready":"AI: add NVIDIA_API_KEY"; $("aiStatus").className="status "+(ai.configured?"ok":"");
  const events=data.browser_events||[]; $("browserCount").textContent=events.length; $("browserEvents").innerHTML=events.length ? events.map(e => '<div class="item"><strong>'+escapeHtml(e.action)+'</strong><div class="meta">'+escapeHtml(e.status)+' · '+escapeHtml(e.url||'no URL')+' · '+escapeHtml(e.created_at)+'</div></div>').join("") : "<div class='meta'>No browser actions observed.</div>";
 } catch(e) { $("health").textContent = "● Auth/config error"; $("health").className = "status error"; $("message").textContent = e.message; }
}
$("run").onclick = async () => { const command = $("command").value.trim(); if (!command) return; $("message").textContent = "Planning…"; try { const result = await api("/api/commands",{method:"POST",body:JSON.stringify({command})}); $("message").textContent = "Plan created: "+result.intent; $("command").value=""; await refresh(); } catch(e) { $("message").textContent=e.message; } };
$("refresh").onclick = refresh;
function escapeHtml(value){return String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
refresh();
setInterval(refresh, 2500);
