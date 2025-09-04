(() => {
 const key='visitorReportState';
 const defaults={type:'all',pending:false,tab:'pass',pass:{page:1,size:10},visitor:{page:1,size:10},host:{page:1,size:10}};
 let state;
 try{state={...defaults,...JSON.parse(localStorage.getItem(key)||'{}')}}catch{state={...defaults}};
 let picker;

 const save=()=>localStorage.setItem(key,JSON.stringify(state));
 const current=()=>state[state.tab];
 const debounce=(fn,ms)=>{let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),ms);};};
 const schedule=debounce(()=>{current().page=1;save();load();},250);
 const setLast7=()=>{const now=new Date();const start=new Date(now);start.setDate(start.getDate()-6);picker.setDate([start,now],true);};

 function load(){
  const sel=picker.selectedDates;
  if(sel.length<2){alert('Select date range');return;}
  const[sd,ed]=sel;const s=new Date(sd);s.setHours(0,0,0,0);const e=new Date(ed);e.setHours(23,59,59,999);
  const params=new URLSearchParams({from:s.toISOString(),to:e.toISOString(),type:state.type,pending:state.pending?'1':'0',tab:state.tab,page:current().page,page_size:current().size});
  const tbody=document.querySelector(`#${state.tab}Table tbody`);
  tbody.innerHTML=`<tr><td colspan="7" class="text-center"><div class="spinner-border" role="status"></div></td></tr>`;
  fetch('/api/visitor-report?'+params).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(d=>{
    const rows=d.rows||[],total=d.total||rows.length;
    render(rows);pager(total);
    document.getElementById('resultInfo').textContent=`${format(s)} to ${format(e)}`;
    document.getElementById('noRecords').classList.toggle('d-none',rows.length>0);
    document.getElementById('exportButtons').classList.toggle('d-none',rows.length===0);
    document.getElementById('exportCsv').href='/api/visitor-report/export?'+params;
  }).catch(()=>{alert('Failed to load report');tbody.innerHTML='';});
 }

 function render(rows){
  const tbody=document.querySelector(`#${state.tab}Table tbody`);
  tbody.innerHTML='';
  rows.forEach(r=>{
   const tr=document.createElement('tr');
   if(state.tab==='pass')tr.innerHTML=`<td>${r.gate_id||''}</td><td>${r.name||''}</td><td>${r.phone||''}</td><td>${r.host||''}</td><td>${r.type||''}</td><td>${r.purpose||''}</td><td>${r.time||''}</td>`;
   else if(state.tab==='visitor')tr.innerHTML=`<td>${r.name||''}</td><td>${r.phone||''}</td><td>${r.count||0}</td>`;
   else tr.innerHTML=`<td>${r.host||''}</td><td>${r.count||0}</td>`;
   tbody.appendChild(tr);
  });
 }

 function pager(total){
  const p=current(),pages=Math.max(1,Math.ceil(total/p.size));
  document.getElementById(`${state.tab}PageInfo`).textContent=`${p.page}/${pages}`;
  document.getElementById(`${state.tab}Prev`).disabled=p.page<=1;
  document.getElementById(`${state.tab}Next`).disabled=p.page>=pages;
 }

 const format=d=>d.toISOString().slice(0,10);
 function bindPag(id){
  document.getElementById(`${id}Prev`).addEventListener('click',()=>{if(state[id].page>1){state[id].page--;save();load();}});
  document.getElementById(`${id}Next`).addEventListener('click',()=>{state[id].page++;save();load();});
  document.getElementById(`${id}Rows`).addEventListener('change',e=>{state[id].size=parseInt(e.target.value,10);state[id].page=1;schedule();});
 }

 document.addEventListener('DOMContentLoaded',()=>{
  picker=flatpickr('#range',{mode:'range',dateFormat:'Y-m-d'});
  if(picker.selectedDates.length<2)setLast7();
  document.getElementById('vtype').value=state.type;
  document.getElementById('pending').checked=state.pending;
  ['pass','visitor','host'].forEach(id=>{document.getElementById(`${id}Rows`).value=state[id].size;bindPag(id);});
  new bootstrap.Tab(document.querySelector(`#${state.tab}-tab`)).show();
  document.getElementById('vtype').addEventListener('change',e=>{state.type=e.target.value;schedule();});
  document.getElementById('pending').addEventListener('change',e=>{state.pending=e.target.checked;schedule();});
  document.getElementById('loadReport').addEventListener('click',()=>{save();load();});
  document.querySelectorAll('#reportTabs button').forEach(btn=>btn.addEventListener('shown.bs.tab',ev=>{state.tab=ev.target.id.replace('-tab','');schedule();}));
  const resetBtn=document.getElementById('resetRange');
  if(resetBtn)resetBtn.addEventListener('click',()=>{setLast7();load();});
  const clearBtn=document.getElementById('clearFilters');
  if(clearBtn)clearBtn.addEventListener('click',()=>{
    picker.clear();
    state.type='all';
    state.pending=false;
    document.getElementById('vtype').value='all';
    document.getElementById('pending').checked=false;
    save();
  });
  load();
});
})();
