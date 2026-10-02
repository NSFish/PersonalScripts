#!/usr/bin/env python3
"""按 source.txt 的剧集清单重命名番剧/剧集文件（自动猜集数，不再手写正则）。

替代 BangumiRenamer 的 `-p pattern.txt` 机制：原来要用户自己写正则（S02E[0-9]{2}、
Ep.[0-9]{3}、第[0-9]{1,3}话…）去抓集数，换一个发布组就失效。这里改成**猜**：
文件名里有集数数字，source.txt 里也有，靠集数把标题赋给文件。

怎么猜（两层打分，取最高分；没把握的**不改名**，只列进待确认清单）：

1. 跨文件一致性（权重最高）。同批下下来的文件名格式是统一的，把数字替换成 `#`
   得到"结构签名"，同签名的文件按数字出现顺序对齐成槽：
   - 取值在所有文件里恒定 → 淘汰（分辨率 1080、编码 264、码率 10、**季号 02** 都死于这条）
   - 取值互不相同且都落在 1..N 内、按文件名排序大体递增 → 强加分（这就是集数槽）
   - 取值一个都不在 1..N 内 → 淘汰
2. 单文件上下文微调。看数字紧邻的前后缀：`Ep.`/`E`/`第X话` 加分；后面跟
   `p`/`i`/`bit`/`K`/`fps`、前面是 `x`/`H.`/`v`/`Part`/`Vol`/`S` 减分；
   位数与 source 位宽一致加分；被分隔符独立包住（`[01]`、`_07.`）加分——这是
   `[DBD-Raws]…[01]…[2160P]…` 这类命名的主要识别依据。

CRC/哈希（4D18E1FE）与递增区间写法（01-20）在拆数字前就**整段剔除**，不参与打分：
否则 `[4D18E1FE]` 里的 `E1` 会被当成 `Ep.1`、和真集数同分。区间只认递增的，
`x264-10bit` 里的 `264-10` 是递减编码串，不剔除。

source.txt 每行一条 `集数 标题`（集数位数由总集数决定）；行首没有数字时按上一条 +1 补。
新名 = source 行原文 + 原扩展名（已经对上的名字跳过，可重复运行）。

集数实在猜不出时的兜底（按顺序分配）：
- 目录名里带区间（如 `[01-20TV全集]`）且文件数对得上 → 用该区间做起始集数
- 否则提示加 `--order`（按文件名排序一一对应 source.txt，起始集数 `--start`）

用法: bangumi-rename -s source.txt -d <目录> [-n] [--force] [--order] [--start N]
                     [--folders] [-R] [-e mkv,ass] [-v]
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from _common import cn_to_arab, natural_key

# ── 调参区 ────────────────────────────────────────────────────────────────
MIN_SCORE = 40      # best 低于此分 → 没把握
MIN_MARGIN = 25     # best 领先 second 不足此值 → 没把握（两个候选咬得紧）
RANGE_MIN_FILES = 2  # 恒定槽/递增槽的判定至少需要这么多个同签名文件

NUM_RE = re.compile(r"\d+")
# 中文数字序号：第一话/第十二集。连写的一串汉字数字，前后是量词或边界。
CN_NUM_RE = re.compile(r"[零〇一二三四五六七八九十百千两]{1,8}(?=[话話集章回节節])")
# 区间写法：01-20 / 1~20。两边都得是数字，避开 HEVC-10bit 这类。
RANGE_RE = re.compile(r"(?<![0-9])(\d{1,3})\s*[-~—－]\s*(\d{1,3})(?![0-9])")
# CRC/哈希：8 位以上、数字与 A-F 混排的独立串（4D18E1FE / 3288FA84）
CRC_RE = re.compile(r"\b(?=[0-9A-Za-z]*\d)(?=[0-9A-Za-z]*[A-Fa-f])[0-9A-Fa-f]{8,}\b")
# 行首数字 = 集数，其余是标题
SOURCE_LINE_RE = re.compile(r"^\s*(\d+)\s*(.*)$")
# 不能进文件名的字符：路径分隔符 + Windows 保留字符（柯南清单里有 B/F/S 这类标记）
UNSAFE_CHARS = re.compile(r"[/\\:*?\"<>|]")

# 剥前缀/后缀时当作分隔符跳过的字符（不含 #，见下）
SEP_CHARS = " \t-_.[]{}【】()（）+&=~'\"!"
# "数字被分隔符独立包住"这一判定要在 rstrip 之前看原始紧邻字符，
# 所以 [ ] ( ) 之类也必须在 SEP_CHARS 里被剥掉后可复原 —— 见 split_numbers 的 raw_p/raw_s
BARE_SEPS = "[](【】（）) {}_-. "
# 数字前缀里暗示"不是集数"的标记（季号/卷号/版本/编码）
BAD_PREFIX = ("part", "vol", "season", "cd", "disc", "disk", "rev", "ver")
# 单字母前缀只在字母确实是独立标记时才算数，避免误伤
BAD_PREFIX_1CHAR = ("v", "x", "h", "s")
# 注意：这里不能放 SEP_CHARS 里的字符（rstrip 会先剥掉它们，永远匹配不上）
GOOD_PREFIX = ("ep", "episode", "no", "num", "第")
GOOD_PREFIX_1CHAR = ("e", "#")
# 数字后缀：分辨率/规格单位
BAD_SUFFIX = ("bit", "p", "i", "k", "kb", "mb", "gb", "hz", "fps", "ch", "ma")
# 数字后缀：中文集数量词
GOOD_SUFFIX = ("话", "話", "集", "章", "回", "节", "節")
# 未指定 -e 时跳过的非媒体文件（清单、说明、封面图、字幕之外的元数据）
SKIP_EXTS = {".txt", ".md", ".nfo", ".json", ".db", ".url", ".html", ".htm", ".log", ".sfv"}


@dataclass
class Candidate:
    """文件名里的一处数字，以及它作为集数的可信度。"""
    value: int
    score: int = 0
    notes: list = field(default_factory=list)   # verbose 时展示的加减分理由

    def add(self, delta: int, reason: str) -> None:
        if delta:
            self.score += delta
            self.notes.append(f"{delta:+d} {reason}")


@dataclass
class Pick:
    """单个待处理条目的判定结果。"""
    path: Path
    number: int = 0          # 0 = 没猜出来
    best: int = 0            # 最高分
    margin: int = 0          # 最高分领先次高分的差值
    confident: bool = False
    candidates: list = field(default_factory=list)


# ── source.txt ────────────────────────────────────────────────────────────
def parse_source(path: Path) -> tuple[dict, int]:
    """解析 source.txt，返回 ({集数: 该行原文}, 集数位宽)。

    保留行原文（含零填充与括号备注），新名就是它 + 原扩展名。
    行首有数字就用它；没有就按上一条 +1 续（从 1 起）。位宽取行首数字的最大位数，
    用于给文件名里的候选打分（24 集 → 2 位，`07` 比 `7` 更像集数）。
    """
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()]
    source: dict = {}
    width = 1
    last = 0
    for ln in lines:
        if not ln.strip():
            continue
        raw = ln.strip()
        m = SOURCE_LINE_RE.match(ln)
        if m:
            number = int(m.group(1))
            width = max(width, len(m.group(1)))
            title = m.group(2).strip()
        else:  # 行首无数字：整行是标题，集数接着上一条数
            number, title = last + 1, raw
        if number in source:
            print(f"⚠️ source.txt 里集数 {number} 重复，保留先出现的那行")
            continue
        # 标题里的 / 等字符会让 with_name 直接抛错：/ 换成全角，其余换成 _
        safe = UNSAFE_CHARS.sub(lambda c: "／" if c.group() == "/" else "＼" if c.group() == "\\" else "_", raw)
        if safe != raw:
            print(f"⚠️ 标题含非法字符，已替换: {raw} -> {safe}")
        source[number] = safe if m else f"{number} {title}"
        last = number
    if not source:
        raise ValueError(f"source.txt 里没解析出任何条目: {path}")
    return source, width


# ── 文件名拆解 ────────────────────────────────────────────────────────────
def noise_spans(stem: str) -> list:
    """返回不该当集数的字符区间：CRC/哈希与区间写法（01-20）。

    `[4D18E1FE]` 里的 `E1` 会被当成 `Ep.1`、`[01-20]` 里的 01/20 会被当成集数，
    所以这两类整段剔除，一个数字都不留。

    区间只认**递增**的（01-20）：`x264-10bit` 里的 `264-10` 是递减的编码串，
    不是区间，不能连带把 264/10 整段剔掉。
    """
    spans = [m.span() for m in CRC_RE.finditer(stem)]
    for m in RANGE_RE.finditer(stem):
        if int(m.group(2)) >= int(m.group(1)):
            spans.append(m.span())
    return spans


def clean_stem(stem: str) -> str:
    """剔除噪声段后的文件名主干，用于拆数字与算签名。

    顺带把中文数字序号（第一话/第十二集）转成阿拉伯数字：不转的话既识别不出集数，
    文件名的自然排序也是错的（第一话 第三话 第二话 … 按字符串排是乱的）。
    """
    for start, end in sorted(noise_spans(stem), reverse=True):
        stem = stem[:start] + stem[end:]
    return CN_NUM_RE.sub(
        lambda m: str(cn_to_arab(m.group())) if cn_to_arab(m.group()) else m.group(), stem
    )


def split_numbers(stem: str) -> list:
    """拆出 stem 里的每处数字，返回 [(数字, 紧邻前缀, 紧邻后缀, 原始左邻, 原始右邻)]。

    前缀/后缀剥掉分隔符后只留紧挨着数字的几个字符，用来判断上下文；
    raw_l/raw_r 是**未剥分隔符**的紧邻单字符，用来判断"数字是否被分隔符独立包住"
    ——这层判断必须在剥离之前看，否则 `[01]` 的 `[` 会被 rstrip 剥掉、永远匹配不上。
    """
    out = []
    for m in NUM_RE.finditer(stem):
        prefix = stem[: m.start()].rstrip(SEP_CHARS)[-6:]
        suffix = stem[m.end():].lstrip(SEP_CHARS)[:6]
        raw_l = stem[m.start() - 1] if m.start() > 0 else ""
        raw_r = stem[m.end()] if m.end() < len(stem) else ""
        out.append((int(m.group()), prefix, suffix, raw_l, raw_r))
    return out


def signature(stem: str) -> str:
    """结构签名：数字换成 #。同批文件名格式一致 → 签名一致，可对齐成槽。

    必须在 clean_stem 之后调用：CRC 段的数字个数因文件而异，不剔除会让
    "同签名"判定失败，跨文件一致性整层失效。
    """
    return NUM_RE.sub("#", stem)


def detect_range(text: str):
    """从名字里找 N-M 区间；要求 end>=start，否则返回 None。"""
    for m in RANGE_RE.finditer(text):
        start, end = int(m.group(1)), int(m.group(2))
        if end >= start:
            return start, end
    return None


# ── 打分 ──────────────────────────────────────────────────────────────────
def context_score(cand: Candidate, prefix: str, suffix: str, width: int,
                  valid: set, max_num: int, raw_l: str = "", raw_r: str = "") -> None:
    """单文件上下文：数字前后紧邻写的是什么，决定它像不像集数。

    raw_l/raw_r 是未剥分隔符的紧邻单字符，用于"独立包住"判定。
    """
    low_p, low_s = prefix.lower(), suffix.lower()

    # 前缀：季号/卷号/版本 → 减分；Ep./第 → 加分
    hit = False
    for mark in BAD_PREFIX:
        if low_p.endswith(mark):
            cand.add(-30, f"前缀 '{mark}' 是季/卷/版本标记")
            hit = True
            break
    if not hit:
        for ch in BAD_PREFIX_1CHAR:
            if low_p.endswith(ch) and not low_p[-2:-1].isalnum():
                cand.add(-30, f"前缀 '{ch}' 是版本/编码标记")
                hit = True
                break
    if not hit:
        for mark in GOOD_PREFIX:
            if low_p.endswith(mark):
                cand.add(40, f"前缀 '{mark}' 是集数标记")
                hit = True
                break
    if not hit:
        for ch in GOOD_PREFIX_1CHAR:
            # 'e' 就是 SxxEyy / Ep 的标记（CRC 段已在拆数字前整段剔除，不会误命中）
            if low_p.endswith(ch):
                cand.add(40, f"前缀 '{ch}' 是集数标记")
                break

    # 后缀：分辨率/码率单位 → 减分；中文量词 → 加分
    hit = False
    for mark in BAD_SUFFIX:
        if low_s.startswith(mark):
            cand.add(-30, f"后缀 '{mark}' 是分辨率/规格单位")
            hit = True
            break
    if not hit:
        for mark in GOOD_SUFFIX:
            if suffix.startswith(mark):
                cand.add(50, f"后缀 '{mark}' 是集数量词")
                break

    # 被分隔符完整包住 = 孤立的序号槽（[01]、_07.、-12-）。
    # 必须用 raw_l/raw_r：prefix/suffix 已被 rstrip/lstrip 剥掉分隔符，看不到这个结构。
    left_ok = raw_l == "" or raw_l in BARE_SEPS
    right_ok = raw_r == "" or raw_r in BARE_SEPS
    if left_ok and right_ok:
        cand.add(20, "数字被分隔符独立包住")

    # 位数与 source 位宽一致更像集数
    digits = len(str(cand.value))
    if digits == width:
        cand.add(15, f"位数 {digits} 与 source 位宽一致")
    elif digits < width:
        cand.add(5, f"位数 {digits} 短于位宽 {width}")
    elif digits >= 8:
        cand.add(-35, "位数过长（CRC/哈希）")
    elif digits >= 6:
        cand.add(-20, "位数偏长")

    # 是否落在 source 的集数范围里
    if cand.value <= 0:
        cand.add(-50, "集数从 1 起")
    elif cand.value in valid:
        cand.add(25, "命中 source.txt 的集数")
    elif cand.value > max_num:
        cand.add(-20, f"超出最大集数 {max_num}")


def slot_scores(stems: list, valid: set) -> dict:
    """跨文件一致性：同签名文件按数字出现顺序对齐成槽，给每个槽打分。

    返回 {(签名, 槽下标): 分数}。同批格式统一时，这一层能一次干掉分辨率、
    编码、码率、季号——它们的共同特征就是"所有文件都一样"。
    """
    groups: dict = {}
    for stem in stems:
        groups.setdefault(signature(stem), []).append(stem)
    scores: dict = {}
    for sig, members in groups.items():
        if len(members) < RANGE_MIN_FILES:
            continue  # 样本太少，恒定与否说明不了问题
        parsed = [split_numbers(s) for s in members]
        slot_count = len(parsed[0])
        if any(len(p) != slot_count for p in parsed):
            continue  # 同签名却数字个数不同，不对齐了
        for k in range(slot_count):
            vals = [p[k][0] for p in parsed]
            uniq = set(vals)
            score = 0
            if len(uniq) == 1:
                score -= 100  # 恒定 → 分辨率/季号/码率，不是集数
            elif len(uniq) == len(vals):
                score += 60   # 互不相同 → 像集数
            else:
                score += 10
            if not uniq & valid:
                score -= 60   # 一个都不在集数范围内 → 分辨率/CRC
            # 按文件名排序后该槽应大体递增（集数槽的自然特征）
            ordered = [v for _, v in sorted(zip(members, vals), key=lambda t: natural_key(t[0]))]
            pairs = max(1, len(ordered) - 1)
            non_dec = sum(1 for a, b in zip(ordered, ordered[1:]) if b >= a)
            if non_dec / pairs >= 0.8:
                score += 20
            scores[(sig, k)] = score
    return scores


def analyze(paths: list, source: dict, width: int) -> list:
    """给一批条目判定集数，返回 [Pick]。"""
    valid, max_num = set(source), max(source)
    stems = [clean_stem(p.stem) for p in paths]
    slots = slot_scores(stems, valid)
    picks = []
    for path, stem in zip(paths, stems):
        cands = []
        for i, item in enumerate(split_numbers(stem)):
            value, prefix, suffix, raw_l, raw_r = item
            cand = Candidate(value)
            context_score(cand, prefix, suffix, width, valid, max_num, raw_l, raw_r)
            slot = slots.get((signature(stem), i))
            if slot is not None:
                cand.add(slot, "跨文件一致性")
            cands.append(cand)
        cands.sort(key=lambda c: c.score, reverse=True)
        pick = Pick(path=path, candidates=cands)
        if cands:
            pick.best = cands[0].score
            pick.margin = cands[0].score - (cands[1].score if len(cands) > 1 else -999)
            pick.number = cands[0].value
            pick.confident = pick.best >= MIN_SCORE and pick.margin >= MIN_MARGIN
            if not pick.confident:
                pick.number = 0
        picks.append(pick)
    return picks


# ── 执行 ──────────────────────────────────────────────────────────────────
def iter_dirs(target: Path, recursive: bool):
    """产出待处理目录，逐个产出而非一次性收集（--folders 会改名，路径会失效）。"""
    yield target
    if not recursive:
        return
    # 每轮重新 rglob：上一轮可能刚把某个子目录改名，旧路径已失效
    seen = {target}
    queue = [target]
    while queue:
        current = queue.pop(0)
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            resolved = child.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield child
            queue.append(child)


def entries_in(d: Path, folders: bool, exts: set, source: dict, exclude: Path) -> list:
    """目录里的待处理条目：默认文件，--folders 时取子目录。

    排除三类：source.txt 本身、清单类文件（.txt/.nfo/.json… 番剧目录里常见，
    会被当成"文件名里没有数字"的待确认项）、以及名字已等于某条 source 原文的
    （让脚本可重复运行）。
    """
    done = set(source.values())
    if folders:
        items = (p for p in d.iterdir() if p.is_dir())
    else:
        items = (p for p in d.iterdir()
                 if p.is_file() and not p.name.startswith(".")
                 and p.resolve() != exclude
                 and (not exts or p.suffix.lower().lstrip(".") in exts)
                 # 未指定 -e 时跳过清单类文件；-e 显式列了才处理
                 and (exts or p.suffix.lower() not in SKIP_EXTS))
    return sorted((p for p in items if p.stem not in done),
                  key=lambda p: natural_key(p.name))


def plan_order(paths: list, start: int) -> list:
    """按顺序分配：排序后依次对应 start, start+1, … 返回 [Pick]。"""
    return [Pick(path=p, number=start + i, confident=True) for i, p in enumerate(paths)]


def resolve_picks(entries: list, d: Path, source: dict, width: int,
                  order: bool, start: int, force: bool) -> list:
    """判定这批条目的集数。全部猜不出时按目录名区间兜底。

    force 要在这里就生效，不能等到 process_dir：analyze 会把不自信的 number 置 0，
    而下面的 any(p.number) 正是靠它判断"这批到底识别出东西了吗"。若 force 晚一步，
    全批皆不自信时会被误判成"一个都没识别出来"，进而走进兜底分支空转。
    """
    if order:
        return plan_order(entries, start)
    picks = analyze(entries, source, width)
    if force:
        # 认最高分候选；文件名压根没数字的保持 0（无从下手）
        for p in picks:
            if not p.confident and p.candidates:
                p.number = p.candidates[0].value
    if any(p.number for p in picks):
        return picks
    rng = detect_range(d.name) or detect_range(d.parent.name)
    if rng and rng[1] - rng[0] + 1 == len(entries):
        print(f"💡 {d.name} 识别不到集数，按目录区间 "
              f"{rng[0]:0{width}d}-{rng[1]:0{width}d} 顺序分配")
        return plan_order(entries, rng[0])
    print(f"ℹ️ {d.name} 共 {len(entries)} 项无法识别集数，"
          f"可加 --order 按排序一一对应（起始集数用 --start）")
    return picks


def build_plan(picks: list, source: dict) -> tuple:
    """把 Pick 落成 [(原路径, 新路径)]，返回 (计划, 未处理清单)。

    同一集数 + 同扩展名只认第一个（番剧常有多种字幕/音轨共存，重名会互相覆盖）。
    """
    plan, missing = [], []
    used: dict = {}
    for pick in picks:
        if not pick.number or pick.number not in source:
            missing.append(pick)
            continue
        new_name = source[pick.number] + pick.path.suffix
        dst = pick.path.with_name(new_name)
        key = (pick.number, pick.path.suffix.lower())
        if key in used:
            print(f"❌ 集数 {pick.number} 重复，跳过: {pick.path.name}"
                  f"（已由 {used[key].name} 占用）")
            missing.append(pick)
            continue
        if dst != pick.path and dst.exists():
            print(f"❌ 目标已存在，跳过: {pick.path.name} -> {new_name}")
            missing.append(pick)
            continue
        used[key] = pick.path
        plan.append((pick.path, dst))
    return plan, missing


def report_pending(pending: list, d: Path, verbose: bool, forced: bool) -> None:
    """打印没把握的条目清单（这批评完就结束，其余照常改名）。

    forced 为真的措辞要分开：有候选的确实按最高分改了，但文件名里压根没有数字的
    无从改起（--force 也救不了），不能都说"已按最高分处理"。
    """
    if not pending:
        return
    with_cand = [p for p in pending if p.candidates]
    no_cand = [p for p in pending if not p.candidates]
    if forced:
        # 有候选的确实按最高分改了；无数字的不可能改，措辞不能混为一谈
        title = "已按最高分改名" if with_cand else "文件名无数字，无从改名"
    else:
        title = "保持原名"
    print(f"\n⚠️  {d} 有 {len(pending)} 项没把握（{title}）：")
    for p in pending:
        top = ", ".join(f"{c.value}({c.score})" for c in p.candidates[:3]) or "文件名里没有数字"
        print(f"   - {p.path.name}   候选: {top}")
        if verbose:
            for c in p.candidates[:2]:
                print(f"     {c.value}: {'; '.join(c.notes)}")
    if no_cand:
        print("   💡 无数字的项可用 --order 按排序一一对应（起始集数用 --start）")


def process_dir(d: Path, source: dict, width: int, folders: bool, exts: set,
                exclude: Path, order: bool, start: int, force: bool,
                dry_run: bool, verbose: bool) -> tuple:
    """处理一个目录，返回 (改名数, 待确认数, 失败数)。"""
    entries = entries_in(d, folders, exts, source, exclude)
    if not entries:
        return 0, 0, 0

    picks = resolve_picks(entries, d, source, width, order, start, force)
    if not force:
        for p in picks:
            if not p.confident:
                p.number = 0  # 没把握的不进改名计划

    plan, missing = build_plan(picks, source)

    if verbose:
        print(f"\n🔍 {d}")
        for pick in picks:
            detail = ", ".join(f"{c.value}({c.score})" for c in pick.candidates[:3]) or "无数字"
            flag = "✅" if pick.confident and pick.number else "⚠️"
            print(f"  {flag} {pick.path.name}  → 集数 {pick.number or '?'}  [候选: {detail}]")

    for src, dst in plan:
        print(f'✅  "{src.name}" -> "{dst.name}"')
        if not dry_run:
            src.rename(dst)

    pending = [p for p in missing if not p.number or not p.confident]
    report_pending(pending, d, verbose, force)

    return len(plan), len(pending), len(missing) - len(pending)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按 source.txt 剧集清单重命名番剧/剧集文件（自动猜集数，无需正则）")
    parser.add_argument("-s", "--source", required=True, help="剧集清单 source.txt（每行一条 '集数 标题'）")
    parser.add_argument("-d", "--directory", required=True, help="待处理的目录")
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不实际重命名)")
    parser.add_argument("--force", action="store_true",
                        help="没把握的也按最高分改名（默认只列清单、不改）")
    parser.add_argument("--order", action="store_true",
                        help="不猜集数，按文件名排序一一对应 source.txt")
    parser.add_argument("--start", type=int, default=1, help="--order 的起始集数(默认 1)")
    parser.add_argument("--folders", action="store_true", help="重命名子目录名而不是文件")
    parser.add_argument("-R", "--recursive", action="store_true", help="递归子目录(每个目录独立分析)")
    parser.add_argument("-e", "--ext", default="", help="只处理这些扩展名，逗号分隔(如 mkv,ass)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示打分详情")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    if not source_path.is_file():
        print(f"❌ source.txt 不存在: {source_path}")
        return 1
    try:
        source, width = parse_source(source_path)
    except (ValueError, OSError) as e:
        print(f"❌ {e}")
        return 1

    target = Path(args.directory).expanduser().resolve()
    if not target.is_dir():
        print(f"❌ 目录不存在: {target}")
        return 1

    exts = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()}
    print(f"📺 source.txt: {len(source)} 集 (位宽 {width})  目录: {target}")
    print(f"🏃 运行模式: {'预览 (dry-run)' if args.dry_run else '实际执行'}"
          f"{'  --force(低置信也改)' if args.force else ''}")

    renamed = pending = failed = 0
    for d in iter_dirs(target, args.recursive):
        r, p, f = process_dir(d, source, width, args.folders, exts, source_path,
                              args.order, args.start, args.force, args.dry_run, args.verbose)
        renamed += r
        pending += p
        failed += f

    verb = "将重命名" if args.dry_run else "已重命名"
    print(f"\n{verb} {renamed} 项" + (f"，{pending} 项待确认" if pending else "")
          + (f"，{failed} 项失败" if failed else ""))
    if pending and not args.force:
        print("💡 待确认项保持原名；人工核对后可加 --force 按最高分处理。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
