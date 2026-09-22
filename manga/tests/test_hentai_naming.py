"""hentai_download 命名逻辑的离线单测（纯函数，不碰网络）。"""
import json
import subprocess
import sys
from pathlib import Path

from hentai_download import (
    build_name,
    cleanup_title,
    is_hepburn_token,
    latin_kind,
    move_to_dest,
    split_dash_variants,
)

SRC = Path(__file__).parent.parent / "src"


def run_ok(mod, *args):
    r = subprocess.run(
        [sys.executable, str(SRC / mod), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, f"{mod} 失败\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    return r


def make_gallery(parent, name, meta):
    d = parent / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "001.jpg").write_bytes(b"x")
    return d


def test_hepburn_tokens():
    for w in ("Mousou", "Kyou", "Tsugutoshi", "Roshutsu", "Oppai", "Matcha", "Shin", "Miyabe"):
        assert is_hepburn_token(w), w
    for w in ("Sketch", "Friends", "Stepmom", "Seduction", "Night", "Housewife", "Comic"):
        assert not is_hepburn_token(w), w


def test_latin_kind():
    assert latin_kind("Warau Kaseifuu~men for 3D") == "romaji"
    assert latin_kind("Kimi to no Mousou Sketch") == "romaji"
    assert latin_kind("Anna, Kyou-chan to Naa") == "romaji"
    assert latin_kind("A Midsummer Night Seduction") == "english"
    assert latin_kind("The Neighbor Housewife Affair") == "english"
    assert latin_kind("My Stepmom and Her Friends") == "english"


def test_golden_4199623():
    meta = {
        "title": "[Fukurou Naru Tori] 新妻七歌的露出妄想3",
        "title_jpn": "[フクロウなる鳥]新妻七歌の露出妄想3",
        "tags_artist": ["fukurou naru tori"],
    }
    # 作者原样输出（不再首字母大写）：tags 小写就保持小写
    assert build_name(meta) == "[fukurou naru tori] 新妻七歌の露出妄想3 | 新妻七歌的露出妄想3"


def test_golden_4200311():
    meta = {
        "title": "[Kito Sakeru] Warau Kaseifuu~men for 3D (COMIC X-EROS #138) [Chinese] [Digital]",
        "title_jpn": "[鬼頭サケル] 笑ゥかせいふぅ～めん for 3D (コミックゼロス #138) [中国翻訳] [DL版]",
        "tags_artist": ["kito sakeru"],
    }
    assert build_name(meta) == "[kito sakeru] Warau Kaseifuu~men for 3D | 笑ゥかせいふぅ～めん for 3D"


def test_english_degrades_to_japanese():
    """拉丁段是纯英文时，标题退化选日文，不再把英文当罗马音。

    第二段严格只放中文（无中文则省略），英文在有更优选项时直接丢弃。"""
    meta = {
        "title": "My Stepmom and Her Friends",
        "title_jpn": "となりの人妻",
        "tags_artist": [],
    }
    assert build_name(meta) == "となりの人妻"


def test_split_dash_variants_drops_english_translation():
    """「罗马音标题 - 英文译文」只留罗马音一侧。"""
    assert split_dash_variants(
        "Sensei, Konshuu mo Otsukaresama, desu - Sensei, Thank You For Your Hard Work This Week."
    ) == "Sensei, Konshuu mo Otsukaresama, desu"
    # 长破折号（en/em dash）同样识别
    assert split_dash_variants(
        "先生、今週もお疲れ様、です \u2014 Sensei, Thank You For Your Hard Work This Week."
    ) == "先生、今週もお疲れ様、です"
    assert split_dash_variants(
        "Konshuu mo Otsukaresama \u2013 Thank You For Your Hard Work This Week"
    ) == "Konshuu mo Otsukaresama"


def test_split_dash_variants_keeps_unrelated_dashes():
    """没有英文对照侧的破折号保留：纯英文标题、噪声段、单段都不动。"""
    assert split_dash_variants("A Midsummer Night - Seduction") == "A Midsummer Night - Seduction"
    assert split_dash_variants("Foo - Part 2") == "Foo - Part 2"
    assert split_dash_variants("Kimi to no Mousou Sketch") == "Kimi to no Mousou Sketch"
    assert split_dash_variants("Foo-Bar") == "Foo-Bar"  # 无空格包裹，不是分隔符


def test_golden_dash_translation_meta():
    """实测 meta.json：罗马音标题后跟 ' - 英文译文'，目录名去掉英文部分；
    中文拼接段同时繁转简。"""
    meta = {
        "title": "[Mikeneko (simao)] Sensei, Konshuu mo Otsukaresama, desu - "
                 "Sensei, Thank You For Your Hard Work This Week. | "
                 "老師，這週也辛苦你了 (Blue Archive) [Chinese] [Decensored] [Digital]",
        "originTitle": "[みけねこ (simao)] 先生、今週もお疲れ様、です (ブルーアーカイブ) "
                       "[中国翻訳] [無修正] [DL版]",
        "tags_artist": ["simao"],
    }
    assert build_name(meta) == "[simao] Sensei, Konshuu mo Otsukaresama, desu | 老师，这周也辛苦你了"


def test_traditional_chinese_to_simplified():
    """繁体中文标题转简体。"""
    assert build_name({"title": "Romaji Title | 老師，這週也辛苦你了"}) == "Romaji Title | 老师，这周也辛苦你了"
    # 中文单独作标题段时同样转
    assert build_name({"title": "老師，這週也辛苦你了"}) == "老师，这周也辛苦你了"
    # 繁体版本标签仍照去（去标签在转简体之前，無修正 不被简体化后漏网）
    assert build_name({"title": "漢化組的圖書館"}) == "汉化组的图书馆"


def test_simplified_chinese_unchanged():
    """已是简体则保持原样（幂等），不做词汇改写（软体/档案 不变成 软件/文件）。"""
    assert build_name({"title": "Romaji Title | 老师，这周也辛苦你了"}) == "Romaji Title | 老师，这周也辛苦你了"
    assert build_name({"title": "Romaji Title | 软体工程师的档案"}) == "Romaji Title | 软体工程师的档案"


def test_japanese_title_not_simplified():
    """日文标题的汉字不能被误转：今週/週末 这类日文写法必须保持。"""
    # 日文段（含假名）作标题
    assert build_name({"title": "今週もお疲れ様です"}) == "今週もお疲れ様です"
    # 日文与中文并存：日文按既有优先级占标题段（且不被简体化），中文作拼接段并被简体化
    meta = {
        "title": "老师，这周也辛苦你了",
        "title_jpn": "先生、今週もお疲れ様、です",
    }
    assert build_name(meta) == "先生、今週もお疲れ様、です | 老师，这周也辛苦你了"


def test_to_simplified_helper():
    """_common.to_simplified 幂等且不动非中文。"""
    from _common import to_simplified

    assert to_simplified("老師，這週也辛苦你了") == "老师，这周也辛苦你了"
    assert to_simplified("老师，这周也辛苦你了") == "老师，这周也辛苦你了"
    assert to_simplified("") == ""
    assert to_simplified("Romaji Title") == "Romaji Title"


def test_fullwidth_pipe_and_miyabe():
    """全角 ｜ 照样拆分；作者 tags_artist 罗马音优先；拼接段中文优先于日文。"""
    meta = {
        "title": "Kimi to no Mousou Sketch｜与你的幻想素描",
        "title_jpn": "君との妄想スケッチ",
        "tags_artist": ["miyabe kiwi"],
    }
    assert build_name(meta) == "[miyabe kiwi] Kimi to no Mousou Sketch | 与你的幻想素描"


def test_extra_title_field():
    """title* 前缀的额外字段也会被纳入候选。"""
    meta = {
        "title": "",
        "title_jpn": "",
        "title_en": "Banana Milk",
        "tags_artist": [],
    }
    assert build_name(meta) == "Banana Milk"


def test_author_bracket_fallback():
    """无 tags_artist 时从标题括号剥离作者（社团丢弃）。"""
    meta = {
        "title": "[McNAIL Workshop (Cloth Tsugutoshi)] Anna, Kyou-chan to Naa",
        "title_jpn": "安娜与京香",
        "tags_artist": [],
    }
    assert build_name(meta) == "[Cloth Tsugutoshi] Anna, Kyou-chan to Naa | 安娜与京香"


def test_rename_single_gallery(tmp_path):
    meta = {
        "title": "[Kito Sakeru] Warau Kaseifuu~men for 3D (COMIC X-EROS #138) [Chinese] [Digital]",
        "title_jpn": "[鬼頭サケル] 笑ゥかせいふぅ～めん for 3D",
        "tags_artist": ["kito sakeru"],
    }
    d = make_gallery(tmp_path, "raw_dir", meta)
    run_ok("hentai_rename.py", str(d))
    out = tmp_path / "[kito sakeru] Warau Kaseifuu~men for 3D | 笑ゥかせいふぅ～めん for 3D"
    assert out.is_dir()
    assert (out / "001.jpg").is_file()  # 内容原样保留
    assert (out / "meta.json").is_file()


def test_rename_parent_dir(tmp_path):
    parent = tmp_path / "exhentai"
    parent.mkdir()
    make_gallery(parent, "g1", {"title": "My Stepmom and Her Friends",
                                "title_jpn": "となりの人妻", "tags_artist": []})
    make_gallery(parent, "g2", {"title": "Kimi to no Mousou Sketch｜与你的幻想素描",
                                "title_jpn": "x", "tags_artist": ["miyabe kiwi"]})
    run_ok("hentai_rename.py", str(parent))
    assert (parent / "となりの人妻").is_dir()
    assert (parent / "[miyabe kiwi] Kimi to no Mousou Sketch | 与你的幻想素描").is_dir()


def test_rename_no_metadata_uses_dirname(tmp_path):
    """无 json 按现名规范化：现名干净则原样保留，exit 0（处理过即成功）。"""
    d = tmp_path / "plain"
    d.mkdir()
    (d / "a.jpg").write_bytes(b"x")
    run_ok("hentai_rename.py", str(d))
    assert (d / "a.jpg").is_file()  # 名本就干净，无事发生


def test_rename_no_metadata_normalizes(tmp_path):
    """无 json 单本：现名里的语言标签照去、作者照拆。"""
    d = tmp_path / "[Kito Sakeru] Warau Kaseifuu~men for 3D [Chinese]"
    d.mkdir()
    (d / "001.jpg").write_bytes(b"x")
    run_ok("hentai_rename.py", str(d))
    out = tmp_path / "[Kito Sakeru] Warau Kaseifuu~men for 3D"
    assert out.is_dir()
    assert (out / "001.jpg").is_file()


def test_rename_parent_mixed_json_and_plain(tmp_path):
    """父目录下有 json / 无 json 的子目录都洗。"""
    parent = tmp_path / "lib"
    parent.mkdir()
    make_gallery(parent, "g1", {"title": "Banana Milk", "tags_artist": []})
    plain = parent / "[Kito Sakeru] Warau Kaseifuu~men for 3D [Chinese]"
    plain.mkdir()
    (plain / "001.jpg").write_bytes(b"x")
    run_ok("hentai_rename.py", str(parent))
    assert (parent / "Banana Milk").is_dir()
    assert (parent / "[Kito Sakeru] Warau Kaseifuu~men for 3D").is_dir()


def test_rename_empty_meta_skips(tmp_path):
    """有 json 但无有效标题：不改出 untitled，原样保留。"""
    d = make_gallery(tmp_path, "g", {"foo": "bar"})
    run_ok("hentai_rename.py", str(d))
    assert d.is_dir()
    assert not (tmp_path / "untitled").exists()


def test_lang_words_dont_eat_substrings():
    """语言词只去独立单词：Temptation / Digital Devil 不能被吃掉子串。"""
    assert cleanup_title("The Temptation of Azusa") == "The Temptation of Azusa"
    assert cleanup_title("Digital Devil Saga") == "Digital Devil Saga"
    assert cleanup_title("An Attempt at Love") == "An Attempt at Love"
    # 独立的标签词照样去
    assert cleanup_title("Warau Kaseifuu~men for 3D (COMIC X-EROS #138) [Chinese] [Digital]") == \
        "Warau Kaseifuu~men for 3D"


def test_tag_only_bracket_not_author():
    """纯语言标签括号（[Chinese]）不能当作者，无作者时作者段省略；
    拼接段有日文时优先日文。"""
    meta = {"title": "[Chinese] Kimi to no Mousou Sketch",
            "title_jpn": "君との妄想", "tags_artist": []}
    assert build_name(meta) == "Kimi to no Mousou Sketch | 君との妄想"


def test_rename_list_meta_skips(tmp_path):
    """metadata 不是 dict（如 list）：不崩溃，原样保留。"""
    d = tmp_path / "g"
    d.mkdir()
    (d / "meta.json").write_text("[1, 2]", encoding="utf-8")
    run_ok("hentai_rename.py", str(d))
    assert d.is_dir()
    assert not (tmp_path / "untitled").exists()


def test_double_bracket_author():
    """双层开头括号取后者（[社团] [作者] → 作者）。"""
    meta = {"title": "[Circle] [My Author] Some Title",
            "title_jpn": "", "tags_artist": []}
    assert build_name(meta) == "[My Author] Some Title"


def test_english_tag_stripped():
    """半角 (English)/(Translated) 与方括号版一样被去掉；实词不受影响。"""
    assert cleanup_title("Title (English)") == "Title"
    assert cleanup_title("Story (Translated)") == "Story"
    assert cleanup_title("The Temptation of Azusa") == "The Temptation of Azusa"


def test_move_to_dest_collision_suffix(tmp_path):
    """落盘撞名不覆盖：递增 (1) 后缀。"""
    work = tmp_path / "work"
    (work / "exhentai").mkdir(parents=True)
    (work / "exhentai" / "book").mkdir()
    dest = tmp_path / "dest"
    (dest / "exhentai" / "book").mkdir(parents=True)
    move_to_dest(work, dest)
    assert (dest / "exhentai" / "book").is_dir()
    assert (dest / "exhentai" / "book (1)").is_dir()


def test_rename_case_only_no_suffix(tmp_path):
    """仅大小写差异不打 (1) 后缀（大小写不敏感文件系统上 exists 会误报）。"""
    meta = {
        "title": "[kito sakeru] Warau Kaseifuu~men for 3D",
        "title_jpn": "[鬼頭サケル] 笑ゥかせいふぅ～めん for 3D",
        "tags_artist": ["kito sakeru"],
    }
    d = make_gallery(tmp_path, "[Kito Sakeru] Warau Kaseifuu~men for 3D | 笑ゥかせいふぅ～めん for 3D", meta)
    run_ok("hentai_rename.py", str(d))
    names = [p.name for p in tmp_path.iterdir() if p.is_dir()]
    assert len(names) == 1
    assert names[0] == "[kito sakeru] Warau Kaseifuu~men for 3D | 笑ゥかせいふぅ～めん for 3D"


def test_parody_bracket_stripped():
    """系列括号剥除（nhentai/comic-looms 实测用例；现在所有括号默认全去）。"""
    meta = {
        "title": "[pumpkinspice] Baikaen no Comic | 梅花园的小漫画 (Blue Archive) [Chinese] [欶澜汉化组]",
        "tags": {"parody": ["blue archive"]},
    }
    assert build_name(meta) == "[pumpkinspice] Baikaen no Comic | 梅花园的小漫画"


def test_all_brackets_stripped():
    """小括号/全角括号内容一律剥除（默认全去，白名单以后加）；语言词仍不吃子串。"""
    assert cleanup_title("梅花园的小漫画 (Blue Archive)") == "梅花园的小漫画"
    assert cleanup_title("Title (Boku no Yabai Yatsu)") == "Title"
    assert cleanup_title("Kimi to no Mousou（妄想番外編）") == "Kimi to no Mousou"
    assert cleanup_title("The Temptation of Azusa") == "The Temptation of Azusa"
    assert cleanup_title("Digital Devil Saga") == "Digital Devil Saga"
    meta = {
        "title": "Some Comic (Blue Archive)",
        "tags_parody": ["blue archive"],
    }
    assert build_name(meta) == "Some Comic"


def test_origin_title_japanese_fallback():
    """comic-looms 的 originTitle 提供日文候选：无中文时顶上拼接段。"""
    meta = {
        "title": "Baikaen no Comic",
        "originTitle": "[pumpkinspice] 梅花園のコミック",
        "tags_artist": [],
    }
    assert build_name(meta) == "[pumpkinspice] Baikaen no Comic | 梅花園のコミック"


def test_origin_title_loses_to_chinese():
    """拼接段中文优先：有中文时 originTitle 的日文不上。"""
    meta = {
        "title": "Baikaen no Comic | 梅花园的小漫画",
        "originTitle": "梅花園のコミック",
    }
    assert build_name(meta) == "Baikaen no Comic | 梅花园的小漫画"
