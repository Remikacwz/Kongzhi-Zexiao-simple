"""§104/§124 科目定名：逐年优先 → 宝典全册兜底；并列取最近年。产出 _科目_全库定名.json + _待改_科目.json"""
import json,io,re,sys,contextlib,collections,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or '.')
import workbench as wb
B=chr(92); HERE=os.path.dirname(os.path.abspath(__file__))
S=json.load(io.open(os.path.join(HERE,'sources.json'),encoding='utf-8'))
AL=json.load(io.open(os.path.join(HERE,'重卷映射.json'),encoding='utf-8'))['别名到正卷']
_c={};_f={}
def _clean(v):
    v=re.split(r'注[:：]|①|②',v.strip())[0].strip(' ：:*#')
    return v if (2<=len(v)<=20 and not any(c in v for c in ':：,，。.')) else None
def name_of(k):
    if k in _c: return _c[k]
    b=io.StringIO()
    try:
        with contextlib.redirect_stdout(b): wb.cmd_brief(k,3000)
    except Exception: _c[k]=None; return None
    t=b.getvalue()
    m=(re.search(r'考试科目[:：][ \t]*([^\n]{2,30})',t)
       or re.search(r'科目名称[:：][ \t#*]*([^\n]{2,30})',t))
    _c[k]=_clean(m.group(1)) if m else None; return _c[k]
def bao_full(fp):
    if fp in _f: return _f[fp]
    try: t=io.open(fp.replace(B,'/'),encoding='utf-8',errors='replace').read()
    except Exception: _f[fp]=collections.Counter(); return _f[fp]
    c=collections.Counter()
    for m in re.finditer(r'(?:考试)?科目(?:名称)?[:：][ \t#*]*([^\n]{2,30})',t):
        v=_clean(m.group(1))
        if v: c[v]+=1
    _f[fp]=c; return c
def pick(ev):
    if not ev: return None
    cnt=collections.Counter(n for _,n in ev); top=max(cnt.values())
    cand=[n for n,c in cnt.items() if c==top]
    return cand[0] if len(cand)==1 else max(cand,key=lambda n:max(y for y,nn in ev if nn==n))
groups=collections.defaultdict(list)
for k in S:
    p=AL.get(k,k).rsplit('_',2); groups[(p[0],p[1])].append(k)
out={};mism=[]
for (school,code),ks in groups.items():
    zhu=[];bao=collections.Counter()
    for k in sorted(ks,key=lambda x:S[x]['年份']):
        n=name_of(k)
        if n and S[k]['源']=='逐年': zhu.append((S[k]['年份'],n))
        fp=S[k].get('宝典文件')
        if fp: bao+=bao_full(fp)
    bao_ev=[(9,n) for n,c in bao.items() for _ in range(c)]
    maj=pick(zhu) or pick(bao_ev); src='逐年' if zhu else ('宝典全册' if bao_ev else '无')
    out[f'{school}_{code}']={'定名':maj,'依据':src,'逐年条数':len(zhu),
        '逐年':collections.Counter(n for _,n in zhu).most_common(),'宝典全册':bao.most_common()}
    for k in ks:
        jp=os.path.join(os.path.dirname(HERE),'思维导图_v6',f'{k}.json')
        if not os.path.exists(jp) or not maj: continue
        try: cur=json.load(io.open(jp,encoding='utf-8')).get('科目')
        except Exception: continue
        if cur!=maj: mism.append({'key':k,'现值':cur,'应改':maj,'依据':src})
io.open(os.path.join(HERE,'_科目_全库定名.json'),'w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=1))
io.open(os.path.join(HERE,'_待改_科目.json'),'w',encoding='utf-8').write(json.dumps(mism,ensure_ascii=False,indent=1))
low=[k for k,v in out.items() if v['逐年条数']+sum(c for _,c in v['宝典全册'])<3]
print(f'定名完成：{len(out)} 组；不符 {len(mism)} 套；依据=逐年 {sum(1 for m in mism if m["依据"]=="逐年")} / 宝典全册 {sum(1 for m in mism if m["依据"]=="宝典全册")}')
print(f'仍属低样本(<3 条)的组：{len(low)} → {low}')
