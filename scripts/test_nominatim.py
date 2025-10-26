import requests

url='https://nominatim.openstreetmap.org/search'
params={'q':'4138 Main St','format':'json','limit':1}
headers={'User-Agent':'PoolParty/1.0 (contact:none)'}
try:
    r=requests.get(url,params=params,headers=headers,timeout=10)
    print('status',r.status_code)
    print(r.text[:1000])
except Exception as e:
    print('error',e)
