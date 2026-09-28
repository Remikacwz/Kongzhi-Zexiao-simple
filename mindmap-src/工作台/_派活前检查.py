# -*- coding: utf-8 -*-
"""派活前逐 key 检查：只有「真的还没产物」或「有产物但 verify 不过」的 key 才可派。
用法: py -3.12 _工作台/_派活前检查.py 院校_代码_年份 [更多 key...]
退出码 0 = 全部可派；非 0 = 有 key 不该派（已在输出中列出原因）。
禁止把「在 _在制.txt 里」当成「没产物」——那是两回事（§155）。"""
import io, os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)

def main():
    keys = sys.argv[1:]
    if not keys:
        print('用法: _派活前检查.py <key> [key...]'); return 2
    src = json.load(io.open(os.path.join(HERE,'sources.json'), encoding='utf-8'))
    alias = set(json.load(io.open(os.path.join(HERE,'重卷映射.json'), encoding='utf-8'))['别名到正卷'])
    bad = []
    for k in keys:
        why = []
        if k not in src: why.append('sources.json 里不存在（禁止派）')
        elif k in alias: why.append('是别名、不生产（禁止派）')
        if why:
            print('%s %s  —— %s' % ('✘', k, '；'.join(why))); bad.append(k); continue
        j = os.path.join(ROOT,'思维导图_v6', k + '.json')
        if os.path.exists(j):
            r = subprocess.run([sys.executable, os.path.join(ROOT,'verify.py'), k],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            if r.stdout.strip().startswith('✓'): why.append('已交付且 verify 通过（不必派，白捡）')
            else: why.append('半成品：有 JSON 但 verify 不过（可派，或先试自己 render）')
        else:
            why.append('OK 可派（无产物）')
        flag = '✔' if why == ['OK 可派（无产物）'] else '✘'
        if flag == '✘' and '半成品' not in why[0]: bad.append(k)
        print('%s %s  —— %s' % (flag, k, '；'.join(why)))
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main())
