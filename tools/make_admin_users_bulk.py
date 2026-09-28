#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量为每所院校创建一个受限编辑账号。

规则:
  - 用户名按 wrjyNNN 三位递增（默认从 wrjy002 开始，自动跳过已存在的）
  - 每个账号只授权它对应的那一所院校（role=school_editor）
  - 密码 16 位强随机，生成后写入对照表 CSV

用法:
  python tools/make_admin_users_bulk.py                       # 给全部院校建号
  python tools/make_admin_users_bulk.py --schools "清华大学,山东大学"
  python tools/make_admin_users_bulk.py --db 数据库/admission.db --out 对照表.csv
  python tools/make_admin_users_bulk.py --start 200            # 从 wrjy200 开始编号

⚠️ 生成的 CSV 含明文密码，别提交到 git。
"""
import argparse
import csv
import importlib.util
import os
import pathlib
import re
import secrets
import sqlite3
import string
import sys
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = BASE / '数据库' / 'admission.db'
DEFAULT_OUT = BASE / '.qrcheck' / '后台账号密码.csv'
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_ca(db):
    os.environ['KAOYAN_SQLITE_PATH'] = str(pathlib.Path(db).resolve())
    if str(BASE / '数据库') not in sys.path:
        sys.path.insert(0, str(BASE / '数据库'))
    spec = importlib.util.spec_from_file_location('ca_bulk', BASE / '数据库' / 'content_admin.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['ca_bulk'] = mod
    spec.loader.exec_module(mod)
    return mod


def gen_password(n=16):
    return ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%^&*-_') for _ in range(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(DEFAULT_DB))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--schools', help='逗号分隔的院校名，默认全部院校')
    ap.add_argument('--start', type=int, default=2, help='起始编号，默认 2 → wrjy002')
    ap.add_argument('--dry-run', dest='dry', action='store_true', help='只预览不写库')
    a = ap.parse_args()

    conn = sqlite3.connect(a.db)
    conn.row_factory = sqlite3.Row
    if a.schools:
        want = [s.strip() for s in a.schools.replace('，', ',').split(',') if s.strip()]
        rows = []
        for n in want:
            r = conn.execute('SELECT id,name FROM schools WHERE name=?', (n,)).fetchone()
            if not r:
                raise SystemExit('库里没有院校: %s' % n)
            rows.append(r)
    else:
        rows = list(conn.execute('SELECT id,name FROM schools ORDER BY id'))

    # 已存在的 wrjyNNN 最大编号 → 自动接着编
    used = set()
    for r in conn.execute("SELECT username FROM admin_users WHERE username LIKE 'wrjy%'"):
        m = re.fullmatch(r'wrjy(\d+)', r[0] or '')
        if m:
            used.add(int(m.group(1)))
    num = a.start
    while num in used:
        num += 1

    # 已经有编辑账号的院校不重复建号
    done = {r[0] for r in conn.execute(
        "SELECT DISTINCT s.school_id FROM admin_user_schools s JOIN admin_users u ON u.id=s.user_id"
        " WHERE u.role='school_editor'")}
    todo = [r for r in rows if r['id'] not in done]
    skipped = len(rows) - len(todo)

    ca = load_ca(a.db)
    out = []
    print('待建 %d 个账号，编号从 wrjy%03d 开始%s%s' % (
        len(todo), num, '（dry-run 不写库）' if a.dry else '',
        ('；跳过 %d 所已有账号的院校' % skipped) if skipped else ''))
    for r in todo:
        while num in used:
            num += 1
        username = 'wrjy%03d' % num
        used.add(num)
        pwd = gen_password()
        if not a.dry:
            exists = conn.execute('SELECT 1 FROM admin_users WHERE username=?', (username,)).fetchone()
            if exists:
                out.append((num, r['name'], username, '(已存在，跳过)'))
                num += 1
                continue
            salt, digest = ca._hash_password(pwd)
            cur = conn.execute(
                'INSERT INTO admin_users(username,password_salt,password_hash,display_name,role,status,'
                'created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                (username, salt, digest, '%s 内容编辑' % r['name'], 'school_editor', 'active', NOW(), NOW()))
            conn.execute('INSERT OR IGNORE INTO admin_user_schools(user_id,school_id) VALUES(?,?)',
                         (cur.lastrowid, r['id']))
        out.append((num, r['name'], username, pwd))
        num += 1
    if not a.dry:
        conn.commit()

    outpath = pathlib.Path(a.out)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with outpath.open('w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh)
        w.writerow(['序号', '院校', '用户名', '密码'])
        for row in out:
            w.writerow(row)
    print('对照表已写入: %s' % outpath.resolve())
    print('')
    print('%-5s %-22s %-10s %s' % ('序号', '院校', '用户名', '密码'))
    for row in out:
        print('%-5s %-22s %-10s %s' % row)
    conn.close()


if __name__ == '__main__':
    main()
