// Controls module: attaches flight control handlers and sends commands
(function(){
  function appendLog(msg){
    const now = new Date().toLocaleTimeString();
    const logEl = document.getElementById('log');
    if(logEl){ logEl.textContent = `[${now}] ${msg}\n` + logEl.textContent; }
    console.log(msg);
  }

  async function sendDroneAction(action, params){
    appendLog('Drone action: ' + action + ' ' + JSON.stringify(params || {}));
    try{
      const res = await fetch('/drone/command', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, params})});
      const js = await res.json();
      appendLog('Drone response: ' + JSON.stringify(js));
      return js;
    }catch(err){ appendLog('Drone action failed: ' + err); return {ok:false, error: String(err)}; }
  }

  function bind(id, cb){
    const el = document.getElementById(id);
    if(el) el.addEventListener('click', cb);
  }

  // Wait for DOM ready
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init(){
    bind('btn_connect_controller', async ()=>{
      appendLog('Connecting controller...');
      try{
        const res = await fetch('/drone/connect_controller', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({})});
        const js = await res.json();
        appendLog('Controller connect: ' + JSON.stringify(js));
      }catch(err){ appendLog('Controller connect failed: ' + err); }
    });
    bind('btn_takeoff', ()=> sendDroneAction('send',{bytes: '6401'}));
    bind('btn_land', ()=> sendDroneAction('send',{bytes: '6402'}));
    bind('btn_up', ()=> sendDroneAction('send',{bytes: '6301'}));
    bind('btn_down', ()=> sendDroneAction('send',{bytes: '6302'}));
    bind('btn_left', ()=> sendDroneAction('send',{bytes: '6303'}));
    bind('btn_right', ()=> sendDroneAction('send',{bytes: '6304'}));
    bind('btn_cam1', ()=> sendDroneAction('switch_camera',{camera:1}));
    bind('btn_cam2', ()=> sendDroneAction('switch_camera',{camera:2}));
    bind('btn_start_video', ()=> sendDroneAction('start_video'));
    bind('btn_stop_video', ()=> sendDroneAction('stop_video'));
  }

})();
