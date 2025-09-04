// Purpose: dashboard graph script
(function(){
async function load(){
  const sel=document.getElementById('timeframe');
  const tf=sel?sel.value:'7d';
  const cmp=document.getElementById('comparisonToggle');
  const compare=cmp&&cmp.checked?'1':'0';
  const errEl=document.getElementById('graphError');
  try{
    const r=await fetch(`/api/dashboard/stats?range=${encodeURIComponent(tf)}&compare=${compare}`);

    if(!r.ok){
      if(errEl) errEl.textContent='Failed to load data';
      return;
    }
    const d=await r.json();
    const payload=compare==='1'?d.current||d:d;
    if(!payload||!payload.timeline||payload.timeline.length===0){
      if(errEl) errEl.textContent='No data available';
      return;
    }
    if(errEl) errEl.textContent='';
    const tv=document.getElementById('kpi_total_visitors');
    if(tv) tv.textContent=d.total_visitors??0;
    const co=document.getElementById('kpi_current_occupancy');
    if(co) co.textContent=d.current??0;
    const vd=document.getElementById('kpi_vehicles_detected');
    if(vd) vd.textContent=d.vehicles_detected??0;
    const sv=document.getElementById('kpi_safety_violations');
    if(sv) sv.textContent=d.safety_violations??0;
    if(window.updateGraphCharts) window.updateGraphCharts(d,tf);
    const styles=getComputedStyle(document.documentElement);
    const safe=styles.getPropertyValue('--status-safe').trim()||'#2ecc71';
    const alert=styles.getPropertyValue('--status-alert').trim()||'#e74c3c';
    const status=d.status||(d.current&&d.max_capacity&&d.current/d.max_capacity>0.8?'alert':'safe');
    const color=status==='alert'?alert:safe;
    if(typeof donutChart!=='undefined'&&donutChart){
      donutChart.data.datasets[0].backgroundColor[0]=color;
      donutChart.update();
    }

  }catch(err){
    console.error('Failed to load dashboard stats',err);
    if(errEl) errEl.textContent='Error loading data';
  }
}
function refreshSnapshot(img,interval=15000){
  if(!img) return;
  const update=()=>{
    const base=img.src.split('?')[0];
    img.src=`${base}?t=${Date.now()}`;
  };
  setInterval(update,interval);
}
window.dashboardGraph={load,refreshSnapshot};
document.addEventListener('DOMContentLoaded',()=>{
  const sel=document.getElementById('timeframe');
  if(sel) sel.addEventListener('change',load);
  const cmp=document.getElementById('comparisonToggle');
  if(cmp) cmp.addEventListener('change',load);

});
})();
