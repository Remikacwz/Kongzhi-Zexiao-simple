# -*- coding: utf-8 -*-
import json, importlib.util, os, sys

spec = importlib.util.spec_from_file_location("fixmod", r"_工作台/_fix_超长_5套.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
FIX = m.FIX

def diffs(a,b,path=''):
    out=[]
    if type(a)!=type(b): out.append(('TYPE',path)); return out
    if isinstance(a,dict):
        for k in a.keys()|b.keys():
            if k not in a or k not in b: out.append(('KEY',path+'/'+str(k)))
            else: out += diffs(a[k],b[k],path+'/'+str(k))
    elif isinstance(a,list):
        if len(a)!=len(b): out.append(('LEN',path))
        for i,(x,y) in enumerate(zip(a,b)): out += diffs(x,y,path+f'[{i}]')
    elif a!=b: out.append(('VAL',path))
    return out

allok=True
for key, fixes in FIX.items():
    o=json.load(open(r'_工作台/_bak_压缩_%s.json'%key,encoding='utf-8'))
    n=json.load(open(r'思维导图_v6/%s.json'%key,encoding='utf-8'))
    exp=set()
    arrays=set()
    for (bi,ci,field,ii,old,new) in fixes:
        base='/板块[%d]/考点[%d]/本卷实例/%s'%(bi,ci,field)
        exp.add(('VAL',base+'[%d]'%ii))
        arrays.add(base)
    for base in arrays:
        exp.add(('LEN',base))
    obs=set(diffs(o,n))
    extra=obs-exp
    missing=exp-obs
    print("== %s expected=%d observed=%d"%(key,len(exp),len(obs)))
    if extra: print("  !! EXTRA(非目标路径):"); [print("    ",x) for x in sorted(extra)]
    if missing: print("  !! MISSING:"); [print("    ",x) for x in sorted(missing)]
    if extra or missing: allok=False
print("ALL_OK" if allok else "FAILED")
