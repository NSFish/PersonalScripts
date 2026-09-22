#!/usr/bin/env python3
"""用 gallery-dl 下载本子并按元数据重命名目录。

用法: python hentai_download.py [--dest 目录] [--no-rename] <URL> [URL ...] [-- gallery-dl 透传参数]
  例: python hentai_download.py "https://exhentai.org/g/4200311/3ada95ac91/"
  例: python hentai_download.py --range 1-5 "https://exhentai.org/?f_search=..."（--range 会透传给 gallery-dl）

目标格式：[罗马音作者] 罗马音标题 | 中文标题（无中文则日文，都无则省略）
作者与标题第一段都按 罗马音 > 日文 > 中文 > 英文 依次退化：
- 纯拉丁片段用 wordfreq 区分罗马音/英文（罕见英文词≥2 → 罗马音；
  仅 1 个时看它是否符合 Hepburn 音节结构 → 是则罗马音，否则英文）；
- 标题来源为标题字段（title、title_jpn、originTitle 优先，其余 title* 兜底），
  每个字段先去掉开头 [...]（作者段），再按半角 | 与全角 ｜ 拆片段逐段判定语种。

流程：设代理 → 临时目录 `gallery-dl -d $WORK --write-metadata` 下载
→ 读每个画廊的 metadata json 重命名 → 按站点 move 到目标目录
（默认 `~/Downloads/hentai/<site>/`）。

依赖：gallery-dl（全局 config 需配好 cookie/限速，cookie 必须在
extractor.exhentai / extractor.e-hentai 层级）。访问 exH 需系统代理
（默认 http://127.0.0.1:7890），否则 DNS 污染超时。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import to_simplified

try:
    from wordfreq import zipf_frequency
except ImportError:  # 缺依赖时拉丁文退化为旧逻辑：一律按罗马音
    zipf_frequency = None

PROXY = "http://127.0.0.1:7890"
DEFAULT_DEST = Path.home() / "Downloads" / "hentai"


def clean(s):
    if not s:
        return ""
    s = re.sub(r'[/\\:*?"<>|]', '_', s)
    return s.strip().rstrip('.')[:180]


def get_artists(meta):
    ta = meta.get("tags_artist")
    if isinstance(ta, dict):
        vals = [v for v in ta.values() if v]
    elif isinstance(ta, list):
        vals = [v for v in ta if v]
    else:
        vals = []
    return vals


# ---------- 内容驱动判定（不看字段名，看内容） ----------
def has_latin(s): return any('a' <= c <= 'z' or 'A' <= c <= 'Z' for c in s)
def has_kana(s):  return any(('\u3040' <= c <= '\u309f') or ('\u30a0' <= c <= '\u30ff') for c in s)
def has_cjk(s):   return any('\u4e00' <= c <= '\u9fff' for c in s)


# Hepburn 罗马音节表（拗音/基本音节/拨音 n），用于区分罗马音与英文单词
_SYL3 = {"kya", "kyu", "kyo", "sha", "shu", "sho", "cha", "chu", "cho",
         "nya", "nyu", "nyo", "hya", "hyu", "hyo", "mya", "myu", "myo",
         "rya", "ryu", "ryo", "gya", "gyu", "gyo",
         "bya", "byu", "byo", "pya", "pyu", "pyo"}
_SYL2 = {"ka", "ki", "ku", "ke", "ko", "sa", "shi", "su", "se", "so",
         "ta", "chi", "tsu", "te", "to", "na", "ni", "nu", "ne", "no",
         "ha", "hi", "fu", "he", "ho", "ma", "mi", "mu", "me", "mo",
         "ya", "yu", "yo", "ra", "ri", "ru", "re", "ro", "wa", "wo",
         "ga", "gi", "gu", "ge", "go", "za", "ji", "zu", "ze", "zo",
         "da", "de", "do", "ba", "bi", "bu", "be", "bo",
         "pa", "pi", "pu", "pe", "po", "ja", "ju", "jo", "di", "du"}
_SYL1 = set("aiueon")


def is_hepburn_token(tok):
    """单词是否符合 Hepburn 罗马音节结构（启发式）。

    能识别 Mousou / Tsugutoshi / Oppai(促音) / Matcha(促音+ch)；
    英文 Sketch / Friends / Stepmom（含 sk、fr、st 等日语音系没有的辅音丛）通不过。
    外来语片假名转写（如 Sketch）会被判非罗马音，这是已知局限——
    但它只在整段仅 1 个罕见词时才起决定作用（见 latin_kind）。"""
    t = tok.lower().replace("'", "")
    if not t or not t.isalpha():
        return False
    i, n = 0, len(t)
    while i < n:
        if i + 1 < n and t[i] == t[i + 1] and t[i] not in "aeioun":
            i += 1  # 促音：双写辅音跳过一个（Oppai / Kappa）
            continue
        if t[i:i + 3] in _SYL3 or t[i:i + 3] in _SYL2:
            i += 3  # 拗音（kya/sha/cha…）与三字母基本音节（tsu/chi/shi…）
            continue
        if t[i] == "t" and t[i + 1:i + 3] == "ch":
            i += 1  # 促音 + ch（Matcha）：跳过 t，ch 由 cha/chu/cho 消费
            continue
        if t[i:i + 2] in _SYL2:
            i += 2
            continue
        if t[i] in _SYL1:
            # 拨音 n 后面不能直接跟元音/y（否则应是 na/ni/ny 系，前面已匹配）
            if t[i] == "n" and i + 1 < n and t[i + 1] in "aiueoy":
                return False
            i += 1
            continue
        return False
    return True


def latin_kind(core):
    """纯拉丁主体是 romaji 还是 english（wordfreq 英文词频判定）。

    罕见英文词（zipf < 3.0）>= 2 个为罗马音；仅 1 个时看它像不像罗马音；
    0 个则为英文。罗马音标题里总有词在英文词频表外露馅（如 Warau、Mousou），
    而纯英文标题（如 A Midsummer Night Seduction）一个都找不出。"""
    if zipf_frequency is None:
        return "romaji"
    toks = [w.replace("'", "") for w in re.findall(r"[A-Za-z']+", core)]
    toks = [w for w in toks if len(w) >= 2]
    if not toks:
        return "romaji"
    rare = [w for w in toks if zipf_frequency(w.lower(), "en") < 3.0]
    if len(rare) >= 2:
        return "romaji"
    if len(rare) == 1:
        return "romaji" if is_hepburn_token(rare[0]) else "english"
    return "english"


# 语言/版本标签词：
# - CJK 词按子串去（它們本身就是完整术语，不会是自然标题的一部分）；
# - 拉丁词必须「前面是空白/左括号」且「后面不是拉丁字母」：
#   Temptation/Attempt 不会被吃子串（Temp 后面还是字母），
#   打头的 Digital Devil Saga 也保留（标签都是缀在标题后面的，实词才打头）。
# 注意 alternation 顺序：長词在前（個人翻譯 before 翻譯，無修正 before 無修）。
_LANG_WORDS_RE = re.compile(
    r"中国翻訳|個人翻譯|翻譯|汉化|無修正|無修|完全版|単行本|单行本"
    r"|(?<=[\s\(\[（【])(?:Chinese|Digital|DL(?:版)?|Temp|English|Translated|Decensored)(?![A-Za-z])",
    flags=re.IGNORECASE,
)


def strip_leading_brackets(s):
    """返回 ([开头连续括号内容...], 余下正文)。无括号则 ([], 原文)。

    '[社团] [作者] 标题' -> (['社团', '作者'], '标题')，逐个剥开头 [...]。"""
    brackets = []
    rest = s.strip()
    while True:
        m = re.match(r'^\s*\[([^\]]*)\]\s*(.*)$', rest, re.S)
        if not m:
            break
        brackets.append(m.group(1).strip())
        rest = m.group(2).strip()
    return brackets, rest


def strip_credits(s):
    """去掉汉化组/社团署名括号：【...】 （...） 〔...〕，避免其夹带的假名干扰判定。

    激进版，只用于语种判定（classify_body 等）：真副标题如（番外編）
    也会被去掉，但判定不受影响；输出标题请用 strip_credits_for_output。"""
    return re.sub(r'[【（〔][^】）〕]*[】）〕]', '', s)


# 输出用：【】〔〕见就删（基本都是汉化组注记），（）只删命中
# 汉化/版本关键词的，（番外編）这类真副标题保留。
_CREDIT_HINT_RE = re.compile(
    r'汉化|漢化|翻譯|翻译|翻訳|個人|个人|中国|中文|同人|社团|社團|工作室'
    r'|修正|無修|単行本|单行本|完全版|Chinese|Digital|DL',
    flags=re.IGNORECASE,
)


def strip_credits_for_output(s):
    """输出标题用：【】〔〕全去，（）只去汉化组/版本注记，保留真副标题。"""
    s = re.sub(r'【[^】]*】', '', s)
    s = re.sub(r'〔[^〕]*〕', '', s)

    def _repl(m):
        inner = m.group(1)
        if _CREDIT_HINT_RE.search(inner) or _LANG_WORDS_RE.search(' ' + inner + ' '):
            return ''
        return m.group(0)

    return re.sub(r'（([^）]*)）', _repl, s)


def classify_body(s):
    """判定正文类型：romaji / japanese(含假名) / chinese(含汉字无假名) / english / None。

    以去掉语言/汉化标签后的主体判定语种；纯拉丁主体再用 latin_kind
    拆成罗马音或英文（wordfreq + Hepburn 启发式）。只返回种类。"""
    if not s:
        return None
    core = strip_credits(s)                                   # 去 【】（〔〕
    core = re.sub(r'\[[^\]]*\]', '', core)                    # 去 [Chinese] 等方括号标签
    core = _LANG_WORDS_RE.sub('', core)
    core = core.strip()
    if not core:
        return None
    if has_kana(core):
        return "japanese"
    if has_cjk(core):
        return "chinese"
    if has_latin(core):
        return latin_kind(core)
    return None


# 退化顺序：罗马音 > 日文 > 中文 > 英文（数值越小越优先）
_LANG_RANK = {"romaji": 0, "japanese": 1, "chinese": 2, "english": 3}

# 标题片段分隔符：半角 | 与全角 ｜（U+FF5C，用 chr 写法避免源码编码问题）
_SPLIT_RE = re.compile(r"\s*[|" + chr(0xFF5C) + r"]\s*")

# 对照标题分隔符：空格包裹的 - / –(U+2013) / —(U+2014)
# exH、comic-looms 常把「罗马音标题 - 英文译文」写在同一段里
_DASH_SEP_RE = re.compile(r"\s+[-" + chr(0x2013) + chr(0x2014) + r"]\s+")


def iter_title_fields(meta):
    """按 title、title_jpn、originTitle 优先，其余 title* 字段兜底，产出非空字符串。

    exH 目前只有 title / title_jpn；comic-looms 的日文原标题放在 originTitle；
    title* 前缀兜底是为了以后加字段（如 title_en）或换站点时无需改代码。"""
    yielded = set()
    for key in ("title", "title_jpn", "originTitle"):
        v = meta.get(key)
        if isinstance(v, str) and v.strip() and v not in yielded:
            yielded.add(v)
            yield v
    for key in sorted(meta):
        if key.startswith("title") and key not in ("title", "title_jpn", "originTitle"):
            v = meta.get(key)
            if isinstance(v, str) and v.strip() and v not in yielded:
                yielded.add(v)
                yield v


def collect_segments(titles):
    """各标题字段去开头 [...] 后，按 | / ｜ 拆片段（去重保序）。"""
    segments = []
    for src in titles:
        _, body = strip_leading_brackets(src)
        body = strip_credits_for_output(body).strip()
        for seg in _SPLIT_RE.split(body):
            seg = seg.strip()
            if seg and seg not in segments:
                segments.append(seg)
    return segments


def _is_tag_only(bracket):
    """括号内容是否只是语言/版本标签（如 Chinese、DL版、中国翻訳）而非作者名。

    这类括号常见于无作者信息的汉化转载标题（[Chinese] xxx），不能当作者。"""
    core = strip_credits(bracket)
    core = re.sub(r'\[[^\]]*\]', '', core)
    # 垫空格：括号内容本身就是整串，标签词常在开头，_LANG_WORDS_RE 不吃打头词
    core = _LANG_WORDS_RE.sub('', ' ' + core + ' ')
    return not core.strip(" ()-")


def detect_author(titles, artists):
    """作者只取个人画师，不要社团(circle)，语种按退化顺序选最优。

    候选：tags_artist（干净，只含画师，原样保留大小写）+ 各标题字段开头 [...]
    （剥离社团，原样保留大小写）。同语种下 tags_artist 优先（它排在候选首位）。
    同一标题内多个开头括号（如 '[社团] [作者]'）以后出现的优先（更靠近标题
    的更可能是作者）；跨标题仍是 title、title_jpn、originTitle 在前者优先。
    标题括号常见 exH 写法 '[社团 (作者)]'，由 _author_from_bracket 剥离出作者。"""
    cands = []
    joined = ", ".join(a.strip() for a in artists if a and a.strip())
    if joined:
        cands.append(joined)
    for src in titles:
        brackets, _ = strip_leading_brackets(src)
        for b in reversed(brackets):  # 后括号优先：[社团] [作者] 取作者
            if b and not _is_tag_only(b):
                cands.append(_author_from_bracket(b))
    best, best_rank = "", 99
    for c in cands:
        kind = classify_body(c)
        rank = _LANG_RANK.get(kind, 99)
        if rank < best_rank:
            best, best_rank = c, rank
    return best


def _author_from_bracket(bracket):
    """从标题括号内容里剥离出作者名，丢弃社团。

    exH 常见写法：
      '[社团 (作者)]'  -> 取 (...) 内作者（原样保留大小写），社团丢弃
      '[社团] [作者]'  -> 双括号由 detect_author 按后括号优先取作者
      '[单一作者]'     -> 没有 (...) 结构，整段当作者（不截断，原样保留）
    只有社团、无 (作者) 的（如 '[Sakura Circle]'）无法可靠拆分，整段返回（可能含社团）。"""
    bracket = bracket.strip()
    m = re.search(r'\(([^()]+)\)', bracket)         # 提取 (作者) 部分
    if m and m.group(1).strip():
        return m.group(1).strip()
    return bracket                                  # 无 (...) 结构：整段当作者


def split_dash_variants(seg):
    """拆「原标题 - 英文译文」对照段，丢掉英文那半。

    exH / comic-looms 的 title 常把罗马音标题与英文译文用 ' - '（或 – / —）
    连在同一段里：
      'Sensei, Konshuu mo Otsukaresama, desu - Sensei, Thank You For Your Hard Work This Week.'
    整段判定只会当成一个罗马音标题，于是英文译文被带进目录名。
    这里按分隔符切开逐段判定语种，只要**同时存在英文段与非英文段**，
    就丢弃英文段、把其余段按原顺序接回；否则（切不开、只有一段、
    或各段语种一致，如纯英文标题 "Foo - Part 2"）原样返回，
    不改变既有行为。"""
    parts = [p.strip() for p in _DASH_SEP_RE.split(seg)]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return seg
    kinds = [classify_body(p) for p in parts]
    if "english" not in kinds:
        return seg
    if all(k == "english" for k in kinds):
        return seg
    kept = [p for p, k in zip(parts, kinds) if k != "english"]
    return " - ".join(kept)


def detect_title_parts(titles):
    """返回 (标题, 拼接标题)。

    标题按 罗马音 > 日文 > 中文 > 英文 取最优片段；
    拼接标题按 中文 > 日文 取最优（与标题去重后不同才保留，否则省略，都无则省略）。
    注意：纯拉丁段即使夹了 [Chinese]/[翻譯] 标签也要先看主体——
    是罗马音才当标题候选，是英文则按英文退化（不再与罗马音同级）。
    判定为中文的片段在**去标签之后**转简体（见 _format_title）。"""
    segments = collect_segments(titles)
    first = {}  # kind -> (原片段, kind)
    for raw_seg in segments:
        seg = split_dash_variants(raw_seg)
        kind = classify_body(seg)
        if kind and kind not in first:
            first[kind] = seg
    title_raw = next((first[k] for k in ("romaji", "japanese", "chinese", "english") if k in first), "")
    title_kind = classify_body(title_raw) if title_raw else None
    title_part = _format_title(title_raw, title_kind) if title_raw else ""
    second_part = ""
    for k in ("chinese", "japanese"):
        if k in first:
            cand = _format_title(first[k], k)
            if cand and cand != title_part:
                second_part = cand
                break
    return title_part, second_part


def _format_title(seg, kind):
    """去标签 → 中文再繁转简。

    顺序很关键：_LANG_WORDS_RE 里的标签词是繁简混合的（無修正 有、无修正 没有），
    若先转简体，原本能被吃掉的 無修正 就吃不掉了。所以先按原文去标签，
    只对最终中文结果做字形转换。"""
    cleaned = cleanup_title(seg)
    return to_simplified(cleaned) if kind == "chinese" else cleaned


def cleanup_title(s):
    """去除标题里的语言/汉化组/版本标签：【…】、[…] 方括号标签、孤立标签词，
    以及小括号 (...) 与全角括号 （...）里的全部内容（默认全去；
    个别值得保留的以后加白名单）。
    注意：[社团 (作者)] 这类作者括号走 _author_from_bracket，不受影响；
    语言词仍只吃独立单词（Temptation / Digital Devil Saga 不受影响）。"""
    s = strip_credits_for_output(s)                         # 去 【】〔〕与注记性 （）
    s = re.sub(r'\[[^\]]*\]', '', s)                       # 去 [Chinese] [Digital] 等方括号
    s = _LANG_WORDS_RE.sub('', s)
    prev = None                                             # 循环到稳定，顺带处理嵌套括号
    while prev != s:
        prev = s
        s = re.sub(r'\([^()]*\)', '', s)
        s = re.sub(r'（[^（）]*）', '', s)
    return re.sub(r'\s{2,}', ' ', s).strip()


def build_name(meta) -> str:
    """由元数据拼出目录名：[罗马音作者] 罗马音标题 | 中文标题。

    作者与标题第一段均按 罗马音 > 日文 > 中文 > 英文 依次退化；
    拼接标题按 中文 > 日文，缺失自动省略；标题里的 (...) / （...）内容一律剥除。"""
    titles = list(iter_title_fields(meta))
    author = detect_author(titles, get_artists(meta))
    title_part, second_part = detect_title_parts(titles)
    parts = []
    if author:
        parts.append(f"[{clean(author)}]")
    if title_part:
        parts.append(clean(title_part))
    if second_part:
        parts.append(clean(second_part))
    if not parts:
        return "untitled"
    if author:
        # [作者] T1 | T2（无标题段时只有 [作者]，不能留尾随空格）
        return parts[0] + (" " + " | ".join(parts[1:]) if len(parts) > 1 else "")
    return " | ".join(parts)


def rename_one(d: Path) -> None:
    """重命名单个本子目录：有 metadata json 就用它，没有就按目录现名规范化。

    json 存在但读坏/无有效标题时仍跳过（不拿现名兜底）。"""
    matches = sorted(p for p in d.iterdir() if p.suffix == ".json" and p.is_file())
    json_path = matches[0] if matches else None
    if json_path is None:
        meta = {"title": d.name}  # 无元数据：现名当标题走同一套流程
    else:
        meta = {}
        try:
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
            else:
                print(f"  [warn] unexpected metadata shape: {json_path}")
        except Exception as e:
            print(f"  [warn] read meta failed {json_path}: {e}")
    newname = build_name(meta)
    if newname == "untitled":
        print(f"  [warn] 无有效标题，跳过重命名: {d}")
        return
    newpath = d.parent / newname
    if newpath == d:
        return
    if newpath.name.casefold() == d.name.casefold():
        # 仅大小写差异（如旧库 Title Case → 新规则原样输出）：大小写不敏感
        # 文件系统上 exists() 会把自己误判成冲突，直接改名即可
        try:
            d.rename(newpath)
            print(f"  -> {newpath.name}")
        except Exception as e:
            print(f"  [warn] rename failed {d}: {e}")
        return
    base = newpath
    i = 1
    while newpath.exists():
        newpath = Path(f"{base} ({i})")
        i += 1
    try:
        d.rename(newpath)
        print(f"  -> {newpath.name}")
    except Exception as e:
        print(f"  [warn] rename failed {d}: {e}")


def move_to_dest(work: Path, dest: Path) -> None:
    for site in sorted(work.iterdir()):
        if not site.is_dir():
            continue
        target = dest / site.name
        target.mkdir(parents=True, exist_ok=True)
        for entry in sorted(site.iterdir()):
            dst = target / entry.name
            if dst.exists():
                # 与 rename_one 同风格：名 (1)、名 (2) 递增，循环直到不撞为止
                base = dst
                i = 1
                while dst.exists():
                    dst = Path(f"{base} ({i})")
                    i += 1
            shutil.move(str(entry), str(dst))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="用 gallery-dl 下载本子并按 [罗马音作者] 罗马音标题 | 中文标题 重命名目录")
    parser.add_argument("urls", nargs="*", help="画廊/搜索 URL（可多个）")
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help=f"正式落盘目录（默认 {DEFAULT_DEST}）")
    parser.add_argument("--no-rename", action="store_true", help="跳过重命名，直接按站点 move")
    parser.add_argument("--range", dest="range_", default=None, help="透传给 gallery-dl 的 --range（如 1-5）")
    args, extra = parser.parse_known_args(argv)
    # `--` 后的透传参数：parse_known_args 会保留 `--` 本体，去掉它
    extra = [a for a in extra if a != "--"]
    if not args.urls:
        parser.print_usage(sys.stdout)
        print("hentai_download.py: error: 至少需要一个 URL", file=sys.stderr)
        return 2

    gallery_dl = shutil.which("gallery-dl")
    if not gallery_dl:
        print("❌ 未找到 gallery-dl（brew install gallery-dl）")
        return 1

    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("https_proxy", PROXY)
    env.setdefault("http_proxy", PROXY)

    with tempfile.TemporaryDirectory(prefix="hentai-download.") as work:
        cmd = [gallery_dl, "-d", work, "--write-metadata"]
        if args.range_:
            cmd += ["--range", args.range_]
        cmd += [*extra, *args.urls]
        r = subprocess.run(cmd, env=env)
        if r.returncode != 0:
            print(f"❌ gallery-dl 失败 (exit {r.returncode})")
            return r.returncode
        workdir = Path(work)
        if not args.no_rename:
            for site in sorted(workdir.iterdir()):
                if not site.is_dir():
                    continue
                for entry in sorted(site.iterdir()):
                    if entry.is_dir():
                        rename_one(entry)
        move_to_dest(workdir, dest)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
