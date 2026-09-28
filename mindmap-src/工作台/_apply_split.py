# -*- coding: utf-8 -*-
import json, shutil, io

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

log = io.open('_工作台/_压缩日志.txt','w',encoding='utf-8')
total = 0
for k in KEYS:
    src = '思维导图_v6/%s.json' % k
    bak = '_工作台/_bak_压缩_%s.json' % k
    shutil.copyfile(src, bak)
    d = json.load(open(src, encoding='utf-8'))
    n = 0
    for bi,b in enumerate(d['板块']):
        for ci,c in enumerate(b['考点']):
            inst = c.get('本卷实例') or {}
            for f in ('关键一步','中间结果','卡点'):
                lst = inst.get(f)
                if not lst:
                    continue
                todo = [(i,s) for i,s in enumerate(lst) if len(s) > 45]
                for i,s in todo:
                    cut = choose_cut(s)
                    p1, p2 = s[:cut].strip(), s[cut:].strip()
                    assert p1 and p2 and len(p1) <= 45 and len(p2) <= 45, (k,s,p1,p2)
                    lst[i] = p1
                    lst.append(p2)
                    n += 1
                    log.write('%s | BI=%d CI=%d %s %s idx=%d %d->(%d+%d)\n  P1: %s\n  P2: %s\n' % (
                        k, bi, ci, c['ref'], f, i, len(s), len(p1), len(p2), p1, p2))
    json.dump(d, open(src, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    with open(src, 'a', encoding='utf-8') as fp:
        fp.write('\n')
    log.write('%s 共拆分 %d 条\n\n' % (k, n))
    total += n
log.write('合计拆分 %d 条\n' % total)
log.close()
print('total split =', total)
