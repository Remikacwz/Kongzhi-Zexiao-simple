# -*- coding: utf-8 -*-
import json, sys
key = sys.argv[1]
o=json.load(open(r'_工作台/_bak_压缩_%s.json'%key,encoding='utf-8'))
n=json.load(open(r'思维导图_v6/%s.json'%key,encoding='utf-8'))
def walk(a,b,path=''):
    if type(a)!=type(b): print('TYPE',path); return
    if isinstance(a,dict):
        for k in set(a)|set(b):
            if k not in a or k not in b: print('KEY',path,k)
            else: walk(a[k],b[k],path+'/'+str(k))
    elif isinstance(a,list):
        if len(a)!=len(b): print('LEN',path,len(a),len(b))
        for i,(x,y) in enumerate(zip(a,b)): walk(x,y,path+f'[{i}]')
    elif a!=b: print('VAL',path,'|',str(a)[:45],'->',str(b)[:45])
walk(o,n)
