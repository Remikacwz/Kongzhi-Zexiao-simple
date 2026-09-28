# -*- coding: utf-8 -*-
import json, io, sys

KEYS = ['北京理工大学_810_2025','华中科技大学_832_2025','吉林大学_812_2025','清华大学_822_2025']
out = io.open('_工作台/_比对结果.txt','w',encoding='utf-8')

def walk(a,b,path,acc):
    if type(a)!=type(b):
        acc.append('TYPE '+path); return
    if isinstance(a,dict):
        for k in set(a)|set(b):
            if k not in a or k not in b:
                acc.append('KEY '+path+'/'+str(k))
            else:
                walk(a[k],b[k],path+'/'+str(k),acc)
    elif isinstance(a,list):
        if len(a)!=len(b):
            acc.append('LEN '+path+' %d -> %d'%(len(a),len(b)))
        for i,(x,y) in enumerate(zip(a,b)):
            walk(x,y,path+'[%d]'%i,acc)
    elif a!=b:
        acc.append('VAL '+path+' | '+repr(a)[:60]+' -> '+repr(b)[:60])

for k in KEYS:
    o = json.load(open('_工作台/_bak_压缩_%s.json'%k, encoding='utf-8'))
    n = json.load(open('思维导图_v6/%s.json'%k, encoding='utf-8'))
    acc = []
    walk(o,n,'',acc)
    out.write('===== %s : %d 处解析差异 =====\n'%(k,len(acc)))
    for line in acc:
        out.write(line+'\n')
    out.write('\n')
out.close()
print('ok')
