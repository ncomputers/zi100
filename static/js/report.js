// Purpose: report page script
Chart.register(ChartDataLabels, ChartZoom);
AOS.init();
const ctx=document.getElementById('reportChart').getContext('2d');
const chart=new Chart(ctx,{
    type:'line',
    data:{labels:[],datasets:[
        {label:'In',yAxisID:'y1',data:[],borderColor:'green',tension:0.2},
        {label:'Out',yAxisID:'y1',data:[],borderColor:'red',tension:0.2},
        {label:'Currently Inside',yAxisID:'y2',data:[],borderColor:'blue',tension:0.2}
    ]},
    options:{
        scales:{
            y1:{type:'linear',position:'left'},
            y2:{type:'linear',position:'right',grid:{drawOnChartArea:false}}
        }
    }
});

const plateEnabled = window.reportConfig?.plateEnabled;

const viewSelect=document.getElementById('view');
const graphBox=document.getElementById('graphBox');
const tableEl=document.getElementById('tbl');
const savedView=localStorage.getItem('report-view');
if(savedView){
  viewSelect.value=savedView;
}
function setView(v){
  if(v==='graph'){
    graphBox.style.display='block';
    tableEl.style.display='none';
  }else{
    graphBox.style.display='none';
    tableEl.style.display='table';
  }
}
setView(viewSelect.value);
viewSelect.addEventListener('change',()=>{
  localStorage.setItem('report-view',viewSelect.value);
  setView(viewSelect.value);
});

const spinner=document.getElementById('loadingSpinner');
const alertBox=document.getElementById('errorAlert');
const loadMoreBtn=document.getElementById('loadMoreBtn');
const cursorInput=document.getElementById('cursor');

async function fetchReport(append=false){
    // Retrieve and format the selected start/end dates from flatpickr
    const [start, end] = document.getElementById('range')._flatpickr.selectedDates;
    const startTime = flatpickr.formatDate(start, 'Y-m-d H:i');
    const endTime = end ? flatpickr.formatDate(end, 'Y-m-d H:i') : startTime;
    const type = document.getElementById('type').value;
    const view = document.getElementById('view').value;
    const rows = document.getElementById('rows').value;
    const camera = document.getElementById('camera').value;
    const label = document.getElementById('label').value;
    const cursor = cursorInput.value;
    const params = new URLSearchParams({start:startTime,end:endTime,type,view,rows,cam_id:camera,label,cursor});
    const url = `/report_data?${params.toString()}`;
    alertBox.classList.add('d-none');
    spinner.classList.remove('d-none');
    try{
        const r = await fetch(url);
        if(!r.ok) throw new Error('Network response was not ok');
        const d = await r.json();
        document.getElementById('exportLink').href = `/report/export?${params.toString()}`;
        if(view==='graph'){
            document.getElementById('graphBox').style.display='block';
            document.getElementById('tbl').style.display='none';
            loadMoreBtn.style.display='none';
            chart.data.labels=d.times;
            chart.data.datasets[0].data=d.ins;
            chart.data.datasets[1].data=d.outs;
            chart.data.datasets[2].data=d.current;
            chart.update();
        }else{
            document.getElementById('graphBox').style.display='none';
            const lbl=document.getElementById('labelHdr');
            if(lbl) lbl.textContent=type==='face'?'Face ID':'Label';
            const tbody=document.querySelector('#tbl tbody');
            if(!append) tbody.innerHTML='';
            d.rows.forEach(row=>{
                const tr=document.createElement('tr');
                const img=row.path?`<img src="${row.path}" width="80" alt="capture">`:'';
                let html=`<td>${row.time}</td><td>${row.cam_id}</td><td>${row.track_id}</td><td>${row.direction||''}</td><td>${row.label||''}</td><td>${img}</td>`;
                if(plateEnabled){
                    const plate=row.plate_path?`<img src="${row.plate_path}" width="80" alt="plate">`:'';
                    html+=`<td>${plate}</td>`;
                }
                tr.innerHTML=html;
                tr.setAttribute('data-aos','fade-up');
                tbody.appendChild(tr);
            });
            AOS.refresh();
            document.getElementById('tbl').style.display='table';
            if(d.next_cursor!==null && d.next_cursor!==undefined){
                cursorInput.value=d.next_cursor;
                loadMoreBtn.style.display='block';
            }else{
                loadMoreBtn.style.display='none';
                cursorInput.value=0;
            }
        }
    }catch(err){
        alertBox.textContent='Failed to load report data. Please try again later.';
        alertBox.classList.remove('d-none');
    }finally{
        spinner.classList.add('d-none');
    }
}

document.getElementById('rangeForm').addEventListener('submit',async e=>{
    e.preventDefault();
    cursorInput.value=0;
    await fetchReport(false);
});

loadMoreBtn.addEventListener('click',async ()=>{
    await fetchReport(true);
});

flatpickr('#range', {
    enableTime: true,
    dateFormat: 'Y-m-d H:i',
    mode: 'range'
});
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
document.getElementById('downloadChart').addEventListener('click',()=>{
  const a=document.createElement('a');
  a.href=chart.toBase64Image('image/png',1);
  a.download='report.png';
  a.click();
});

