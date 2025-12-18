import urllib.request,json
req = urllib.request.Request('http://127.0.0.1:5000/drone/connect_controller', data=b'{}', headers={'Content-Type':'application/json'})
try:
    print(urllib.request.urlopen(req, timeout=5).read().decode())
except Exception as e:
    print('error', e)
