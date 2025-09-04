// Purpose: initialize camera map and plot camera locations
(function(){
let map;
let initialized=false;
async function init(){
  if(initialized){
    setTimeout(()=>{map.invalidateSize();},0);
    return;
  }
  initialized=true;
  map=L.map('cameraMap').setView([0,0],2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,
    attribution:'&copy; OpenStreetMap contributors'
  }).addTo(map);
  try{
    const res=await fetch('/api/camera_info');
    if(!res.ok) return;
    const data=await res.json();
    (data.cameras||[]).forEach(c=>{
      if(typeof c.lat!=='number'||typeof c.lng!=='number') return;
      const online=c.stream_status==='online'||c.stream_status==='ok';
      const color=online?'green':'red';
      const marker=L.circleMarker([c.lat,c.lng],{radius:8,color}).addTo(map);
      marker.bindPopup(c.name||('Camera '+c.id));
    });
  }catch(err){
    console.error('Failed to load camera map',err);
  }
}
window.cameraMapInit=init;
})();
