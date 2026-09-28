#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后台账号管理（操作本地库，改完随部署生效）。

用法:
  python tools/make_admin_user.py list
  python tools/make_admin_user.py add --username zhangsan --display 张三 --schools 清华大学,北京大学
  python tools/make_admin_user.py add --username lisi --display 李四 --password 'Pass123!' --schools all
  python tools/make_admin_user.py passwd  --username zhangsan [--password 新密码]
  python tools/make_admin_user.py schools --username zhangsan --schools 浙江大学
  python tools/make_admin_user.py disable|enable|remove --username zhangsan

说明:
  - 默认操作 数据库/admission.db，用 --db 可指定其它库
  - --schools 支持中/英文逗号分隔；填 all 表示全部院校；不传则不给任何授权
  - 不传 --password 会自动生成强随机密码并打印
  - role 固定 school_editor（受限角色：只能管理被授权院校的内容）
"""
import argparse, importlib.util, os, pathlib, secrets, sqlite3, string, sys
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = BASE / '数据库' / 'admission.db'
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_ca(db):
    os.environ['KAOYAN_SQLITE_PATH'] = str(pathlib.Path(db).resolve())
    if str(BASE / '数据库') not in sys.path:      # content_admin 内部会 import heat_rankings
        sys.path.insert(0, str(BASE / '数据库'))
    spec = importlib.util.spec_from_file_location('ca_local', BASE / '数据库' / 'content_admin.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['ca_local'] = mod
    spec.loader.exec_module(mod)
    return mod


def gen_password(n=16):
    return ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%^&*-_') for _ in range(n))


def names(raw):
    if raw is None:
        return None
    return [p.strip() for p in raw.replace('，', ',').split(',') if p.strip()]


def resolve(conn, raw):
    lst = names(raw)
    if lst is None:
        return None
    if lst == ['all']:
        return [r[0] for r in conn.execute('SELECT id FROM schools ORDER BY id')]
    ids, miss = [], []
    for n in lst:
        row = conn.execute('SELECT id FROM schools WHERE name=?', (n,)).fetchone()
        (ids.append(row[0]) if row else miss.append(n))
    if miss:
        lines = ['找不到院校: ' + '、'.join(miss)]
        for m in miss:
            cand = [r[0] for r in conn.execute('SELECT name FROM schools WHERE name LIKE ? LIMIT 6', ('%' + m + '%',))]
            lines.append('  %s 的相近候选: %s' % (m, '、'.join(cand) if cand else '(无)'))
        raise SystemExit('\n'.join(lines))
    return ids


def show(conn, row):
    ids = [r[0] for r in conn.execute('SELECT school_id FROM admin_user_schools WHERE user_id=?', (row['id'],))]
    total = conn.execute('SELECT COUNT(*) FROM schools').fetchone()[0]
    nm = [(conn.execute('SELECT name FROM schools WHERE id=?', (i,)).fetchone() or ['#%d' % i])[0] for i in ids]
    if row['role'] == 'super_admin':
        scope = '全部院校（超管）'
    elif not nm:
        scope = '未授权任何院校（登录后看不到内容）'
    elif len(ids) >= total:
        scope = '全部院校（%d 所）' % len(ids)
    else:
        scope = '%d 所: %s' % (len(nm), '、'.join(nm))
    print('  id=%-3s 用户名=%-16s 显示名=%-10s 角色=%-14s 状态=%-9s 授权=%s' % (
        row['id'], row['username'], row['display_name'], row['role'], row['status'], scope))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(DEFAULT_DB))
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    for c in ('add', 'passwd'):
        p = sub.add_parser(c)
        p.add_argument('--username', required=True)
        p.add_argument('--password')
        if c == 'add':
            p.add_argument('--display')
            p.add_argument('--schools')
    for c in ('schools', 'enable', 'disable', 'remove'):
        p = sub.add_parser(c)
        p.add_argument('--username', required=True)
        if c == 'schools':
            p.add_argument('--schools', required=True)
    a = ap.parse_args()
    if not pathlib.Path(a.db).exists():
        raise SystemExit('库文件不存在: %s' % a.db)
    conn = sqlite3.connect(a.db)
    conn.row_factory = sqlite3.Row
    get = lambda u: conn.execute('SELECT * FROM admin_users WHERE username=?', (u,)).fetchone()

    if a.cmd == 'list':
        rows = list(conn.execute('SELECT * FROM admin_users ORDER BY id'))
        print('账号数: %d' % len(rows))
        for r in rows:
            show(conn, r)
    elif a.cmd == 'add':
        if get(a.username):
            raise SystemExit('用户名已存在: %s' % a.username)
        ca = load_ca(a.db)
        pwd = a.password or gen_password()
        salt, digest = ca._hash_password(pwd)
        cur = conn.execute('INSERT INTO admin_users(username,password_salt,password_hash,display_name,role,status,'
                           'created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                           (a.username, salt, digest, a.display or a.username, 'school_editor', 'active', NOW(), NOW()))
        ids = resolve(conn, a.schools) or []
        conn.executemany('INSERT OR IGNORE INTO admin_user_schools(user_id,school_id) VALUES(?,?)',
                         [(cur.lastrowid, i) for i in ids])
        conn.commit()
        print('✅ 已创建账号')
        show(conn, get(a.username))
        print('\n  登录用户名: %s\n  登录密码:   %s' % (a.username, pwd))
        if not ids:
            print('\n  ⚠️ 未授权院校，登录后看不到内容，请用 schools 子命令补授权')
    elif a.cmd == 'passwd':
        r = get(a.username) or sys.exit('账号不存在: %s' % a.username)
        ca = load_ca(a.db)
        pwd = a.password or gen_password()
        salt, digest = ca._hash_password(pwd)
        conn.execute('UPDATE admin_users SET password_salt=?,password_hash=?,updated_at=? WHERE id=?',
                     (salt, digest, NOW(), r['id']))
        conn.commit()
        print('✅ 已重置密码  用户名: %s  新密码: %s' % (a.username, pwd))
    elif a.cmd == 'schools':
        r = get(a.username) or sys.exit('账号不存在: %s' % a.username)
        ids = resolve(conn, a.schools)
        conn.execute('DELETE FROM admin_user_schools WHERE user_id=?', (r['id'],))
        conn.executemany('INSERT OR IGNORE INTO admin_user_schools(user_id,school_id) VALUES(?,?)',
                         [(r['id'], i) for i in ids])
        conn.commit()
        print('✅ 已更新授权')
        show(conn, get(a.username))
    elif a.cmd in ('enable', 'disable'):
        r = get(a.username) or sys.exit('账号不存在: %s' % a.username)
        conn.execute('UPDATE admin_users SET status=? WHERE id=?',
                     ('active' if a.cmd == 'enable' else 'disabled', r['id']))
        conn.commit()
        print('✅ 状态已更新')
        show(conn, get(a.username))
    elif a.cmd == 'remove':
        r = get(a.username) or sys.exit('账号不存在: %s' % a.username)
        if r['role'] == 'super_admin':
            raise SystemExit('拒绝删除超级管理员: %s' % a.username)
        conn.execute('DELETE FROM admin_user_schools WHERE user_id=?', (r['id'],))
        conn.execute('DELETE FROM admin_users WHERE id=?', (r['id'],))
        conn.commit()
        print('✅ 已删除账号: %s' % a.username)
    conn.close()


if __name__ == '__main__':
    main()
