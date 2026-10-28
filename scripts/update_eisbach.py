"""Read publicly shown latest Eisbach water level from official GKD, HND fallback.
Never replace a valid measurement with a fabricated value.
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.request import Request, urlopen
from html import unescape
import re, json

GKD='https://www.gkd.bayern.de/de/fluesse/wasserstand/kelheim/muenchen-himmelreichbruecke-16515005/messwerte'
HND='https://www.hnd.bayern.de/pegel/donau_bis_kelheim/muenchen-himmelreichbruecke-16515005'
TZ=ZoneInfo('Europe/Berlin')

def get(url):
    req=Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; PassisWetter/1.1)', 'Accept':'text/html'})
    with urlopen(req,timeout=25) as r:
        return r.read().decode('utf-8','replace')

def parse_gkd(page):
    # Read the data table: date/time in the first column, water level in cm in second.
    rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>',page,re.I|re.S)
    readings=[]
    for row in rows:
        cols=re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',row,re.I|re.S)
        if len(cols)<2: continue
        plain=[unescape(re.sub(r'<[^>]+>',' ',c)).strip() for c in cols]
        date=re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})',plain[0])
        value=re.fullmatch(r'\s*(\d{1,4})(?:[,.]0+)?\s*',plain[1])
        if date and value:
            dt=datetime.strptime(date.group(1)+' '+date.group(2),'%d.%m.%Y %H:%M').replace(tzinfo=TZ)
            readings.append((dt,float(value.group(1))))
    # Some site versions expose accessible table text instead of table markup.
    if not readings:
        text=unescape(re.sub(r'<[^>]+>',' ',page))
        text=re.sub(r'\s+',' ',text)
        for m in re.finditer(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+Uhr\s+(\d{1,4})(?!\d)',text):
            dt=datetime.strptime(m.group(1)+' '+m.group(2),'%d.%m.%Y %H:%M').replace(tzinfo=TZ)
            readings.append((dt,float(m.group(3))))
    if not readings: raise ValueError('GKD Messwert-Tabelle nicht erkannt')
    return max(readings,key=lambda x:x[0])

def parse_hnd(page):
    text=unescape(re.sub(r'<[^>]+>',' ',page))
    text=re.sub(r'\s+',' ',text)
    m=re.search(r'Letzter Messwert vom\s*(\d{2}\.\d{2}\.\d{2,4})\s+(\d{2}:\d{2})\s*Uhr\s*:\s*(\d{1,4})\s*cm',text,re.I)
    if not m: raise ValueError('HND Letzter Messwert nicht erkannt')
    fmt='%d.%m.%y %H:%M' if len(m.group(1).split('.')[-1])==2 else '%d.%m.%Y %H:%M'
    return datetime.strptime(m.group(1)+' '+m.group(2),fmt).replace(tzinfo=TZ),float(m.group(3))

errors=[]
for url,parser in [(GKD,parse_gkd),(HND,parse_hnd)]:
    try:
        timestamp,level=parser(get(url))
        now=datetime.now(TZ)
        if timestamp>now+timedelta(minutes=30):raise ValueError('Messung liegt in der Zukunft')
        if timestamp<now-timedelta(hours=6):raise ValueError('Letzter amtlicher Messwert ist älter als sechs Stunden')
        result={'station':'München Himmelreichbrücke / Eisbach','water_level_cm':level,'discharge_m3s':None,'observed_at':timestamp.isoformat(),'observed_at_label':timestamp.strftime('%d.%m.%Y %H:%M'),'source':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
        dest=Path('data/eisbach.json');dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Erfolgreich:',result['water_level_cm'],'cm, Messung',result['observed_at_label'],'aus',url)
        break
    except Exception as e:
        errors.append(f'{url}: {e}')
else:
    raise RuntimeError('Kein aktueller GKD/HND Wert verfügbar: '+' | '.join(errors))
