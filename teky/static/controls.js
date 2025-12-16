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
    // start polling controller status
    pollControllerStatus();
    setInterval(pollControllerStatus, 3000);

    async function pollControllerStatus(){
      try{
        const res = await fetch('/drone/status');
        const js = await res.json();
        const nameEl = document.getElementById('controller_name');
        if(nameEl && js && js.status && js.status.controller_class){
          nameEl.textContent = js.status.controller_class;
        }
      }catch(e){ /* ignore */ }
    }

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
    // Camera switch with spinner and auto-restart handling
    const cam1 = document.getElementById('btn_cam1');
    const cam2 = document.getElementById('btn_cam2');
    const spinner = document.getElementById('camera_spinner');

    async function switchCameraWithSpinner(num){
      // disable buttons and show spinner
      if(cam1) cam1.disabled = true; if(cam2) cam2.disabled = true;
      if(spinner) spinner.style.display = 'block';
      const overlay = document.getElementById('video_overlay');
      if(overlay) overlay.style.display = 'flex';
      appendLog('Switching to camera ' + num + ' (waiting for stream restart)');
      try{
        const res = await sendDroneAction('switch_camera',{camera:num});
        // poll video_status until running or timeout
        const start = Date.now();
        const timeout = 10000; // 10s
        let ok = false;
        while(Date.now() - start < timeout){
          try{
            const r = await fetch('/video_status');
            const js = await r.json();
            if(js.running){ ok = true; break; }
          }catch(e){ /* ignore */ }
          await new Promise(res=>setTimeout(res, 500));
        }
        appendLog('Camera switch complete, stream ' + (ok ? 'running' : 'not running'));
      }catch(err){ appendLog('Camera switch failed: ' + err); }
        // hide spinner and re-enable
      if(spinner) spinner.style.display = 'none';
      if(overlay) overlay.style.display = 'none';
      if(cam1) cam1.disabled = false; if(cam2) cam2.disabled = false;
    }

    if(cam1) cam1.addEventListener('click', ()=> switchCameraWithSpinner(1));
    if(cam2) cam2.addEventListener('click', ()=> switchCameraWithSpinner(2));
    bind('btn_start_video', ()=> sendDroneAction('start_video'));
    bind('btn_stop_video', ()=> sendDroneAction('stop_video'));
  }

})();
