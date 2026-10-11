"use strict";
const COLORS=["#f5a623","#3ec1d3","#b48ef7","#4cc38a","#ff8fb1","#9aa7b8"];
let S=null, PV=null, TAB="road_closure", SEG="last";
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=m=>m==null?"--:--":String(Math.floor(Math.round(m)/60)).padStart(2,"0")+":"+String(Math.round(m)%60).padStart(2,"0");
const col=(vid)=>COLORS[Object.keys(S.plan.vehicles).indexOf(vid)%COLORS.length];
async function api(p,body){const r=await fetch(p,body===undefined?{}:{method:"POST",body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j}
function say(t,c){$("msg").className="msg "+(c||"");$("msg").textContent=t||""}

async function load(){S=await api("/api/state");renderAll()}
function renderAll(){renderHeader();renderForms();renderMap();renderTimeline();renderCompare();renderSide();renderEvents();renderPreview();renderCharts();}
function renderHeader(){$("scn").textContent=S.scenario.name+" · "+S.scenario.vehicles.length+" vehicles · "+S.scenario.deliveries.length+" orders";
 $("clock").textContent="now "+fmt(S.plan.now);
 $("timeSlider").value=S.plan.now}

/* ---------------- forms ---------------- */
function locOpts(sel){return Object.keys(S.scenario.locations).map(l=>`<option ${l===sel?"selected":""}>${l}</option>`).join("")}
function renderForms(){
 [...$("tabs").children].forEach(b=>b.classList.toggle("on",b.dataset.t===TAB));
 const now=fmt(S.plan.now), locs=Object.keys(S.scenario.locations), vopts=S.scenario.vehicles.filter(v=>!S.plan.vehicles[v.id].failed).map(v=>`<option>${v.id}</option>`).join("");
 const F={
 road_closure:`<div class="row2"><div><label class="f">Location A</label><select id="f_a">${locOpts(locs[1])}</select></div><div><label class="f">Location B</label><select id="f_b">${locOpts(locs[2])}</select></div></div>
  <div class="row2"><div><label class="f">Closed from</label><input id="f_s" value="${now}"></div><div><label class="f">Until</label><input id="f_e" value="${fmt(S.plan.now+60)}"></div></div>
  <div class="row2"><div><label class="f">Extra minutes</label><input id="f_x" type="number" value="30"></div><div><label class="f">Multiplier</label><input id="f_m" type="number" step="0.1" value="1"></div></div>`,
 vehicle_breakdown:`<label class="f">Vehicle</label><select id="f_v">${vopts}</select><label class="f">Failure time</label><input id="f_t" value="${now}">`,
 urgent_order:`<div class="row2"><div><label class="f">Location</label><select id="f_l">${locOpts(locs[1])}</select></div><div><label class="f">Weight</label><input id="f_w" type="number" value="5"></div></div>
  <div class="row2"><div><label class="f">Window opens</label><input id="f_ws" value="${now}"></div><div><label class="f">Deadline</label><input id="f_we" value="${fmt(S.plan.now+90)}"></div></div>
  <div class="row2"><div><label class="f">Received at</label><input id="f_r" value="${now}"></div><div><label class="f">Service min</label><input id="f_sv" type="number" value="5"></div></div>`,
 text:`<label class="f">Free-text report (interpreted, then confirmed by you)</label><textarea id="f_txt" placeholder="The road between C1 and C2 will be closed from 10:00 to 10:30 adding 25 min"></textarea><div class="small">Also: "Vehicle V2 broke down at 09:30" · "Urgent order to C5, 12 kg, between 10:00 and 11:30, received at 09:45"</div>`};
 if($("forms").dataset.tab!==TAB){$("forms").innerHTML=F[TAB]+`<div style="margin-top:10px"><button class="pri" id="btnPrev">${TAB==="text"?"Interpret report":"Preview impact"}</button></div>`;$("forms").dataset.tab=TAB;$("btnPrev").onclick=preview}
}
$("tabs").onclick=e=>{if(e.target.dataset.t){TAB=e.target.dataset.t;$("forms").dataset.tab="";PV=null;say("");renderAll()}};
const v=id=>$(id).value;
async function preview(){
 say("Computing…");
 try{
  let r;
  if(TAB==="text") r=await api("/api/incident/text",{text:v("f_txt")});
  else{let b={type:TAB};
   if(TAB==="road_closure")b={...b,a:v("f_a"),b:v("f_b"),start:v("f_s"),end:v("f_e"),extra:+v("f_x"),factor:+v("f_m"),time:v("f_s")};
   if(TAB==="vehicle_breakdown")b={...b,vehicle_id:v("f_v"),time:v("f_t")};
   if(TAB==="urgent_order")b={...b,time:v("f_r"),delivery:{location:v("f_l"),weight:+v("f_w"),tw_start:v("f_ws"),tw_end:v("f_we"),service:+v("f_sv")}};
   r=await api("/api/incident/preview",b)}
  if(!r.ok){PV=null;say((r.errors||[r.message]).join(" · "),"err");renderAll();return}
  PV=r;say("");renderAll();
 }catch(e){say(e.message,"err")}
}
function renderPreview(){
 const b=$("previewBox");if(!PV){b.innerHTML="";return}
 const inc=PV.incident, s=PV.summary||{};
 b.innerHTML=`<div class="pv"><b>${PV.requires_confirmation?"Proposed interpretation — awaiting your confirmation":"Proposed change"}</b><div>${esc(inc.description)}</div>
 ${inc.assumptions&&inc.assumptions.length?`<ul>${inc.assumptions.map(a=>`<li>${esc(a)}</li>`).join("")}</ul>`:""}
 ${PV.accepted?`<div class="chips">${chips(s)}</div><div class="small">${(PV.log||[]).map(esc).join("<br>")}</div>
 <div class="small">Validation: ${PV.validation.valid?"✔ all checks passed":"✘ failed"} · strategy: ${PV.strategy}${PV.attempts.length>1?" (fallback used)":""}</div>
 <div class="small">The active plan is unchanged until you apply.</div>
 <div class="acts"><button class="ok" id="btnApply">${PV.requires_confirmation?"Confirm & apply":"Apply"}</button><button id="btnDisc">Discard</button></div>`
 :`<div class="msg err">${esc(PV.message)}</div><ul>${(PV.validation.errors||[]).slice(0,5).map(e=>`<li>${esc(e)}</li>`).join("")}</ul><div class="acts"><button id="btnDisc">Discard</button></div>`}</div>`;
 const a=$("btnApply");if(a)a.onclick=async()=>{try{S=await api("/api/incident/apply",{id:PV.id,confirm:true});PV=null;SEG="last";$("forms").dataset.tab="";renderAll()}catch(e){say(e.message,"err")}};
 $("btnDisc").onclick=async()=>{await api("/api/incident/cancel",{id:PV.id});PV=null;renderAll()};
}
const chips=s=>["kept","moved","broken","new"].filter(k=>s[k]||k!=="new").map(k=>`<span class="chip s-${k}">${k} ${s[k]||0}</span>`).join("");

/* ---------------- map ---------------- */
function viewPlan(){return PV&&PV.accepted?PV.revised:S.plan}
function renderMap(){
 const L=S.scenario.locations, P=viewPlan(), O=S.initial, W=640,H=420,pad=28;
 const xs=Object.values(L).map(l=>l.x),ys=Object.values(L).map(l=>l.y);
 const mx=Math.min(...xs),Mx=Math.max(...xs),my=Math.min(...ys),My=Math.max(...ys);
 const X=x=>pad+(x-mx)/(Mx-mx||1)*(W-2*pad),Y=y=>pad+(y-my)/(My-my||1)*(H-2*pad);
 const pt=n=>[X(L[n].x),Y(L[n].y)];
 const path=(veh)=>{const n=[S.scenario.depot];veh.history.forEach(r=>n.push(r.location));veh.rows.forEach(r=>n.push(r.location));
   if(!veh.failed)n.push(S.scenario.depot);return n.map(pt).map(p=>p.join(",")).join(" ")};
 let g="";
 S.scenario.closures.forEach(c=>{const a=pt(c.a),b=pt(c.b);g+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="var(--bad)" stroke-width="5" opacity=".35"/>`});
 if(PV&&PV.incident.type==="road_closure"){const d=PV.incident.data,a=pt(d.a),b=pt(d.b);g+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="var(--bad)" stroke-width="6" stroke-dasharray="6 4" opacity=".7"/>`}
 Object.entries(O.vehicles).forEach(([vid,veh])=>{g+=`<polyline points="${path(veh)}" fill="none" stroke="${col(vid)}" stroke-width="1.5" stroke-dasharray="3 5" opacity=".35"/>`});
 Object.entries(P.vehicles).forEach(([vid,veh])=>{g+=`<polyline points="${path(veh)}" fill="none" stroke="${col(vid)}" stroke-width="2.6" opacity=".9"/>`});
 const owner={};Object.entries(P.vehicles).forEach(([vid,vv])=>[...vv.history,...vv.rows].forEach(r=>{owner[r.stop_id]=vid}));
 const un=P.unassigned;
 S.scenario.deliveries.forEach(d=>{const [x,y]=pt(d.location);const c=un[d.id]?"var(--bad)":owner[d.id]?col(owner[d.id]):"var(--mu)";
   g+=`<circle cx="${x}" cy="${y}" r="${d.priority?8:6}" fill="var(--p)" stroke="${c}" stroke-width="2.4"/><text x="${x+9}" y="${y-7}" font-size="9.5" fill="var(--tx)">${d.id}</text>`});
 const [dx,dy]=pt(S.scenario.depot);g+=`<rect x="${dx-8}" y="${dy-8}" width="16" height="16" fill="var(--amb)"/><text x="${dx+11}" y="${dy+4}" font-size="10" fill="var(--amb)">DEPOT</text>`;
 Object.entries(P.vehicles).forEach(([vid,veh])=>{if(veh.failed){const [x,y]=pt(veh.failed.location);g+=`<text x="${x-6}" y="${y+6}" font-size="20" fill="var(--bad)">✖</text><text x="${x+9}" y="${y+18}" font-size="9.5" fill="var(--bad)">${vid} down ${fmt(veh.failed.time)}</text>`}});
 $("map").innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="100%">${g}</svg>`;
 $("legend").innerHTML=Object.keys(P.vehicles).map(x=>`<span><i style="background:${col(x)}"></i>${x}</span>`).join("")+`<span class="small">dashed = morning plan</span>`;
}

/* ---------------- timeline ---------------- */
function renderTimeline(){
 const P=viewPlan(),vs=Object.entries(P.vehicles);let t0=1e9,t1=0;
 vs.forEach(([_,vv])=>{[...vv.history,...vv.rows].forEach(r=>{t0=Math.min(t0,r.arrival-5);t1=Math.max(t1,r.depart+5)})});if(t0>t1){t0=480;t1=720}
 const W=900,lw=40,X=t=>lw+(t-t0)/(t1-t0)*(W-lw-10);let g="";
 for(let h=Math.ceil(t0/30)*30;h<=t1;h+=30)g+=`<line x1="${X(h)}" x2="${X(h)}" y1="14" y2="${vs.length*34+20}" stroke="var(--ln)"/><text x="${X(h)-14}" y="10" font-size="9" fill="var(--mu)">${fmt(h)}</text>`;
 vs.forEach(([vid,vv],i)=>{const y=22+i*34;g+=`<text x="0" y="${y+13}" font-size="11" fill="${col(vid)}">${vid}</text>`;
  [...vv.history.map(r=>({...r,h:1})),...vv.rows].forEach(r=>{
   if(r.wait>0.5)g+=`<rect x="${X(r.arrival)}" y="${y+4}" width="${Math.max(1,X(r.start)-X(r.arrival))}" height="10" fill="none" stroke="var(--mu)" stroke-dasharray="2 2"/>`;
   const fill=r.kind==="pickup"?"var(--bad)":col(vid);
   g+=`<rect x="${X(r.start)}" y="${y}" width="${Math.max(6,X(r.depart)-X(r.start))}" height="18" rx="3" fill="${fill}" opacity="${r.h?0.45:0.95}"><title>${r.stop_id} @${r.location} arr ${fmt(r.arrival)} wait ${Math.round(r.wait)}m start ${fmt(r.start)} load ${r.load_after}${r.tw_end?` deadline ${fmt(r.tw_end)}`:""}</title></rect><text x="${X(r.start)+2}" y="${y+13}" font-size="9" fill="#10151c">${r.kind==="pickup"?"PK":r.stop_id}</text>`});
  if(vv.failed)g+=`<text x="${X(vv.failed.time)-5}" y="${y+14}" fill="var(--bad)" font-size="14">✖</text>`});
 g+=`<line x1="${X(P.now)}" x2="${X(P.now)}" y1="14" y2="${vs.length*34+20}" stroke="var(--amb)" stroke-width="1.5"/>`;
 $("timeline").innerHTML=`<svg viewBox="0 0 ${W} ${vs.length*34+26}" width="100%">${g}</svg><div class="small">Faded = completed · dashed box = waiting for window · red PK = cargo pickup from a failed vehicle · amber line = now</div>`;
}

/* ---------------- comparison ---------------- */
$("segLast").onclick=()=>{SEG="last";renderCompare()};$("segOrig").onclick=()=>{SEG="orig";renderCompare()};
function renderCompare(){
 $("segLast").classList.toggle("on",SEG==="last");$("segOrig").classList.toggle("on",SEG==="orig");
 let rows=null,sum=null,title="";
 if(PV&&PV.accepted){rows=PV.comparison;sum=PV.summary;title="PROPOSED (not yet applied)"}
 else if(SEG==="orig"){rows=S.vs_original;title="morning plan → current"}
 else if(S.last_comparison){rows=S.last_comparison.rows;sum=S.last_comparison.summary;title=S.last_comparison.incident.description}
 if(!rows){$("chips").innerHTML=`<div class="small">No incident applied yet. Preview one from the console.</div>`;$("cmp").innerHTML="";return}
 if(!sum){sum={kept:0,moved:0,broken:0,new:0};rows.forEach(r=>sum[r.status]++)}
 $("chips").innerHTML=`<div class="small">${esc(title)}</div><div class="chips">${chips(sum)}</div>`;
 $("cmp").innerHTML=`<tr><th>Order</th><th>Window</th><th>Vehicle</th><th>ETA (service)</th><th>Arrive / wait</th><th>Status</th><th>Reason</th></tr>`+rows.map(r=>`<tr>
 <td class="m">${r.delivery}<div class="small">${r.location} · ${r.weight}</div></td><td class="m">${r.window}</td>
 <td class="m">${r.vehicle_before||"—"} → ${r.vehicle_after||"—"}</td>
 <td class="m">${fmt(r.eta_before)} → ${fmt(r.eta_after)}${r.eta_delta?`<div class="small">${r.eta_delta>0?"+":""}${Math.round(r.eta_delta)} min</div>`:""}</td>
 <td class="m">${r.arrival_after!=null?fmt(r.arrival_after)+" / "+Math.round(r.wait_after)+"m":"—"}</td>
 <td><span class="chip s-${r.status}">${r.status==="broken"?"broken · unfulfilled":r.status}</span><div class="small">${r.tag.replace(/_/g," ")}</div></td><td class="r">${esc(r.reason)}</td></tr>`).join("");
}

/* ---------------- side ---------------- */
function renderSide(){
 const V=PV&&PV.accepted?PV.validation:S.validation;
 $("valid").innerHTML=V.checks.map(c=>`<div class="chk ${c.passed?"pass":"fail"}"><i>${c.passed?"✔":"✘"}</i><div>${esc(c.name)}${c.details.map(d=>`<div class="small">${esc(d)}</div>`).join("")}</div></div>`).join("");
 const P=viewPlan(),m=P.metrics,o=S.initial.metrics;
 $("metrics").innerHTML=[["Orders",m.deliveries],["Completed",m.completed],["Pending (assigned)",m.pending_assigned],["Unfulfilled",m.unfulfilled],
  ["Total travel (min)",m.total_travel+` <span class="small">(morning ${o.total_travel})</span>`],["Total waiting (min)",m.total_wait]].map(([k,x])=>`<div class="kv"><span>${k}</span><span>${x}</span></div>`).join("");
 $("fleet").innerHTML=Object.entries(P.vehicles).map(([vid,vv])=>`<div style="margin-bottom:8px"><div class="kv" style="border:0"><span style="color:${col(vid)}">${vid}${vv.failed?" ✖ failed "+fmt(vv.failed.time):""}</span><span>cap ${vv.capacity}</span></div>
  <div class="bar"><div style="width:${m.peak_utilization_pct[vid]}%;background:${col(vid)}"></div></div><div class="small">peak load ${m.peak_utilization_pct[vid]}% · ${vv.history.length} done · ${vv.rows.length} pending</div></div>`).join("");
}
function renderEvents(){$("events").innerHTML=S.events.length?S.events.map(e=>`<div>${esc(e.incident.description)}<br>→ kept ${e.summary.kept} · moved ${e.summary.moved} · broken ${e.summary.broken}${e.summary.new?" · new "+e.summary.new:""}${e.strategy==="rebuild"?" · fallback":""}</div>`).join(""):"<div>No incidents yet.</div>"}

$("btnReset").onclick=async()=>{S=await api("/api/reset",{});PV=null;SEG="last";$("forms").dataset.tab="";renderAll()};
$("btnSave").onclick=async()=>{const n=prompt("Scenario name","my_scenario");if(n){await api("/api/scenario/save",{name:n});say("Saved to data/scenarios/"+n+".json","ok")}};
$("file").onchange=async e=>{try{S=await api("/api/scenario",JSON.parse(await e.target.files[0].text()));PV=null;$("forms").dataset.tab="";renderAll()}catch(x){say(x.message,"err")}};

$("btnAdvance").onclick=async()=>{
 try{
  const sliderVal=$("timeSlider").value;
  const minutes=parseFloat(sliderVal)-S.plan.now;
  if(minutes<=0){say("Time must be in the future","err");return}
  S=await api("/api/advance",{minutes});
  say(`Time advanced to ${fmt(S.plan.now)}`,"ok");
  renderAll();
 }catch(e){say(e.message,"err")}
};

$("btnUndo").onclick=async()=>{
 try{
  S=await api("/api/undo",{});
  say("Last incident undone","ok");
  PV=null;
  renderAll();
 }catch(e){say(e.message,"err")}
};

$("btnReport").onclick=async()=>{
 try{
  const r=await api("/api/report");
  const blob=new Blob([r.report],{type:"text/markdown"});
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");
  a.href=url;
  a.download="reroute_report.md";
  a.click();
  URL.revokeObjectURL(url);
  say("Report downloaded","ok");
 }catch(e){say(e.message,"err")}
};

$("timeSlider").oninput=()=>{
 $("clock").textContent="now "+fmt(S.plan.now)+" → "+fmt(parseFloat($("timeSlider").value));
};

// AI features
$("btnAskWhy").onclick=async()=>{
 try{
  const question=$("whyQuestion").value.trim();
  if(!question){say("Please enter a question","err");return}
  const r=await api("/api/ai/why",{question});
  $("aiAnswer").style.display="block";
  $("aiAnswer").innerHTML=`<b>AI Answer:</b><br>${esc(r.answer)}${r.sources&&r.sources.length?`<br><small>Sources: ${r.sources.join(", ")}</small>`:""}`;
 }catch(e){say(e.message,"err")}
};

$("btnGenMessages").onclick=async()=>{
 try{
  const comp=S.last_comparison||{rows:[]};
  const r=await api("/api/ai/messages",{comparison:comp});
  const msgs=r.messages||[];
  if(msgs.length===0){$("aiMessages").innerHTML="<div class='small'>No messages to generate.</div>";return}
  $("aiMessages").innerHTML=`<h3>Customer Messages (${msgs.length})</h3>`+msgs.map((m,i)=>`
   <div style="margin:8px 0;padding:8px;background:var(--p);border-radius:4px">
    <b>${m.delivery_id}</b> (${m.status})<br>
    <div style="margin:4px 0">${esc(m.message)}</div>
    <button class="ghost small" onclick="approveMessage(${i})">Approve & Send</button>
   </div>`).join("");
  window.pendingMessages=msgs;
 }catch(e){say(e.message,"err")}
};

$("btnShowAlerts").onclick=async()=>{
 try{
  const r=await api("/api/ai/alerts",{threshold_minutes:10});
  const alerts=r.alerts||[];
  if(alerts.length===0){$("aiAlerts").innerHTML="<div class='small'>No alerts - all deliveries on track!</div>";return}
  $("aiAlerts").innerHTML=`<h3>Predictive Alerts (${alerts.length})</h3>`+alerts.map(a=>`
   <div style="margin:8px 0;padding:8px;background:${a.severity==="critical"?"var(--bad)":"var(--warn)"};border-radius:4px;color:#fff">
    <b>${a.stop}</b> on ${a.vehicle}<br>
    <small>Arrives ${a.predicted_arrival}, deadline ${a.deadline} (${a.lateness_minutes}min late)</small><br>
    <small>${a.action}</small>
   </div>`).join("");
 }catch(e){say(e.message,"err")}
};

window.approveMessage=(i)=>{
 if(window.pendingMessages&&window.pendingMessages[i]){
  window.pendingMessages[i].approved=true;
  window.pendingMessages[i].sent=true;
  say(`Message for ${window.pendingMessages[i].delivery_id} approved (simulation - not actually sent)`,"ok");
  $("btnGenMessages").onclick();  // Refresh
 }
};


/* ---------------- Plotly charts ---------------- */
function renderCharts(){
 if(window.PlotlyFailed||!window.Plotly)return;
 if(!S||!S.plan)return;
 const P=viewPlan(),L=S.scenario.locations;
 
 // Chart 1: Route map
 const mapTraces=[];
 Object.entries(P.vehicles).forEach(([vid,veh])=>{
  const path=[S.scenario.depot];
  veh.history.forEach(r=>path.push(r.location));
  veh.rows.forEach(r=>path.push(r.location));
  if(!veh.failed)path.push(S.scenario.depot);
  const xs=path.map(n=>L[n].x),ys=path.map(n=>L[n].y);
  mapTraces.push({x:xs,y:ys,mode:'lines+markers',name:vid,line:{color:col(vid),width:2}});
 });
 const allLocs=Object.entries(L).map(([n,p])=>({name:n,x:p.x,y:p.y}));
 mapTraces.push({x:allLocs.map(l=>l.x),y:allLocs.map(l=>l.y),mode:'markers',name:'Locations',
  marker:{size:8,color:'#888'},text:allLocs.map(l=>l.name),hoverinfo:'text'});
 Plotly.newPlot('chartMap',mapTraces,{title:'Route Map',xaxis:{title:'X'},yaxis:{title:'Y'},showlegend:true,height:400},{displayModeBar:false});
 
 // Chart 2: Gantt chart
 const ganttTraces=[];
 Object.entries(P.vehicles).forEach(([vid,veh])=>{
  [...veh.history,...veh.rows].forEach(r=>{
   ganttTraces.push({
    x:[r.depart-r.arrival],y:[vid],base:[r.arrival],
    type:'bar',orientation:'h',name:r.stop_id||'stop',
    marker:{color:col(vid)},showlegend:false,hovertext:`${r.stop_id} ${r.location}`,
    text:r.stop_id,textposition:'inside'
   });
  });
 });
 Plotly.newPlot('chartGantt',ganttTraces,{title:'Gantt Timeline',xaxis:{title:'Time (minutes)'},yaxis:{title:'Vehicle'},barmode:'stack',height:300},{displayModeBar:false});
 
 // Chart 3: Utilization
 const m=P.metrics;
 const vids=Object.keys(P.vehicles);
 const utils=vids.map(vid=>m.peak_utilization_pct[vid]||0);
 Plotly.newPlot('chartUtil',[{x:vids,y:utils,type:'bar',marker:{color:vids.map(vid=>col(vid))}}],
  {title:'Vehicle Utilization',xaxis:{title:'Vehicle'},yaxis:{title:'Peak Load %'},showlegend:false,height:300},{displayModeBar:false});
}

load().catch(e=>say(e.message,"err"));
