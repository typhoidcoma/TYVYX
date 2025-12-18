import urllib.request, json, sys

data = json.dumps({'action': sys.argv[1] if len(sys.argv)>1 else 'start_video', 'params': {}}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/drone/command', data=data, headers={'Content-Type':'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(resp.read().decode())
except Exception as e:
    print('error', e)
    sys.exit(2)
