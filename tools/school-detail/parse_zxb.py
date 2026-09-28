# -*- coding: utf-8 -*-
"""
解析《27考研择校宝典》Word 文档（控制类）为结构化 JSON。

用法：
  1. 先把 docx 文本抽取出来（见下），或直接改 TEXT 指向已抽取文本
  2. python parse_zxb.py

抽取文本（一次性，需要 99MB XML 解码）：
  python -c "
  import zipfile, re
  z = zipfile.ZipFile(r'桌面上docx路径')
  xml = z.read('word/document.xml').decode('utf-8', errors='replace')
  paras = []
  for p in re.findall(r'<w:p[ >].*?</w:p>', xml, flags=re.S):
      paras.append(''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p)))
  open(r'zxb_text.txt', 'w', encoding='utf-8').write('\\n'.join(paras))
  "

输出：zxb_parsed.json（每校一节：简介/学院/学科评估/专业/复试线/历年招生/录取分析）
"""

import re, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from major_parse import parse_major

TEXT = os.environ.get('ZXB_TEXT', r'C:\Users\51366\AppData\Local\Temp\zxb_text.txt')
OUT = os.environ.get('ZXB_OUT', r'C:\Users\51366\AppData\Local\Temp\zxb_parsed.json')

lines = [l.rstrip() for l in open(TEXT, encoding='utf-8').read().split('\n')]
N = len(lines)


def num(s):
    if s is None:
        return None
    s = str(s).replace('..', '.').replace('．', '.').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None


# ---------- 目录与章节定位 ----------
toc_start = next(i for i, l in enumerate(lines) if l.strip() == '目录')
toc_end = next(i for i in range(toc_start + 1, N) if lines[i].strip() == '27考研万人教育全程班详情')
school_names, school_tier = [], {}
tier = None
for i in range(toc_start + 1, toc_end):
    l = lines[i].strip()
    if l.startswith('一、985院校'):
        tier = '985'; continue
    if l.startswith('二、211院校'):
        tier = '211'; continue
    if l.startswith('三、普通院校'):
        tier = '双非'; continue
    if l.startswith(('27考研', '万人教育', '控制院校', '最新考情', '26考研', '《致')):
        continue
    m = re.match(r'^(.+?)(\d+)$', l)
    if m and tier:
        school_names.append(m.group(1))
        school_tier[m.group(1)] = tier

body985 = next(i for i in range(toc_end, N) if lines[i].strip() == '一、985院校')
sections = []
prev = body985 + 1
for name in school_names:
    for i in range(prev, min(prev + 3000, N)):
        if lines[i].strip() == name:
            sections.append((name, i))
            prev = i + 1
            break


def nxt(idx, stop):
    i = idx
    while i < stop and not lines[i].strip():
        i += 1
    return i


def find_sec(titles, from_i, end):
    for j in range(from_i, min(from_i + 400, end)):
        if lines[j].strip() in titles:
            return j
    return None


def find_sec_re(pattern, from_i, end):
    for j in range(from_i, min(from_i + 400, end)):
        if re.match(pattern, lines[j].strip()):
            return j
    return None


def is_yearish(s):
    """历年招生表的第一列：2022 / 2023考研 / 25考研 / 26考研（081100）控制科学与工程"""
    return bool(re.match(r'^(?:19|20)\d{2}(?:考研)?$', s)) or bool(re.match(r'^\d{2}考研', s))


def parse_analysis(t, end):
    """一段录取情况分析：进复试/录取/复录比/最高最低平均分/分数段（含各科均分）"""
    sec = {'标题': lines[t].strip(), '复试最高': None, '复试最低': None, '复试平均': None,
           '录取最高': None, '录取最低': None, '录取平均': None, '进复试': None, '录取': None, '复录比': None,
           '分数段': [], '政治均分': None, '英语均分': None, '数学均分': None, '专业课均分': None, '总分均分': None,
           '有复试人数列': True, '_layout': None}
    # 标题被换行拆成"…录取情况 / 分析"时拼接
    if sec['标题'].endswith('录取情况'):
        nxtline = next((lines[u].strip() for u in range(t + 1, min(t + 3, end)) if lines[u].strip()), '')
        if nxtline == '分析':
            sec['标题'] = sec['标题'] + '分析'
    # 标题被拆成"四、26考研XX学院" / "（081100）…录取情况分析"
    if '录取情况' not in sec['标题']:
        _t2 = next((lines[u].strip() for u in range(t + 1, min(t + 4, end)) if lines[u].strip()), '')
        # 仅当下一行是"续行"（不是另一个编号小节）时才拼接，避免把下一个小节标题粘进来
        if '录取情况' in _t2 and not re.match(r'^(?:\d+|[一二三四五六七八九十]+)、', _t2):
            sec['标题'] = sec['标题'] + _t2
    for u in range(t + 1, min(t + 130, end)):
        ll = lines[u].strip()
        if not ll:
            continue
        if re.match(r'^(?:\d+|[一二三四五六七八九十]+)、', ll):
            break
        # 转置格式：行标签 + 3 个值（最高/最低/平均）
        if ll == '进入复试人员初试成绩':
            vals = [lines[v].strip() for v in range(u + 1, min(u + 6, end))
                    if lines[v].strip() and not re.match(r'^[一二三四五六七八九十]+、', lines[v].strip())][:3]
            if len(vals) == 3:
                sec['复试最高'] = num(vals[0]); sec['复试最低'] = num(vals[1]); sec['复试平均'] = num(vals[2])
            continue
        if ll == '已录取人员初试成绩':
            vals = [lines[v].strip() for v in range(u + 1, min(u + 6, end))
                    if lines[v].strip() and not re.match(r'^[一二三四五六七八九十]+、', lines[v].strip())][:3]
            if len(vals) == 3:
                sec['录取最高'] = num(vals[0]); sec['录取最低'] = num(vals[1]); sec['录取平均'] = num(vals[2])
            continue
        g = re.search(r'进入复试人员初试成绩(最高|最低|平均)分[：:]?\s*([\d.]+)', ll)
        if g:
            sec[{'最高': '复试最高', '最低': '复试最低', '平均': '复试平均'}[g.group(1)]] = num(g.group(2))
        g = re.search(r'已录取人员初试成绩(最高|最低|平均)分[：:]?\s*([\d.]+)', ll)
        if g:
            sec[{'最高': '录取最高', '最低': '录取最低', '平均': '录取平均'}[g.group(1)]] = num(g.group(2))
        g = re.search(r'一志愿\s*(\d+)人\s*进复试', ll) or re.search(r'进入?复试(\d+)人', ll)
        if g:
            sec['进复试'] = int(g.group(1))
        g = re.search(r'(?:实际共?|拟)录取(\d+)人', ll)
        if g:
            sec['录取'] = int(g.group(1))
        g = re.search(r'复录比[为是]?\s*[：:]?\s*(?:\d+\s*[:：]\s*)?([\d.]+)', ll)
        if g:
            sec['复录比'] = num(g.group(1))
        # 列式转置表：标签行 + 值行（如沈阳工业大学）
        if ll == '学科' and re.match(r'^一志愿(?:拟)?录取人数$', lines[u + 1].strip()):
            # 转置表：标签列 + 值行；专业名可能被拆成多行，故向下找第一个纯数字行
            v = u + 2
            while v < end and not re.match(r'^\d+$', lines[v].strip()):
                v += 1
            row = [lines[v + k].strip() if v + k < end else '' for k in range(4)]
            if len(row) == 4 and re.match(r'^\d+$', row[0]):
                sec['录取'] = int(row[0])
                sec['录取最高'] = num(row[1]); sec['录取最低'] = num(row[2]); sec['录取平均'] = num(row[3])
            for w in range(u, min(u + 40, end)):
                if lines[w].strip() == '一志愿复试人数':
                    vv = w + 1
                    while vv < end and not re.match(r'^\d+$', lines[vv].strip()):
                        vv += 1
                    if vv < end:
                        sec['进复试'] = int(lines[vv].strip())
                    break
        if ll == '一志愿进复试人数' and lines[u + 1].strip() == '一志愿进复试最高分':
            v = u + 5
            while v < end and not lines[v].strip():
                v += 1
            row = [lines[v + k].strip() for k in range(4)]
            if len(row) >= 4 and re.match(r'^\d+$', row[0]):
                sec['进复试'] = int(row[0])
                sec['复试最高'] = num(row[1]); sec['复试最低'] = num(row[2]); sec['复试平均'] = num(row[3])
        # 个人分数列表："初试成绩分别为：386、382、357、339、330"
        g = re.search(r'初试成绩分别为[：:]\s*([\d、，\s]+)', ll)
        if g:
            vals = [num(x) for x in re.split(r'[、，,\s]+', g.group(1).strip()) if re.match(r'^\d', x)]
            if vals:
                sec['录取最高'] = max(vals); sec['录取最低'] = min(vals)
                sec['录取平均'] = round(sum(vals) / len(vals), 1)
        # 单个考生："初试总分282分"
        g = re.search(r'初试(?:成绩)?总分\s*(\d+)\s*分', ll)
        if g and sec['录取平均'] is None:
            sec['录取最高'] = sec['录取最低'] = sec['录取平均'] = num(g.group(1))
        if g and sec['复试平均'] is None and sec['录取'] == 0:
            sec['复试最高'] = sec['复试最低'] = sec['复试平均'] = num(g.group(1))
        # 散文式："一志愿选择01/02方向只有一人，该学生的初试成绩345，已被录取"
        g = re.search(r'初试成绩\s*(\d{3})\s*[，,]?\s*已被(?:拟)?录取', ll)
        if not g:
            _tail = next((lines[x].strip() for x in range(u + 1, min(u + 3, end)) if lines[x].strip()), '')
            if '已被' in _tail and '录取' in _tail:
                g = re.search(r'初试成绩\s*(\d{3})', ll)
        if g and sec['录取最高'] is None:
            _v = num(g.group(1))
            if _v and 100 <= _v <= 500:
                sec['录取最高'] = sec['录取最低'] = sec['录取平均'] = _v
                if sec['录取'] is None:
                    sec['录取'] = 1
        # 散文式："一志愿进复试1人，初试总分为：288分，已被拟录取，接收调剂。"
        g = re.search(r'一志愿进复试(\d+)人[，,].*?初试总分(?:为)?[：:]?\s*(\d+)\s*分', ll)
        if g:
            if sec['进复试'] is None: sec['进复试'] = int(g.group(1))
            if sec['录取'] is None: sec['录取'] = int(g.group(1))
            if sec['录取最高'] is None:
                sec['录取最高'] = sec['录取最低'] = sec['录取平均'] = num(g.group(2))
        # 散文式："一志愿进复试分别为254分、254分，初试总分均分为302.9分，已被拟录取。"
        g = re.search(r'进复试分别为([\d、，,\s]+?)分', ll)
        if g:
            _vs = [num(x) for x in re.split(r'[、，,\s]+', g.group(1)) if re.match(r'^\d', x)]
            if _vs:
                sec['进复试'] = len(_vs)
                sec['复试最高'] = max(_vs); sec['复试最低'] = min(_vs)
                sec['复试平均'] = round(sum(_vs) / len(_vs), 1)
        g = re.search(r'初试总分均分为\s*([\d.]+)\s*分', ll)
        if g and sec['录取平均'] is None:
            sec['录取平均'] = num(g.group(1))
        # 紧凑格式：一志愿进入复试14人，实际共录取7人，…初试成绩最高分431，最低分330，平均分380，复录比1:2
        if re.search(r'实际共?录取\d+人', ll) and '已录取人员' not in ll:
            g = re.search(r'最高分[：:]?\s*([\d.]+)', ll)
            if g:
                sec['录取最高'] = num(g.group(1))
            g = re.search(r'最低分[：:]?\s*([\d.]+)', ll)
            if g:
                sec['录取最低'] = num(g.group(1))
            g = re.search(r'平均分[：:]?\s*([\d.]+)', ll)
            if g:
                sec['录取平均'] = num(g.group(1))
            # 紧凑格式只有一组分数（进入复试/录取共用），复试与录取同步
            if sec['复试平均'] is None:
                sec['复试最高'] = sec['录取最高']
                sec['复试最低'] = sec['录取最低']
                sec['复试平均'] = sec['录取平均']
        if re.match(r'^(\d{3})-(\d{3})$', ll) or ll == '总计':
            cells = [ll]
            for v in range(u + 1, min(u + 11, end)):
                cc = lines[v].strip()
                if re.match(r'^\d+(\.\d+)?%?$', cc) or cc == '':
                    cells.append(cc)
                    if len(cells) >= 11:
                        break
                else:
                    break
            clean = [c for c in cells if c != '']
            if sec['_layout'] is None:
                # 以本段「分数段」表头为锚点判定列布局；不能用固定回溯窗口，
                # 否则表头前有较长分数描述时会错过表头，把 A 误判成 B 导致整列错位。
                hdr = next((v for v in range(u - 1, t, -1) if lines[v].strip() == '分数段'), None)
                head = ('\n'.join(lines[hdr:hdr + 14]) if hdr is not None else '\n'.join(lines[t:u]))
                sec['_layout'] = 'A' if ('复试人数' in head and '录取人数' in head) else 'B'
                sec['有复试人数列'] = (sec['_layout'] == 'A')
            if ll == '总计':
                # A: [总计, 复试, 录取, 百分比, 政治, 英语, 数学, 专业课, 总分均分, 备注]
                # B: [总计, 录取, 政治, 英语, 数学, 专业课, 总分均分, 备注]
                if sec['_layout'] == 'A' and len(clean) >= 9:
                    if re.match(r'^\d+$', clean[1]):
                        sec['进复试'] = int(clean[1])
                    if re.match(r'^\d+$', clean[2]):
                        sec['录取'] = int(clean[2])
                    sec['政治均分'] = num(clean[4]); sec['英语均分'] = num(clean[5])
                    sec['数学均分'] = num(clean[6]); sec['专业课均分'] = num(clean[7])
                    sec['总分均分'] = num(clean[8])
                elif sec['_layout'] == 'B' and len(clean) >= 7:
                    if re.match(r'^\d+$', clean[1]):
                        sec['录取'] = int(clean[1])
                    # B: [分数段, 录取, 政治, 英语, 数学, 专业课, 总分(, 备注)]
                    sec['政治均分'] = num(clean[2]); sec['英语均分'] = num(clean[3])
                    sec['数学均分'] = num(clean[4]); sec['专业课均分'] = num(clean[5])
                    sec['总分均分'] = num(clean[6]) if len(clean) >= 7 else None
            else:
                sec['分数段'].append(cells)
    # 分数段求和兜底（无"实际录取X人"总结、无总计行时）
    if sec['录取'] is None and sec['分数段']:
        aidx = 2 if sec.get('有复试人数列', True) else 1
        total = sum(int(r[aidx]) for r in sec['分数段'] if len(r) > aidx and re.match(r'^\d+$', r[aidx]))
        if total:
            sec['录取'] = total
    if sec['进复试'] is None and sec['分数段'] and sec.get('有复试人数列', True):
        total = sum(int(r[1]) for r in sec['分数段'] if len(r) > 1 and re.match(r'^\d+$', r[1]))
        if total:
            sec['进复试'] = total
    # 无总计行时，用分数段按人数加权计算各科均分（口径：各科均分来自进复试名单）
    if sec['专业课均分'] is None and sec['分数段']:
        layout = sec.get('_layout', 'A')
        # 该兜底只在表宽与布局口径吻合时才可用，否则会把总分/复试分错当各科均分
        # A: [分数段,复试,录取,录取率,政治,英语,数学,专业课,总分]  → 需 >=9 列
        # B: [分数段,录取,政治,英语,数学,专业课,总分]              → 需 >=7 列
        width = max((len(r) for r in sec['分数段']), default=0)
        if layout == 'A' and width >= 9:
            idx_score, idx_w = 4, 1
        elif layout == 'B' and width >= 7:
            idx_score, idx_w = 2, 1
        else:
            idx_score = None
        if idx_score is None:
            return sec

        def wavg(col):
            s = 0
            d = 0
            for r in sec['分数段']:
                if len(r) > col and re.match(r'^\d+(\.\d+)?$', r[col]):
                    w = int(r[idx_w]) if (len(r) > idx_w and re.match(r'^\d+$', r[idx_w]) and int(r[idx_w]) > 0) else 1
                    s += w * num(r[col])
                    d += w
            return round(s / d, 1) if d else None

        sec['政治均分'] = sec['政治均分'] or wavg(idx_score)
        sec['英语均分'] = sec['英语均分'] or wavg(idx_score + 1)
        sec['数学均分'] = sec['数学均分'] or wavg(idx_score + 2)
        sec['专业课均分'] = sec['专业课均分'] or wavg(idx_score + 3)
        sec['总分均分'] = sec['总分均分'] or wavg(idx_score + 4)
    # 单科均分合理区间收尾：docx 源数据存在把总分写成单科、用 0.0 占位、
    # 或列错位等情形，越界值一律清空，宁缺勿错。
    for _k, _lo, _hi in (('政治均分', 10, 100), ('英语均分', 10, 100),
                         ('数学均分', 10, 150), ('专业课均分', 10, 150),
                         ('总分均分', 100, 500)):
        _v = sec[_k]
        if _v is not None and not (_lo <= _v <= _hi):
            sec[_k] = None
    return sec


# ---- 复试线：合并列布局（学科 | 政治/英语 | 业务课一/二 | 总分 …） ----
_SCORE_LABELS = {
    '政治': ('政治',), '英语': ('英语',), '外语': ('英语',),
    '业务课一': ('业务课一',), '业务课二': ('业务课二',),
    '专业课一': ('业务课一',), '专业课二': ('业务课二',),
    '业务课一/二': ('业务课一', '业务课二'), '业务课二/一': ('业务课一', '业务课二'),
    '专业课一/二': ('业务课一', '业务课二'),
    '政治/英语': ('政治', '英语'), '政治/外语': ('政治', '英语'),
    '英语/政治': ('政治', '英语'), '外语/政治': ('政治', '英语'),
    '总分': ('总分',),
    '业务课三/四': (), '专业课三/四': (), '业务课三': (), '业务课四': (),
    '单科(满分=100分)': ('政治', '英语'), '单科(满分>100分)': ('业务课一', '业务课二'),
    '单科(满分=150分)': ('业务课一', '业务课二'),
    '单科(=100分)': ('政治', '英语'), '单科(>=100分)': ('业务课一', '业务课二'),
    '单科(>100分)': ('业务课一', '业务课二'), '单科(满分100分)': ('政治', '英语'),
}


def score_label(ss):
    """归一化后查列名（处理 &gt; 实体、全角括号、空格）。返回 None = 不是列名。"""
    x = re.sub(r'\s+', '', ss or '')
    x = x.replace('&gt;', '>').replace('&lt;', '<').replace('（', '(').replace('）', ')')
    return _SCORE_LABELS.get(x)


def is_score_label(ss):
    return score_label(ss) is not None
_BS = chr(92)
_COLLEGE_TAIL = re.compile(r'(?:学院|学部|研究院|研究所|研究生院|系|中心|实验室|校区|基地)$')


def is_score_val(s):
    """复试线表格里的"值"格：纯数字、百分比、空记号、未公示。"""
    if not s:
        return False
    core = s[:-1] if s.endswith('%') else s
    if core and core.replace('.', '', 1).isdigit():
        return True
    if re.fullmatch(r'\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?', core):
        return True
    if s in (_BS, '-', '--', '/', chr(65295), chr(8212), chr(8212) * 2):
        return True
    return any(x in s for x in ('未公示', '未公布', '未公开', '未知'))


def clean_score_val(v):
    """规范复试线单元格：官网未公示 / 未公布 / 未公开 统一为「官网未公示」。"""
    v = (v or '').strip()
    if any(x in v for x in ('未公示', '未公布', '未公开')):
        return '官网未公示'
    if '未知' in v:
        return '未知'
    return v


_RANGE = {'政治': (10, 100), '英语': (10, 100), '业务课一': (10, 150), '业务课二': (10, 150),
          '业务课三': (10, 150), '业务课四': (10, 150), '总分': (100, 500)}


def clamp_score(k, v):
    """docx 单元格粘连（如总分 2624 / 9402）→ 超出合理区间则留空。"""
    lo, hi = _RANGE.get(k, (0, 10 ** 6))
    c = (v or '').strip()
    if re.fullmatch(r'\d{1,5}', c):
        n = int(c)
        if n < lo or n > hi:
            return ''
    return v


def parse_scoreline_merged(sch, j, end):
    """4/5/6 列合并表头：学科 | 政治/外语 | 业务课一/二 | 总分 ……"""
    hdr = None
    for u in range(j + 1, min(j + 40, end)):
        if lines[u].strip() == '学科':
            hdr = u
            break
    if hdr is None:
        return
    labels = []
    u = hdr + 1
    while u < end and is_score_label(lines[u].strip()):
        labels.append(lines[u].strip())
        u += 1
    if not labels:
        return
    keys = [score_label(x) for x in labels]
    nvals = len(labels)
    cur_college = ''
    while u < end:
        while u < end and not lines[u].strip():
            u += 1
        if u >= end:
            break
        labs = []
        while u < end:
            s = lines[u].strip()
            if not s:
                u += 1
                continue
            if s == '总计' or is_score_val(s):
                break
            if re.match(r'^[一二三四五六七八九十\d]+、', s):
                break
            labs.append(s)
            u += 1
        if u >= end or lines[u].strip() == '总计' or not labs:
            break
        vals = []
        while u < end and len(vals) < nvals and is_score_val(lines[u].strip()):
            vals.append(lines[u].strip())
            u += 1
        if len(vals) < nvals:
            break
        if len(labs) >= 2 and _COLLEGE_TAIL.search(labs[0]):
            cur_college = labs[0]
            xk = ' '.join(labs[1:])
        elif len(labs) == 1 and _COLLEGE_TAIL.search(labs[0]):
            cur_college = labs[0]
            xk = ''
        else:
            xk = ' '.join(labs)
        if cur_college and xk.startswith(cur_college):
            xk = xk[len(cur_college):].strip()
        row = {'学院': cur_college, '学科': xk, '政治': '', '英语': '', '业务课一': '', '业务课二': '', '总分': ''}
        for ks, v in zip(keys, vals):
            v = clean_score_val(v)
            for kk in ks:
                row[kk] = clamp_score(kk, v)
        sch['复试线'].append(row)


def parse_school(name, start, end):
    sch = {'学校': name, '层级': school_tier.get(name, ''), '简介': '', '学院': [], '学科评估': '',
           '专业': [], '复试线': [], '历年招生': [], '录取分析': []}
    i = start
    j = find_sec(['学校简介'], i, end)
    if j is not None:
        sch['简介'] = lines[nxt(j + 1, end)].strip()
    j = find_sec(['学院'], i, end)
    if j is not None:
        k = nxt(j + 1, end)
        cols = []
        while k < end:
            l = lines[k].strip()
            if not l:
                k += 1
                continue
            if re.match(r'^\(\d{3}\)[\s\u4e00-\u9fa5（）()、，]+$', l) or \
               re.match(r'^(?:\d{3})?[\u4e00-\u9fa5（）()]+(?:学院|学部|研究院|所|系)[、，]?$', l):
                cols.append(l.rstrip('、，'))
                k += 1
                continue
            break
        sch['学院'] = cols if cols else [x.strip() for x in re.split(r'[、，,]', lines[nxt(j + 1, end)].strip()) if x.strip()]
    j = find_sec(['控制学科评估排名'], i, end)
    if j is not None:
        sch['学科评估'] = lines[nxt(j + 1, end)].strip()
    # ---- 学科介绍（专业信息表）----
    j = find_sec(['一、26考研学科介绍', '26考研学科介绍', '一、27考研学科介绍', '27考研学科介绍',
                 '一、学科介绍', '学科介绍'], i, end)
    if j is None:  # 无标题的院校：从「综合性价比概况图」之后开始
        j = next((k for k in range(i, end) if '综合性价比概况图' in lines[k]), None)
    if j is not None:
        k = j + 1
        cur_col = ''
        while k < end:
            l = lines[k].strip()
            if not l:
                k += 1
                continue
            if re.match(r'^[一二三四五六七八九十]+、', l):
                break
            # 学院行（不含专业代码）
            if not re.match(r'^[（(]?(?:08|14)[0-9A-Za-z]{2}', l):
                m_col = re.match(r'^(?:[（(]?\d{2,4}[）)]?\s*)?'
                                 r'([\u4e00-\u9fa5（）()]{1,}(?:研究生院|学院|学部|研究所|研究院|系|中心|分院|实验室|校区|基地))(?:[（(][^（()）]{1,12}[）)])?[：:]?$', l)
                # 「01 (全日制)深圳先进技术研究院」是研究方向行，不是学院
                if m_col and ('全日制' in l or re.match(r'^\d{1,3}\s*[（(]', l)):
                    m_col = None
                # 形如「哈尔滨工业大学（深圳）：」的学院行（不含常见后缀）
                if not m_col:
                    m_col = re.match(r'^([一-龥]{2,12}大学(?:[（(][^（()）]{1,10}[）)])?)[：:]?$', l)
                if m_col:
                    cur_col = l.rstrip('：:').strip()
                    k += 1
                    continue
            # 学院与专业同行：智能制造学院0854 电子信息23人
            m_inline = re.match(r'^(.{2,26}?(?:研究生院|学院|学部|研究所|研究院|系|中心|分院|实验室|校区|基地))\s*'
                                r'[（(]?\s*((?:08|14)[0-9A-Za-z]{2,5})\s*'
                                r'[）)]?\s*(.*)$', l)
            if m_inline:
                cur_col = m_inline.group(1).strip()
                l = (m_inline.group(2) + m_inline.group(3)).strip()
            # 畸形残留行，如中国科学技术大学「（085406控制工程））」：不是独立专业
            if re.match(r'^[（(]\s*(?:08|14)\d{4}[^（()）]*[）)]\s*[）)]\s*$', l):
                k += 1
                continue
            foll = [lines[u].strip() for u in range(k + 1, min(k + 12, end)) if lines[u].strip()]
            major = parse_major(l, foll, cur_col)
            # 学院写在专业行括号里，如「081100控制科学与工程【学硕】（智能工程学院）5」
            if major and not major.get('学院'):
                _mi = re.search(r'[（(]([^（()）]{2,28}?(?:研究生院|学院|学部|研究所|研究院|系|中心|分院|实验室|校区|基地))[）)]', l)
                if _mi: major['学院'] = _mi.group(1)
            if major:
                for t in range(k + 1, min(k + 40, end)):   # 研究方向可能长达 10+ 行
                    ll = lines[t].strip()
                    if not ll:
                        continue
                    if re.match(r'^[二三四五六七八九十]+、', ll):
                        break
                    # 遇到下一个专业行 / 学院行就停，避免串味
                    if re.match(r'^[（(]?(?:08|14)[0-9A-Za-z]{2}', ll):
                        break
                    if re.match(r'^[（(]?\d{2,4}[）)]?\s*[一-龥]{2,}'
                                r'(?:研究生院|学院|学部|研究所|研究院|系|中心|分院|实验室|校区|基地)(?:[（(][^（()）]{1,12}[）)])?[：:]?$', ll):
                        break
                    # 编号 ①②③④ 可省略；代码可带括号：(101)思想政治理论
                    m_sub = re.match(r'^[①②③④⑤⑥⑦⑧⑨]?\s*[（(]?([1-9]\d{2})[）)]?\s*'
                                     r'([一-龥].{0,40})$', ll)
                    if m_sub:
                        major['科目'][m_sub.group(1)] = m_sub.group(2).strip()
                major['_行号'] = k + 1        # docx 原文行号（1 基），供逐行核对
                sch['专业'].append(major)
                k += 1
                continue
            k += 1

    # ---- 复试分数线（合并单元格） ----
    j = find_sec(['二、26考研复试分数线', '26考研复试分数线', '二、27考研复试分数线', '27考研复试分数线'], i, end)
    if j is None:
        # 标题带序号前缀或学院名，如「三、26考研自动化学院复试分数线」
        j = find_sec_re(r'^[一二三四五六七八九十\d]+、\s*2\d\s*考研.*复试分数线', i, end)
    if j is not None:
        hdr = None
        for t in range(j + 1, min(j + 40, end)):
            if lines[t].strip() == '学院' and lines[t + 1].strip() == '学科':
                hdr = t
                break
        if hdr is not None:
            _hlab = []
            _u = hdr + 2
            while _u < end and is_score_label(lines[_u].strip()):
                _hlab.append(lines[_u].strip())
                _u += 1
            if _hlab:
                _nv = len(_hlab)
                t = _u
            else:
                _nv = 0          # 表头列名无法识别 → 不解析（宁可空，不出垃圾行）
                t = end
            cur_college = ''

            def is_college(x):
                x0 = re.sub(r'^\d{3}\s*', '', x)
                return any(x0 in c or c in x0 for c in sch['学院']) or x.endswith(('学院', '学部', '研究生院', '研究院', '研究所', '系', '中心', '实验室'))

            while _nv and t < end:
                while t < end and not lines[t].strip():
                    t += 1
                if t >= end:
                    break
                l0 = lines[t].strip()
                if re.match(r'^[一二三四五六七八九十\d]+、', l0):
                    break
                # 学院行：后面第一个非空行不是数值
                _fw = []
                for w in range(t + 1, min(t + 9, end)):
                    s2 = lines[w].strip()
                    if s2:
                        _fw.append(s2)
                        if len(_fw) == 3:
                            break
                _nx = _fw[0] if _fw else ''
                _nx2 = _fw[1] if len(_fw) > 1 else None
                # 结构化判定：本行非值 + 下一行也不是值 + 再下一行是值 → 学院行
                _struct = (bool(_nx) and not is_score_val(_nx) and _nx2 is not None
                           and is_score_val(_nx2))
                if ((is_college(l0) or _struct) and not re.match(r'^\d+$', l0)
                        and not l0.endswith(('学硕', '专硕')) and not is_score_val(_nx)):
                    cur_college = l0
                    t += 1
                    continue
                # 学科行 + _nv 个值（允许中间夹空行）
                row = [l0]
                t += 1
                while t < end and len(row) < 1 + _nv:
                    s = lines[t].strip()
                    if not s:
                        t += 1
                        continue
                    if re.match(r'^[一二三四五六七八九十\d]+、', s):
                        break
                    row.append(s)
                    t += 1
                if len(row) < 1 + _nv:
                    break
                if not (re.match(r'^\d+$', row[0]) or all(re.match(r'^\d+$|^$', c) for c in row[1:])):
                    break
                _rec = {'学院': cur_college, '学科': row[0], '政治': '', '英语': '',
                        '业务课一': '', '业务课二': '', '总分': ''}
                for _ks, _v in zip([score_label(x) for x in _hlab], row[1:]):
                    for _kk in _ks:
                        _rec[_kk] = clamp_score(_kk, clean_score_val(_v))
                sch['复试线'].append(_rec)
        else:
            # 6 列布局没找到表头 → 试合并列布局
            parse_scoreline_merged(sch, j, end)
    # ---- 历年招生 ----
    j = find_sec(['三、招生人数（实际招生人数）', '招生人数（实际招生人数）',
                  '三、27考研招生人数（实际招生人数）', '27考研招生人数（实际招生人数）'], i, end)
    if j is None:
        j = find_sec_re(r'^[一二三四五六七八九十\d]+、.*招生人数', i, end)
    if j is not None:
        t = next((u + 1 for u in range(j + 1, min(j + 20, end)) if lines[u].strip() == '年份'), j + 1)
        while t < end:
            l = lines[t].strip()
            if not l:
                t += 1
                continue
            if re.match(r'^[一二三四五六七八九十\d]+、', l):
                break
            if is_yearish(l):
                row = [l]
                t += 1
                while t < end:
                    c = lines[t].strip()
                    if not c:
                        t += 1
                        continue
                    if re.match(r'^[一二三四五六七八九十\d]+、', c) or is_yearish(c):
                        break
                    if all(ch.isdigit() or ch in '.+-—＋/' or ch == _BS for ch in c) or '未' in c:
                        row.append('—' if c == _BS else c)   # docx 用 \ 表示无数据
                        t += 1
                    else:
                        break
                sch['历年招生'].append(row)
            else:
                t += 1
    # ---- 录取情况分析（标题写法各异，统一按同一节处理）----
    _AN_TAIL = ('录取情况分析', '录取数据分析', '录取结果分析', '复试情况分析',
                '复试数据分析', '录取情况', '复试情况')

    def _is_an_title(_s):
        _m = re.match(r'^(?:\d+|[一二三四五六七八九十]+)、\s*(.*)$', _s)
        if not _m:
            return False
        _b = re.sub(r'\s+', '', re.sub(r'^2\d?\s?考研?', '', _m.group(1)))
        return _b.endswith(_AN_TAIL)

    _hits = []
    for t in range(start, end):
        l = lines[t].strip()
        if _is_an_title(l):
            _hits.append(t)
            continue
        if re.match(r'^(?:\d+|[一二三四五六七八九十]+)、\s*2\d\s*考研?', l):
            _nx = next((lines[u].strip() for u in range(t + 1, min(t + 4, end)) if lines[u].strip()), '')
            if re.search(r'(?:录取(?:情况|数据)|复试情况)(?:分析)?$', _nx):
                _hits.append(t)
    # 兜底：按内容锚点回溯标题（标题可能是学院名、或被换行拆开）
    _ANCHOR = re.compile(r'^(?:进入复试人员初试成绩最高分|已录取人员初试成绩最高分)')
    _LABEL = re.compile(r'^(进入复试人员初试成绩|已录取人员初试成绩|最高分|最低分|平均分|分析|分数段|'
                        r'复试人数|录取人数|录取百分比|各科均分|来自拟录取名单|来自进复试名单|备注|'
                        r'政治|英语|数学|专业课|总分均分)')
    if not _hits:
        # 只有"标题法一无所获"时才启用，避免把长块切碎
        for u in range(start, end):
            if not _ANCHOR.match(lines[u].strip()):
                continue
            j = u - 1
            while j > start and _LABEL.match(lines[j].strip()):
                j -= 1
            if j > start and lines[j].strip() and not any(abs(j - h) <= 2 for h in _hits):
                _hits.append(j)
    for t in sorted(set(_hits)):
        _a = parse_analysis(t, end)
        # 丢弃"标题命中但正文无任何数据"的空壳块
        if any([_a['复试最高'], _a['复试最低'], _a['复试平均'], _a['录取最高'], _a['录取最低'],
                _a['录取平均'], _a['进复试'], _a['录取'], _a['分数段']]):
            sch['录取分析'].append(_a)
    # ---- 学院回退：学科介绍里没有学院行时，用学校级学院第一项（Excel 亦如此）----
    def _clean(c):
        c = re.sub(r'^[（(]?\d{2,4}[）)]?\s*', '', (c or '').strip())
        return c.rstrip('、，,：:').strip()

    cand = [_clean(x) for x in (sch.get('学院') or []) if _clean(x)]
    for p in sch['专业']:
        if p.get('学院'):
            p['学院'] = _clean(p['学院'])
        elif cand:
            p['学院'] = cand[0]

    return sch


schools = []
for idx, (name, start) in enumerate(sections):
    end = sections[idx + 1][1] if idx + 1 < len(sections) else N
    schools.append(parse_school(name, start, end))

json.dump(schools, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('保存:', OUT)
print('=== 统计 ===')
print('学校:', len(schools))
print('专业记录:', sum(len(s['专业']) for s in schools))
print('无专业记录:', [s['学校'] for s in schools if not s['专业']][:20])
print('复试线总数:', sum(len(s['复试线']) for s in schools))
print('历年招生总数:', sum(len(s['历年招生']) for s in schools))
print('录取分析段:', sum(len(s['录取分析']) for s in schools))
print('有学科评估:', sum(1 for s in schools if s['学科评估']))
