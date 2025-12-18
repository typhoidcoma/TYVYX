import urllib.request,json,sys
try:
    print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:5000/video_status')), indent=2))
except Exception as e:
    print('error', e); sys.exit(2)
