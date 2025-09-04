// Purpose: vms dashboard script
(function(){
const cssVar=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const shade=(c,p)=>{
  let num=parseInt(c.slice(1),16),amt=Math.round(2.55*p),R=(num>>16)+amt,G=(num>>8&0x00FF)+amt,B=(num&0x0000FF)+amt;
  return'#'+(0x1000000+(Math.max(0,Math.min(R,255))<<16)+(Math.max(0,Math.min(G,255))<<8)+Math.max(0,Math.min(B,255))).toString(16).slice(1);
};
const kpis=[
  {id:'occ',label:'Current Occupancy',icon:'people-fill'},
  {id:'peak',label:'Visitor Peak Time',icon:'clock-fill',fmt:v=>v||'—'},
  {id:'inv',label:'Total Invites Sent',icon:'envelope-fill'},
  {id:'busy',label:'Busiest Day',icon:'calendar3',fmt:v=>v||'—'},
  {id:'avg',label:'Avg Visit Duration',icon:'hourglass',fmt:v=>v?('~'+v):'—'},
  {id:'ret',label:'Returning %',icon:'arrow-repeat',fmt:v=>v+'%'}
];
let dailyChart,employeeChart,visitorChart,autoTimer;

document.addEventListener('DOMContentLoaded',()=>{
  const wrap=document.getElementById('kpiWrap');
  wrap.innerHTML=kpis.map(k=>`<div class="col"><div class="card text-center py-3 h-100 position-relative" data-aos="fade-up">
      <div class="spinner-border loading position-absolute top-50 start-50 translate-middle d-none"></div>
      <i class="bi bi-${k.icon} fs-3 text-primary mb-1"></i>
      <div id="kpi-${k.id}" class="fs-2 fw-bold">0</div>
      <small class="text-muted">${k.label}</small></div></div>`).join('');
  new DataTable('#logTable',{searchable:true,fixedHeight:true,perPage:5});
  document.querySelectorAll('#logTable tbody tr').forEach(r=>r.setAttribute('data-aos','fade-up'));
  AOS.init();
  document.querySelectorAll('#sideMenu a.nav-link').forEach(l=>{if(l.getAttribute('href')===location.pathname)l.classList.add('active');});
  loadStats();
  document.getElementById('timeframe').addEventListener('change',loadStats);
  const auto=document.getElementById('autoRefresh');
  if(auto){
    auto.addEventListener('change',setAuto);
    setAuto();
  }
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'){clearInterval(autoTimer);}else setAuto();});
});

function setAuto(){
  const auto=document.getElementById('autoRefresh');
  clearInterval(autoTimer);
  if(auto&&auto.checked) autoTimer=setInterval(loadStats,30000);
}

async function loadStats(){
  const tf=document.getElementById('timeframe').value;
  document.querySelectorAll('.loading').forEach(el=>el.classList.remove('d-none'));
  const r=await fetch('/api/vms/stats?range='+encodeURIComponent(tf));
  document.querySelectorAll('.loading').forEach(el=>el.classList.add('d-none'));
  if(!r.ok) return;
  const d=await r.json();
  updateKPIs(d);
  buildCharts(d);
}

function updateKPIs(d){
  const map={occ:'occupancy',peak:'peak_hour',inv:'total_invites',busy:'busiest_day',avg:'avg_duration',ret:'returning_pct'};
  kpis.forEach(k=>{
    const val=d[map[k.id]];
    const el=document.getElementById('kpi-'+k.id);
    if(typeof val==='number'){
      const cu=new CountUp(el,val,{startVal:parseInt(el.textContent)||0});
      if(!cu.error) cu.start(); else el.textContent=val;
    }else el.textContent=k.fmt?k.fmt(val):val;
    if(typeof gsap!=='undefined'){
      gsap.fromTo(el,{scale:1},{scale:1.1,duration:0.3,yoyo:true,repeat:1,ease:'power1.out'});
    }
  });
}

function buildCharts(d){
  const primary=cssVar('--bs-primary');
  if(dailyChart) dailyChart.destroy();
  dailyChart=new Chart(document.getElementById('dailyChart'),{
    type:'line',
    data:{labels:d.visitor_daily.map(x=>x.date),datasets:[{label:'Visits',data:d.visitor_daily.map(x=>x.count),borderColor:primary,backgroundColor:primary+'33',tension:0.4,fill:true}]},
    options:{aspectRatio:2,scales:{y:{beginAtZero:true}}}
  });
  if(employeeChart) employeeChart.destroy();
  employeeChart=new Chart(document.getElementById('employeeChart'),{
    type:'bar',
    data:{labels:d.top_employees.map(x=>x.name),datasets:[{label:'Visitors',data:d.top_employees.map(x=>x.count),backgroundColor:cssVar('--bs-success'),borderRadius:4}]},
    options:{aspectRatio:2,indexAxis:'y',scales:{x:{beginAtZero:true}}}
  });
  if(d.top_visitors.length===0){
    document.getElementById('visitorChartWrap').innerHTML='<div class="text-muted text-center my-5">No data</div>';
    visitorChart=undefined;
  }else{
    document.getElementById('visitorChartWrap').innerHTML='<div class="spinner-border loading position-absolute top-50 start-50 translate-middle d-none"></div><canvas id="visitorChart"></canvas>';
    if(visitorChart) visitorChart.destroy();
    const base=primary.trim();
    const colors=[0,15,30,45,60].map(p=>shade(base,p));
    visitorChart=new Chart(document.getElementById('visitorChart'),{
      type:'doughnut',
      data:{labels:d.top_visitors.map(x=>x.name),datasets:[{data:d.top_visitors.map(x=>x.count),backgroundColor:colors}]},
      options:{aspectRatio:2,plugins:{legend:{position:'bottom'}},cutout:'60%'}
    });
  }
}
})();
