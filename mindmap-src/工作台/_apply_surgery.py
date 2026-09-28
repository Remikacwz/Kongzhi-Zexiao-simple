# -*- coding: utf-8 -*-
import json, os, sys

BASE = r'E:\真题思维导图\_索引'
V6 = os.path.join(BASE, '思维导图_v6')
BAK = os.path.join(BASE, '_工作台')

src = open(os.path.join(BAK, '_compress_inst.py'), encoding='utf-8').read()
ns = {}
exec(src.split('FORBID =')[0], ns)
REPL = ns['REPL']

def apply_key(key):
    path = os.path.join(V6, key+'.json')
    bak = os.path.join(BAK, '_bak_压缩_'+key+'.json')
    with open(bak, 'rb') as f: raw = f.read()
    text = raw.decode('utf-8')
    nl = '\r\n' if '\r\n' in text else '\n'
    od = json.loads(text)  # 原始对象（用原始下标取旧文本）
    changes = []
    for (bi, ci, fld, idx, items) in REPL[key]:
        old = od['板块'][bi]['考点'][ci]['本卷实例'][fld][idx]
        assert len(old) > 45, (key, old)
        changes.append((old, items, (bi, ci, fld, idx)))
    # 按旧串长度降序处理（互不包含，顺序其实无关）
    for old, items, loc in sorted(changes, key=lambda x: -len(x[0])):
        lit = json.dumps(old, ensure_ascii=False)
        cnt = text.count(lit)
        assert cnt == 1, (key, 'old literal count', cnt, old)
        pos = text.find(lit)
        ls = text.rfind(nl, 0, pos) + len(nl)
        indent = text[ls:pos]
        after = text[pos+len(lit):pos+len(lit)+2]
        if after.startswith(']'):
            sep = ', '
        else:
            assert after[0] in (',', '\n', '\r'), (key, repr(after))
            assert indent.strip() == '', (key, 'indent not spaces', repr(indent))
            sep = ',' + nl + indent
        repl = sep.join(json.dumps(s, ensure_ascii=False) for s in items)
        text = text[:pos] + repl + text[pos+len(lit):]
    nd = json.loads(text)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    return changes

if __name__ == '__main__':
    for key in REPL:
        ch = apply_key(key)
        print(f'[ok] {key}: {len(ch)} 处')
    print('ALL DONE')
