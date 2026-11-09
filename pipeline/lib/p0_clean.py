# Vendored from the private production pipeline (syllabus2anki).
# Logic UNCHANGED except: (1) WS data-dir override via S2A_DATA_DIR,
# (2) tolerant/overridable data-file loads (S2A_ENTRIES / S2A_AUDIO_MAP_OUT).
# Regression-verified byte-identical against production outputs. See docs/pipeline.md.
# -*- coding: utf-8 -*-
"""
P0 数据清洗模块（2026-11-08）
四项：
  1) 全字段 HTML 实体清洗（含二次编码），登记标记 <英> → 〔英〕
  2) 例句前导编号清理（真题 PDF 页码/题号 + 卡片数字标记改圆点）
  3) 搭配过滤三条（词+虚词伪搭配 / 中文释义截 12 字 / 领域标记长串）
  4) 助记空壳消隐（纯词根分解不当助记；音节==单词、词根==单词 也不渲染）

用法：import p0_clean as P0
"""
import html
import re

# ---------- 1) HTML 实体 ----------

# 源数据里 <xx> 既可能是真标签，也可能是词典登记标记（用法/语域标注）
REAL_TAGS = {
    "br", "b", "i", "em", "strong", "span", "div", "p", "ul", "ol", "li",
    "u", "s", "sub", "sup", "font", "td", "tr", "table", "img", "a", "small",
}
_TAG_ANY = re.compile(r"<[^<>]{0,240}>")
# 登记标记可能带空格/逗号（"<美， 非正式>" "<英， 非正式>"），\s 会把它们漏掉
_SHORT_TAG = re.compile(r"<([^<>]{1,14})>")
_ENTITY = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,10}|#\d{1,6}|#x[0-9a-fA-F]{1,5});")


def unescape_all(s, rounds=3):
    """反复解码直到不再变化（处理 &amp;#x27; 这类二次编码）"""
    if not s:
        return ""
    prev = None
    cur = s
    for _ in range(rounds):
        if cur == prev:
            break
        prev = cur
        cur = html.unescape(cur)
    return cur


def marks_to_brackets(s):
    """<英> <非正式> <美，非正式> → 〔英〕 〔非正式〕（真标签原样保留）"""
    def rep(m):
        t = m.group(1)
        base = re.split(r"[\s=]", t, 1)[0].lower().lstrip("/")
        return m.group(0) if base in REAL_TAGS else f"〔{t}〕"
    return _SHORT_TAG.sub(rep, s)


def text(s):
    """任意字段值 → 纯文本：解码实体、登记标记转方括号、去真标签、压空白"""
    s = unescape_all(s)
    s = marks_to_brackets(s)
    s = _TAG_ANY.sub("", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def esc(s):
    """HTML 转义但不动引号：Anki 字段里 &#x27; 会以源码形式露在卡面上"""
    return html.escape(s or "", quote=False)


def has_residue(s):
    """渲染后在卡面上还能看到的脏东西？

    浏览器只解码一层实体，所以这里也只解一次：
      · 再看到 &xxx; → 二次编码漏网
      · 再看到 <英> 这类短标签 → 登记标记没转方括号
    """
    t = html.unescape(s or "")
    if _ENTITY.search(t):
        return True
    for m in _SHORT_TAG.finditer(t):
        base = re.split(r"[\s=]", m.group(1), 1)[0].lower().lstrip("/")
        if base not in REAL_TAGS:
            return True
    return False


# ---------- 2) 例句编号 ----------

# 「38.」「26 」「6 · 5 」「34.」「6.·9 」；不吞正文里的年份/数字
_LEAD_NUM = re.compile(
    r"^\s*(?P<n>\d{1,3}(?:\s*[.．、·]\s*\d{1,3})?)"
    r"(?:\s*[.．、)）·]\s*|\s+)"
)


def strip_lead_num(s):
    """去掉句子前导题号/页码。只在剩余部分以字母开头时动手，避免切坏正文数字。"""
    if not s:
        return ""
    t = s.lstrip()
    m = _LEAD_NUM.match(t)
    if not m:
        return t
    rest = t[m.end():].lstrip()
    if not rest or not rest[0].isalpha():
        return t
    # 「1990 was a good year」这类：数字后紧跟空格且是年份 → 不当编号
    if re.fullmatch(r"\d{4}", m.group("n")) and m.group("n").endswith(("19", "20")):
        return t
    rest = rest[0].upper() + rest[1:]
    return rest


def clean_sentence(s):
    """例句用：解码 → 去标签 → 去前导编号 → 收空白"""
    s = unescape_all(s)
    s = _TAG_ANY.sub("", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s{2,}", " ", s).strip()
    return strip_lead_num(s)


# ---------- 3) 搭配 ----------

VIRT = {
    "of", "on", "to", "in", "for", "with", "at", "by", "from", "about",
    "into", "upon", "as", "that", "than", "and", "or", "the", "a", "an",
}
DOMAIN = re.compile(r"[◎［【\[]")
ZH_LIMIT = 12


def _cut_zh(zh, limit=ZH_LIMIT):
    """中文释义截到 ≤limit 字，优先在标点处断"""
    zh = zh.strip()
    if len(zh) <= limit:
        return zh
    head = zh[:limit + 1]
    for i in range(len(head) - 1, 3, -1):
        if head[i] in "；;，,、。：:":
            return zh[:i]
    return zh[:limit]


_MARK_ANY = re.compile(r"[◎［］【】\[\]]")


def _clean_zh_marks(zh):
    """剥领域/分项标记：◎ 当分项符取首段；[]［］【】 直接删"""
    zh = zh.strip()
    if "◎" in zh:
        zh = zh.split("◎", 1)[1] if zh.startswith("◎") else zh.split("◎")[0]
    zh = re.sub(r"[［【\[][^］】\]]{0,6}[］】\]]", "", zh)
    zh = _MARK_ANY.sub("", zh)
    return re.sub(r"\s{2,}", " ", zh).strip(" ；;，,、")


def colloc_ok(en, zh):
    """搭配是否保留。返回 (ok, 新中文释义)

    规则（留长串才丢，不整条误杀）：
      ① 二词 + 虚词 → 伪搭配，丢
      ② 剥掉 ◎ 分项与 [医][化] 类标记
      ③ 剥完为空，或仍超 12 字 → 丢；否则截到 12 字
    """
    en = (en or "").strip()
    zh = (zh or "").strip()
    if not en or not zh:
        return False, zh
    toks = en.lower().split()
    if len(toks) == 2 and toks[1] in VIRT:   # ① impact of / permit of
        return False, zh
    zh2 = _clean_zh_marks(zh)                # ②
    if not zh2:
        return False, zh2
    if len(zh2) > ZH_LIMIT * 2:              # ③ 剥完仍是长串（>24 字）→ 丢
        return False, zh2
    return True, _cut_zh(zh2)


# ---------- 4) 助记空壳 ----------

def mnemonic_shell(m):
    """纯词根分解（无可落地释义）判为空壳。
    v.【ag -加强意义，grav 重，-ate 动词后缀】  → 空壳
    n.【cult 培养；“由教养所形成的”→ 文化】   → 有效
    多 + 述：含 → 或引号释义才算把词义讲出来
    """
    if not m:
        return True
    t = m.strip()
    t = re.sub(r"^[a-zA-Z/\.]{1,12}\s*[.．:：]\s*", "", t)   # 去掉词性前缀
    if "→" not in t and "“" not in t and "”" not in t:
        return True
    # 有箭头但箭头后没有落点，且引号里也没有释义 → 仍算空壳
    tail = [x for x in t.split("→") if x.strip()]
    if not tail:
        return True
    return False


def syll_ok(syl, word):
    """音节切分是否真的切开了（knee 只有一段 = 和单词一样，没信息）"""
    if not syl:
        return False
    segs = [x for x in re.split(r"[·\-]", syl) if x.strip()]
    return len(segs) >= 2


def root_ok(root_text, word):
    """词根说明是否只是把单词重复一遍"""
    if not root_text:
        return False
    plain = re.sub(r"[\s·\-]", "", root_text).lower()
    return plain != re.sub(r"[\s·\-]", "", (word or "")).lower()
