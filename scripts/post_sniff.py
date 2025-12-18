import urllib.request, json, sys

data = json.dumps({"duration":10, "dst":"192.168.1.1", "port":7099}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/sniff/run', data=data, headers={'Content-Type':'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(resp.read().decode())
except Exception as e:
    print('error', e)
    sys.exit(2)
