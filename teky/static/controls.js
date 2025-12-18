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
    // Note: FFmpeg-specific status polling removed after video_stream simplification

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
    // Sniffer controls
    bind('btn_start_sniff', async ()=>{
      const dst = document.getElementById('sniff_dst').value || undefined;
      const port = document.getElementById('sniff_port').value || undefined;
      const dur = parseInt(document.getElementById('sniff_dur').value || '20', 10);
      appendLog('Starting capture...');
      try{
        const res = await fetch('/sniff/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({dst:dst, port:port, duration:dur})});
        const js = await res.json();
        appendLog('Sniff start: ' + JSON.stringify(js));
        refreshSniffs();
      }catch(e){ appendLog('Sniff start failed: ' + e); }
    });

    bind('btn_refresh_sniffs', ()=> refreshSniffs());

    async function refreshSniffs(){
      try{
        const r = await fetch('/sniff/status');
        const js = await r.json();
        const list = document.getElementById('sniff_list');
        if(!list) return;
        list.innerHTML = '';
        if(js && js.jobs){
          for(const [jid, info] of Object.entries(js.jobs)){
            const div = document.createElement('div');
            const status = info.status || 'unknown';
            const hdr = document.createElement('div');
            hdr.style.fontWeight = '700';
            hdr.textContent = `${jid}: ${status} -> ${info.out || ''}`;

            // download link
            if(status === 'done'){
              const a = document.createElement('a'); a.href = `/sniff/download?job=${jid}`; a.textContent = ' download'; a.style.marginLeft='8px';
              hdr.appendChild(a);
            }

            div.appendChild(hdr);

            // show stdout/stderr if available
            const hasStdout = info.stdout && info.stdout.length > 0;
            const hasStderr = info.stderr && info.stderr.length > 0;
            if(hasStdout || hasStderr){
              const btn = document.createElement('button');
              btn.textContent = 'show logs';
              btn.style.marginLeft = '8px';
              btn.addEventListener('click', ()=>{
                const pre = div.querySelector('pre');
                if(pre){
                  if(pre.style.display === 'none'){
                    pre.style.display = 'block'; btn.textContent = 'hide logs';
                  } else { pre.style.display = 'none'; btn.textContent = 'show logs'; }
                }
              });
              hdr.appendChild(btn);

              const pre = document.createElement('pre');
              pre.style.display = 'none';
              pre.style.background = '#111';
              pre.style.color = '#eee';
              pre.style.padding = '8px';
              pre.style.whiteSpace = 'pre-wrap';
              pre.style.maxHeight = '200px';
              pre.style.overflow = 'auto';
              let outText = '';
              if(hasStdout) outText += `STDOUT:\n${info.stdout}\n\n`;
              if(hasStderr) outText += `STDERR:\n${info.stderr}\n`;
              pre.textContent = outText;
              div.appendChild(pre);
            }

            list.appendChild(div);
          }
        }
      }catch(e){ appendLog('Refresh sniffs failed: ' + e); }
    }
    // initial refresh
    refreshSniffs();
  }

})();
