# -*- coding: utf-8 -*-
"""《27考研择校宝典》docx 专业信息行解析器（v4）

已覆盖排版：
  1  085400电子信息（专业学位）12（名额不变）注：…
  2  081100 控制科学与工程 【学硕】 2（减少10人）注：…
  3  （081100）控制科学与工程【招生计划为80（26实际录取人数90人，相比于25减少14人）】
  4  （081100）控制科学与工程 【学硕】（智能工程学院）5（减少19人）注：…
  5  081100 控制科学与工程 / 研究方向 / 预计招生 / … / 1人          计划在后续行
  6  控制科学与工程（0811）8（增加1人）注：…                       代码在名称后
  7  【学硕】（081100）控制科学与工程 17（名额不变）注：…            学位标记前置
  8  081100（学术学位）控制科学与工程  22个（含推免生1个）           标记在代码与名称之间
  9  人工智能与机器人学院 （081100）控制科学与工程 【学硕】12…        学院前缀 + 全角括号代码
"""
import re

# 学位标记：【学硕】/【专硕】/（学硕）/（专硕）/（学术学位）/（专业学位）/（学术硕士）…
DEG      = r'学硕|专硕|学术学位|专业学位|学术硕士|专业硕士'
MARKER   = re.compile(r'【(?:%s)】|[（(](?:%s)[）)]' % (DEG, DEG))
DEG_OF   = {'学硕': '学硕', '学术学位': '学硕', '学术硕士': '学硕',
            '专硕': '专硕', '专业学位': '专硕', '专业硕士': '专硕'}
CHANGE   = re.compile(r'[（(]\s*(增加|减少|名额不变|不变|扩招|该专业为新增专业[！!]?)[^）)]*[）)]')
NOTE     = re.compile(r'注[：:]\s*(.*)$')
# 名称右侧截断词：招生口径说明
CUTWORD  = re.compile(r'暂定招生人数|预计招生|招生人数|招生计划|拟招生|方向|名额')
# 专业代码：门类 08(工学) / 14(交叉学科)，长度 4–7（含 0811J1、08100Z1 等）
CODEPAT  = r'(?:08|14)[0-9A-Za-z]{2,5}'
CODE_HEAD = re.compile(r'^[（(]?\s*(%s)\s*[）)]?(?![0-9A-Za-z])' % CODEPAT)
CODE_MID  = re.compile(r'^(?P<name>[^（(]{2,40}?)[（(](?P<code>%s)[）)]\s*(?P<tail>.*)$' % CODEPAT)
DEG_HEAD  = re.compile(r'^【(?:%s)】\s*' % DEG)
BAD_NAME = ('研究方向', '初试科目', '复试科目', '招生计划', '预计招生', '科目', '备注', '复试笔试')
# 尾部括注里出现这些词 => 是说明而非名称
PAREN_KEEP = re.compile(r'[（(][^（()）]*(?:招生|全日制|学硕|专硕|学院|方向|学位|合作|计划|硕士|培养|专项)[^（()）]*[）)]$')
F3 = re.compile(r'【\s*招生计划为\s*(\d+)\s*[（(]([^）)]*)[）)]\s*】')


def _clean_name(n):
    n = (n or '').strip(' 　:：、,，')
    n = re.sub(r'[（(](?:%s)[）)]$' % DEG, '', n).strip()
    for _ in range(4):                       # 反复剥尾部说明性括注
        m = PAREN_KEEP.search(n)
        if not m: break
        n = n[:m.start()].strip(' 　:：、,，')
    n = re.sub(r'[（(][^（()）]*$', '', n).strip(' 　:：、,，')   # 未闭合尾括注
    n = re.sub(r'【[^】]*$', '', n).strip()                     # 未闭合【
    n = re.sub(r'^[（(][^（()）]{1,20}[）)]\s*', '', n).strip()   # 前置括注（全日制、非全日制）
    # 尾部右括号只在「括号不配平」时才剥（控制工程）） → 控制工程；保留 （含量子技术等）
    if n.count('）') + n.count(')') > n.count('（') + n.count('('):
        n = re.sub(r'[）)]+$', '', n).strip()
    n = re.sub(r'\s*\d+(?:[、/]\d+)*\s*(?:方向|个|人)?$', '', n).strip()  # 尾部方向/数量
    return n.strip(' 　:：、,，')


def _split_name_tail(s, tail=''):
    cut = None
    for pat in (CHANGE, NOTE, CUTWORD):
        c = pat.search(s)
        if c and (cut is None or c.start() < cut): cut = c.start()
    num = re.search(r'\d', s)
    if num and (cut is None or num.start() < cut): cut = num.start()
    if cut is not None:
        return s[:cut].strip(), (s[cut:].strip() + ' ' + tail).strip()
    return s.strip(), tail


LABEL = re.compile(r'^[\s　]*(?:暂定招生人数|招生人数|预计招生|招生计划|拟招生人数|拟招生|计划)[：:]?\s*(.*)$')


def _plan_from(srcs):
    for src in srcs:
        if not src: continue
        tgt = src
        ml = LABEL.match(tgt)
        if ml: tgt = ml.group(1)
        mp = re.match(r'[\s　]*(?:[（(][^）)]{1,24}[）)]\s*)?'
                      r'([0-9]+(?:\s*[+＋]\s*[0-9]+)*)\s*[个人]?', tgt)
        if not mp: continue
        # 「01/04方向」这类不是计划，跳过
        if re.match(r'\s*[/、]\s*\d', tgt[mp.end():]): continue
        raw = mp.group(1)
        nums = [int(x) for x in re.split(r'[+＋]', raw) if x.strip().isdigit()]
        # 合理性：单个专业招生计划不可能超过 2000 人（>2000 多半是误抓到下一行的专业代码）
        if not nums or sum(nums) > 2000: continue
        ch = CHANGE.search(src)
        return (sum(nums) if nums else None), raw, (ch.group(0).strip('（）() ') if ch else '')
    return None, '', ''


def parse_major(line, following=(), cur_college=''):
    s = (line or '').strip()
    if not s: return None

    degree = ''
    mh = DEG_HEAD.match(s)
    if mh:
        degree = DEG_OF.get(mh.group(0).strip('【】'), '')
        s = s[mh.end():].strip()
    if not s: return None

    # ── 定位代码与名称 ──
    code = name = None
    mc = CODE_HEAD.match(s)
    if mc:
        code, rest = mc.group(1), s[mc.end():].strip()
        # 名称可能仍在学位标记之后：081100（学术学位）控制科学与工程
        name, tail = _split_name_tail(rest)
    else:
        mm = CODE_MID.match(s)
        if not mm: return None
        code, name, tail = mm.group('code'), mm.group('name').strip(), mm.group('tail').strip()
    if not name: return None

    # ── 学位标记（挂在名称上）──
    mk = MARKER.search(name)
    if mk:
        degree = degree or DEG_OF.get(mk.group(0).strip('【】（）()'), '')
        if mk.start() == 0:                       # 标记在名称之前
            name, tail = _split_name_tail(name[mk.end():].strip(), tail)
        else:                                      # 标记在名称之后
            tail = (name[mk.end():].strip() + ' ' + tail).strip()
            name = name[:mk.start()]
    name = _clean_name(name)
    if not name or re.match(r'^\d+$', name) or any(k in name for k in BAD_NAME): return None

    # ── 自含格式：【招生计划为80（26实际录取人数90人，相比于25减少14人）】──
    f3 = F3.search(name) or F3.search(tail) or F3.search(s)
    if f3:
        inner = f3.group(2)
        admit = None
        ma = re.search(r'(?:26)?\s*实际(?:录取|招生)人数?\s*(\d+)', inner)
        if ma: admit = int(ma.group(1))
        chg = ''
        mch = re.search(r'相比于\s*25\s*(增加|减少|不变)\s*(\d*)', inner)
        if mch: chg = mch.group(1) + (mch.group(2) or '')
        nm = _clean_name(name[:f3.start()] if f3.group(0) in name else name)
        if not nm or any(k in nm for k in BAD_NAME): return None
        mn = NOTE.search(s)
        return {'学院': cur_college, '代码': code, '名称': nm, '学位': degree,
                '招生计划': int(f3.group(1)), '实际录取': admit, '招生计划原文': f3.group(1),
                '变化': chg, '科目': {}, '备注': mn.group(1).strip() if mn else ''}

    # ── 计划 + 变化 ──
    plan, plan_raw, chg = _plan_from((tail,) + tuple(following))
    if not chg:
        mcx = CHANGE.search(tail) or CHANGE.search(s)
        if mcx: chg = mcx.group(0).strip('（）() ')
    mn = NOTE.search(s)
    return {'学院': cur_college, '代码': code, '名称': name, '学位': degree,
            '招生计划': plan, '实际录取': None, '招生计划原文': plan_raw,
            '变化': chg, '科目': {}, '备注': mn.group(1).strip() if mn else ''}
