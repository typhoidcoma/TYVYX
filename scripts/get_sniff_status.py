import urllib.request,json
print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:5000/sniff/status')), indent=2))
