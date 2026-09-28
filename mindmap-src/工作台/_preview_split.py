# -*- coding: utf-8 -*-
import json, io

KEYS = ['北京理工大学_810_2025','华中科技大学_832_2025','吉林大学_812_2025','清华大学_822_2025']
GROUPS = ['。；！？', '，：', '、']

def choose_cut(s):
    L = len(s)
    lo = max(1, L-45)
    hi = min(45, L-1)
    for g in GROUPS:
        c = [i for i in range(lo, hi+1) if s[i-1] in g]
        if c:
            return min(c, key=lambda i: abs(i - L/2.0))
    c = [i for i in range(lo, hi+1) if s[i-1] == ' ' or s[i] == ' ']
    if c:
        return min(c, key=lambda i: abs(i - L/2.0))
    return L // 2

out = io.open('_工作台/_preview_split.txt','w',encoding='utf-8')
for k in KEYS:
    d = json.load(open('思维导图_v6/%s.json'%k, encoding='utf-8'))
    out.write('===== %s =====\n'%k)
    for bi,b in enumerate(d['板块']):
        for ci,c in enumerate(b['考点']):
            inst = c.get('本卷实例') or {}
            for f in ('关键一步','中间结果','卡点'):
                for ii,s in enumerate(inst.get(f,[]) or []):
                    if len(s) > 45:
                        cut = choose_cut(s)
                        p1,p2 = s[:cut].strip(), s[cut:].strip()
                        out.write('BI=%d CI=%d %s %s idx=%d len=%d cut=%d spaces=%s\n'%(bi,ci,c['ref'],f,ii,len(s),cut,[i for i,ch in enumerate(s) if ch==' ']))
                        out.write('  P1(%d): %s\n'%(len(p1),p1))
                        out.write('  P2(%d): %s\n'%(len(p2),p2))
                        if len(p1)>45 or len(p2)>45 or not p1 or not p2:
                            out.write('  *** BAD ***\n')
out.close()
print('ok')
