#!/usr/bin/env python3
"""生成 EPUB 的 content.opf（书目清单：manifest + spine）。

替代原 shell script/content_opf_generate.sh：纯字符串模板生成，
不再依赖 xmlstarlet 与 uuidgen。

输出与旧 shell 版**严格等价**：元数据保持空标签（dc:title 等留空由后续
手工填写）、4 个空 dc:subject、固定 zh-CN / novel，仅 UUID 每次新生成。

生成的 UUID 会同步写入已存在的 toc.ncx（dtb:uid），原文件备份为 .bak。
"""
import argparse
import re
import sys
import uuid
from pathlib import Path

NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

OPF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uuid_id">
    <metadata xmlns:opf="http://www.idpf.org/2007/opf"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier opf:scheme="uuid" id="uuid_id">{uuid}</dc:identifier>
        <dc:title></dc:title>
        <dc:creator opf:role="aut" opf:file-as=""></dc:creator>
        <dc:description></dc:description>
        <dc:subject></dc:subject>
        <dc:subject></dc:subject>
        <dc:subject></dc:subject>
        <dc:subject></dc:subject>
        <dc:date></dc:date>
        <dc:language>zh-CN</dc:language>
        <dc:format>application/epub+zip</dc:format>
        <dc:type>novel</dc:type>
        <meta name="cover" content="cover"/>
    </metadata>
    <manifest>
        <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="cover" href="cover.jpg" media-type="image/jpeg"/>
        <item id="style" href="style.css" media-type="text/css"/>
{manifest_items}    </manifest>
    <spine toc="toc">
        <itemref idref="cover" linear="no"/>
{spine_items}    </spine>
</package>
"""

# toc.ncx 里 dtb:uid 的 content 属性（uuid 形态，如 7DAA2FB1-6D5C-42A1-...）
UID_PATTERN = re.compile(
    r'(<meta\s+name="dtb:uid"\s+content=")([^"]*)(")',
)


def list_xhtml_ids(text_dir: Path) -> list[str]:
    """列出 Text/ 下 *.xhtml 的文件名（不含扩展名，即 manifest 的 id）。"""
    if not text_dir.is_dir():
        return []
    return sorted(p.stem for p in text_dir.glob("*.xhtml") if p.is_file())


def build_opf(ids: list[str], uid: str) -> str:
    """按 ids 生成 content.opf 文本。"""
    manifest_items = "".join(
        f'        <item id="{i}" href="Text/{i}.xhtml" '
        f'media-type="application/xhtml+xml"/>\n'
        for i in ids
    )
    spine_items = "".join(
        f'        <itemref idref="{i}" linear="yes"/>\n' for i in ids
    )
    return OPF_TEMPLATE.format(
        uuid=uid, manifest_items=manifest_items, spine_items=spine_items)


def update_toc_uid(toc_file: Path, uid: str) -> bool:
    """把 toc.ncx 里的 dtb:uid 换成 uid，原文件备份为 .bak。返回是否成功。"""
    try:
        text = toc_file.read_text(encoding="utf-8")
    except OSError:
        return False
    new_text, n = UID_PATTERN.subn(rf"\g<1>{uid}\g<3>", text)
    if n == 0:
        return False
    toc_file.with_suffix(toc_file.suffix + ".bak").write_text(text, encoding="utf-8")
    toc_file.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 EPUB 的 content.opf（manifest + spine）")
    parser.add_argument("target_dir", help="目标文件夹路径（内含 Text/*.xhtml）")
    args = parser.parse_args()

    target = Path(args.target_dir).expanduser().resolve()
    if not target.is_dir():
        print(f"错误: 文件夹 '{target}' 不存在")
        sys.exit(1)

    # uuidgen 默认输出大写带破折号的 UUID，保持同形态
    uid = str(uuid.uuid4()).upper()

    ids = list_xhtml_ids(target / "Text")
    if not ids:
        print(f"警告: 未找到Text文件夹 '{target / 'Text'}'，可能导致manifest不完整")

    opf_file = target / "content.opf"
    opf_file.write_text(build_opf(ids, uid), encoding="utf-8")
    print(f"已生成: {opf_file}")
    print(f"使用的UUID: {uid}")

    toc_file = target / "toc.ncx"
    if toc_file.is_file():
        if update_toc_uid(toc_file, uid):
            print(f"已更新toc.ncx中的UUID: {uid}")
            print(f"原始文件备份为: {toc_file}.bak")
        else:
            print("错误: 更新toc.ncx文件失败")
            print("请检查文件格式或手动更新")
    else:
        print("注意: 未找到toc.ncx文件，未进行UUID更新")


if __name__ == "__main__":
    main()
