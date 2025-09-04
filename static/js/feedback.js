// Purpose: enterprise feedback submission logic
const form=document.getElementById('feedbackForm');
const resultBox=document.getElementById('feedbackResult');
const stepsContainer=document.getElementById('stepsContainer');
const addStepBtn=document.getElementById('addStep');
const attachmentsInput=document.getElementById('attachments');
const dropZone=document.getElementById('dropZone');
const attachmentList=document.getElementById('attachmentList');
const includeContext=document.getElementById('includeContext');
const contextField=document.getElementById('contextField');
const contextList=document.getElementById('contextList');
const recentList=document.getElementById('recentList');
const submitBtn=document.getElementById('submitBtn');
let attachments=[];let dirty=false;
function addStep(val=''){
  const i=stepsContainer.children.length+1;
  const div=document.createElement('div');
  div.className='input-group mb-2';
  div.innerHTML=`<span class="input-group-text">${i}</span><input type="text" class="form-control" name="steps" value="${val}">`;
  stepsContainer.appendChild(div);
}
addStep();
addStepBtn.addEventListener('click',()=>addStep());
function addAttachment(file){
  attachments.push(file);
  const item=document.createElement('div');
  item.className='d-flex align-items-center mb-1';
  item.dataset.name=file.name;
  item.innerHTML=`<span class="me-2">${file.name} (${Math.round(file.size/1024)} KB)</span><button type="button" class="btn-close" aria-label="Remove"></button>`;
  attachmentList.appendChild(item);
}
attachmentsInput.addEventListener('change',e=>{for(const f of e.target.files) addAttachment(f);attachmentsInput.value='';});
attachmentList.addEventListener('click',e=>{if(e.target.classList.contains('btn-close')){const name=e.target.parentElement.dataset.name;attachments=attachments.filter(f=>f.name!==name);e.target.parentElement.remove();}});
dropZone.addEventListener('click',()=>attachmentsInput.click());
dropZone.addEventListener('dragover',e=>{e.preventDefault();dropZone.classList.add('dragover');});
dropZone.addEventListener('dragleave',()=>dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop',e=>{e.preventDefault();dropZone.classList.remove('dragover');for(const f of e.dataTransfer.files) addAttachment(f);});
function populateContext(){
  const ctx={url:location.href,ua:navigator.userAgent,viewport:`${window.innerWidth}x${window.innerHeight}`,time:new Date().toISOString(),version:document.body.dataset.appVersion};
  contextField.value=JSON.stringify(ctx);
  contextList.innerHTML='';
  Object.entries(ctx).forEach(([k,v])=>{const li=document.createElement('li');li.className='list-group-item';li.textContent=`${k}: ${v}`;contextList.appendChild(li);});
}
populateContext();
includeContext.addEventListener('change',()=>{if(!includeContext.checked) contextField.value=''; else populateContext();});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
form.addEventListener('change',()=>dirty=true);
async function loadRecent(){
  try{const resp=await fetch('/feedback/recent');if(!resp.ok) return;const arr=await resp.json();arr.forEach(it=>{const li=document.createElement('li');li.className='list-group-item';li.textContent=`${it.id} - ${it.title||it.type}`;recentList.appendChild(li);});}catch{}
}
loadRecent();
form.addEventListener('submit',async e=>{
  e.preventDefault();dirty=false;
  const data=new FormData(form);
  if(!includeContext.checked) data.set('context','');
  attachments.forEach(f=>data.append('attachments',f));
  resultBox.classList.add('d-none');submitBtn.disabled=true;
  try{
    const resp=await fetch('/feedback',{method:'POST',body:data});
    if(!resp.ok) throw new Error();
    const json=await resp.json();
    resultBox.textContent=`Ticket ID: ${json.id}`;
    resultBox.className='alert alert-success';
    resultBox.classList.remove('d-none');
    form.reset();stepsContainer.innerHTML='';attachmentList.innerHTML='';attachments=[];addStep();
  }catch(err){
    resultBox.textContent='Submission failed. Please try again.';
    resultBox.className='alert alert-danger';
    resultBox.classList.remove('d-none');
  }finally{
    submitBtn.disabled=false;populateContext();
  }
});
