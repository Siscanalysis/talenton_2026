from pathlib import Path
import re, json, html, hashlib, base64, sys
import numpy as np

ROOT = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
(OUT/'data').mkdir(exist_ok=True)
raw = (ROOT/'docs/gallery/index.html').read_text(encoding='utf-8')
decoder = json.JSONDecoder()
plots=[]
def plain(t): return html.unescape(re.sub('<[^>]+>', '', t)).strip()
for m in re.finditer(r'Plotly\.newPlot\(\s*"[^"\n]+"\s*,', raw):
    try:
        traces,end=decoder.raw_decode(raw,m.end()+len(raw[m.end():])-len(raw[m.end():].lstrip()))
        pos=end
        while raw[pos] in ' \r\n\t,': pos+=1
        layout,end=decoder.raw_decode(raw,pos)
        if not isinstance(traces,list): continue
        prefix=raw[:m.start()]
        h2=re.findall(r'<h2[^>]*>(.*?)</h2>',prefix,re.S)
        h3=re.findall(r'<h3[^>]*>(.*?)</h3>',prefix,re.S)
        plots.append({'section':plain(h2[-1]) if h2 else '', 'heading':plain(h3[-1]) if h3 else '', 'data':traces,'layout':layout})
    except (ValueError,IndexError): continue
(OUT/'data/gallery_plots.json').write_text(json.dumps(plots,indent=2),encoding='utf-8')
tables = [[plain(c) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',row,re.S)] for row in re.findall(r'<tr[^>]*>(.*?)</tr>',raw,re.S)]
(OUT/'data/gallery_tables.json').write_text(json.dumps(tables,indent=2),encoding='utf-8')
print('Extracted',len(plots),'plots;',len(tables),'table rows')
