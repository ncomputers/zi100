// Purpose: Provide webcam modal with face capture and upload
(function(){
// Modal controller for webcam capture
class CameraModal{
  constructor(id){
    this.modal=document.getElementById(id);
    this.video=this.modal.querySelector('video');
    this.canvas=this.modal.querySelector('canvas');
    this.ctx=this.canvas.getContext('2d');
    this.useBtn=this.modal.querySelector('.use-photo');
    this.upload=this.modal.querySelector('.cm-upload');
    if(!this.upload){
      this.upload=document.createElement('input');
      this.upload.type='file';
      this.upload.accept='image/*';
      this.upload.className='form-control form-control-sm mt-2 cm-upload d-none';
      this.modal.querySelector('.modal-body')?.appendChild(this.upload);
    }
    this.upload.addEventListener('change',e=>this.handleUpload(e));
    this.useBtn.disabled=true;
    this.stream=null;this.ws=null;this.boxes=[];
    this.useBtn.addEventListener('click',()=>this.capture());
    this.modal.addEventListener('shown.bs.modal',()=>this.start());
    this.modal.addEventListener('hidden.bs.modal',()=>this.stop());
  }
  // Begin webcam stream and websocket for face boxes
  async start(){
    try{
      if(!navigator.mediaDevices?.getUserMedia) throw new Error('unsupported');
      this.stream=await navigator.mediaDevices.getUserMedia({video:true});
      this.video.srcObject=this.stream;this.video.play();
      this.useBtn.disabled=false;
      this.ws=new WebSocket(`ws://${location.host}/ws/faceboxes`);
      this.ws.onmessage=e=>{try{this.boxes=JSON.parse(e.data);}catch(_){this.boxes=[];}};
      this.draw();
    }catch(_){
      alert('Camera access denied or not supported. Please upload an image instead.');
      this.useBtn.disabled=true;
      this.upload.classList.remove('d-none');
    }
  }
  // Halt streams and sockets
  stop(){
    if(this.ws){this.ws.close();this.ws=null;}
    if(this.stream){this.stream.getTracks().forEach(t=>t.stop());this.stream=null;}
    this.useBtn.disabled=true;
  }
  // Render video frame and detection boxes
  draw(){
    if(!this.stream)return;
    this.canvas.width=this.video.videoWidth||320;
    this.canvas.height=this.video.videoHeight||240;
    this.ctx.drawImage(this.video,0,0);
    this.ctx.strokeStyle='lime';
    this.ctx.lineWidth=2;
    for(const [x,y,w,h] of this.boxes){this.ctx.strokeRect(x,y,w,h);} 
    requestAnimationFrame(()=>this.draw());
  }
  // Capture current frame and send to server
  capture(){
    this.canvas.toBlob(async blob=>{
      const fd=new FormData();
      fd.append('image',blob,'face.jpg');
      fd.append('visitor_id',this.useBtn.dataset.visitorId||'');
      const r=await fetch('/api/faces/add',{method:'POST',body:fd});
      const d=await r.json();
      showToast(d.added?'Face added':d.error||'Error', d.added?'success':'danger');
    },'image/jpeg');
  }

  handleUpload(e){
    const file=e.target.files[0];
    if(!file) return;
    const fd=new FormData();
    fd.append('image',file,'face.jpg');
    fd.append('visitor_id',this.useBtn.dataset.visitorId||'');
    fetch('/api/faces/add',{method:'POST',body:fd})
      .then(r=>r.json())
      .then(d=>showToast(d.added?'Face added':d.error||'Error',d.added?'success':'danger'));
  }
}
window.CameraModal=CameraModal;
// Utility to display toast notifications
window.showToast=window.showToast||function(msg,type){
  let t=document.getElementById('mainToast');
  if(!t){
    t=document.createElement('div');
    t.id='mainToast';
    t.className='toast align-items-center text-bg-success border-0 position-fixed top-0 end-0 m-3';
    t.innerHTML='<div class="d-flex"><div class="toast-body"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    document.body.appendChild(t);
  }
  t.classList.remove('text-bg-danger','text-bg-success');
  t.classList.add(type==='success'?'text-bg-success':'text-bg-danger');
  t.querySelector('.toast-body').textContent=msg;
  bootstrap.Toast.getOrCreateInstance(t).show();
};
})();
