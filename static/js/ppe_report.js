// Purpose: PPE report page script
const loadingOverlay=document.getElementById('loadingOverlay');
const errorAlert=document.getElementById('errorAlert');

function showError(msg){
  errorAlert.querySelector('.alert-message').textContent=msg;
  errorAlert.classList.remove('d-none');
}

async function loadData(){
  loadingOverlay.classList.remove('d-none');
  errorAlert.classList.add('d-none');
  const range=document.getElementById('range').value.split(' to ');
  const s=range[0];
  const e=range[1]||range[0];
  const sel=document.getElementById('status');
  const st=[...sel.selectedOptions].map(o=>o.value);
  const mc=document.getElementById('minConf').value;
  const col=document.getElementById('color').value;
  try{
    const params=new URLSearchParams();
    params.append('start',s);
    params.append('end',e);
    st.forEach(v=>params.append('status',v));
    params.append('min_conf',mc);
    params.append('color',col);
    const r=await fetch(`/ppe_report_data?${params.toString()}`);
    if(!r.ok) throw new Error(`Request failed with status ${r.status}`);
    const d=await r.json();
    const body=document.querySelector('#logTable tbody');
    body.innerHTML='';
    if(d.rows.length===0){
      body.innerHTML='<tr><td colspan="7" class="text-center">No data found for the selected filters</td></tr>';
    }else{
      d.rows.forEach(row=>{
        const tr=document.createElement('tr');
        const img=row.image?`<a href="${row.image}" download><img src="${row.image}" width="80" alt="frame"></a>`:'';
        tr.innerHTML=`<td>${row.time}</td><td>${row.cam_id}</td><td>${row.track_id}</td><td>${row.status}</td><td>${row.conf.toFixed(2)}</td><td>${row.color||''}</td><td>${img}</td>`;
        body.appendChild(tr);
      });
    }
    const link=document.getElementById('exportLink');
    link.href=`/ppe_report/export?${params.toString()}`;
    if($.fn.DataTable.isDataTable('#logTable')){
      $('#logTable').DataTable().destroy();
    }
    if(d.rows.length>0){
      $('#logTable').DataTable();
    }
  }catch(err){
    showError(err.message);
  }finally{
    loadingOverlay.classList.add('d-none');
  }
}

document.getElementById('rangeForm').addEventListener('submit',e=>{e.preventDefault();loadData();});

document.getElementById('sendBtn').addEventListener('click',async()=>{
  const range=document.getElementById('range').value.split(' to ');
  const s=range[0];
  const e=range[1]||range[0];
  const sel=document.getElementById('status');
  const st=[...sel.selectedOptions].map(o=>o.value);
  const mc=document.getElementById('minConf').value;
  const col=document.getElementById('color').value;
  const email=document.getElementById('mailTo').value;
  loadingOverlay.classList.remove('d-none');
  errorAlert.classList.add('d-none');
  try{
    const params=new URLSearchParams();
    params.append('start',s);
    params.append('end',e);
    st.forEach(v=>params.append('status',v));
    params.append('min_conf',mc);
    params.append('color',col);
    params.append('to',email);
    const resp=await fetch(`/ppe_report/email?${params.toString()}`,{method:'POST'});
    if(!resp.ok) throw new Error(`Request failed with status ${resp.status}`);
    alert('Email sent');
  }catch(err){
    showError(err.message);
  }finally{
    loadingOverlay.classList.add('d-none');
  }
});

flatpickr('#range',{enableTime:true,dateFormat:'Y-m-d H:i',mode:'range'});
document.getElementById('quick').addEventListener('change',e=>{
  const fp=document.getElementById('range')._flatpickr;
  const now=new Date();
  if(e.target.value==='today'){
      const start=new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      fp.setDate([start, now]);
  }else if(e.target.value==='week'){
      const past=new Date(now.getTime()-7*24*3600*1000);
      fp.setDate([past,now]);
  }else if(e.target.value==='month'){
      const first=new Date(now.getFullYear(),now.getMonth(),1);
      fp.setDate([first,now]);
  }
});
const initialQuick=document.getElementById('quick').value;
if(initialQuick) document.getElementById('quick').dispatchEvent(new Event('change'));
let statusChoices;
function initStatusChoices(){
  if(statusChoices){statusChoices.destroy();}
  statusChoices=new Choices('#status',{
    removeItemButton:true,
    placeholder:true,
    placeholderValue:'Select Statuses',
    searchPlaceholderValue:'Type to filter...',
    searchEnabled:true
  });
}
document.addEventListener('DOMContentLoaded',initStatusChoices);
