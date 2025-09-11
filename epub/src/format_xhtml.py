"""
EPUB XHTML文件格式化工具（支持文件名排序处理）
功能：
1. 按文件名顺序处理文件（从小到大）
2. 标准化头部声明（XML + DOCTYPE）
3. 修复自闭合标签并保持换行（特定条件下跳过）
4. 4空格缩进格式化（特定条件下跳过）
5. 将h2-span文本复制到title（特定条件下跳过）
6. 清理head部分
7. 特定卷/部/番外标题跳过body格式化和标题更新
"""
import os
import argparse
import re
from lxml import etree

# 需要保留换行的自闭合标签列表
LINE_PRESERVING_TAGS = {"p", "div", "span", "a", "ul", "li", "h1", "h2", "h3", "br"}

# 标准头部声明
STANDARD_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
STANDARD_DOCTYPE = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'

# 需要跳过body格式化的标题模式
SKIP_TITLE_PATTERNS = [
    r'^第[一二三四五六七八九十零百千万\d]+卷\s+.+',  # 第X卷 XXX
    r'^第[一二三四五六七八九十零百千万\d]+部\s+.+',  # 第X部 XXX
    r'^番外\s+.+',                      # 番外 XXX
    r'^第[一二三四五六七八九十零百千万\d]+卷$',   # 仅"第X卷"
    r'^第[一二三四五六七八九十零百千万\d]+部$',   # 仅"第X部"
    r'^番外$'                          # 仅"番外"
]

def should_skip_body_formatting(title_text):
    """检查标题是否符合跳过body格式化的条件"""
    if not title_text:
        return False
    title_text = title_text.strip()
    return any(re.match(pattern, title_text) for pattern in SKIP_TITLE_PATTERNS)

def extract_title_from_raw_content(content):
    """直接从原始内容中提取<title>标签内容"""
    title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    return title_match.group(1).strip() if title_match else None

def extract_declarations(content):
    """分离XML声明和DOCTYPE声明"""
    xml_declaration = ""
    doctype = ""
    body_start = 0

    xml_match = re.search(r'<\?xml[^>]*\?>', content)
    if xml_match:
        body_start = xml_match.end()
        xml_declaration = xml_match.group(0).strip()

    if body_start > 0:
        remaining = content[body_start:]
    else:
        remaining = content

    doctype_match = re.search(r'<!DOCTYPE[^>]+>', remaining, re.IGNORECASE)
    if doctype_match:
        doctype = doctype_match.group(0).strip()
        body_start += doctype_match.end()

    return xml_declaration, doctype, content[body_start:].lstrip()

def format_self_closing_tags(content):
    """预处理：保留特定自闭合标签的单独换行特性"""
    pattern = r'<([a-z]+:)?([a-z0-9]+)([^>]*)/>'

    def replace_tag(match):
        ns_prefix = match.group(1) or ""
        tag_name = match.group(2)
        attributes = match.group(3)

        if tag_name in LINE_PRESERVING_TAGS:
            start_pos = match.start()
            preceding_text = content[:start_pos]
            if "\n" in preceding_text:
                last_newline = preceding_text.rfind("\n")
                if not preceding_text[last_newline+1:start_pos].strip():
                    return f"<{ns_prefix}{tag_name}{attributes}></{ns_prefix}{tag_name}>"

        return match.group(0)

    return re.sub(pattern, replace_tag, content, flags=re.IGNORECASE)

def fix_self_closing_tags(root):
    """修复非空元素的自闭合标签"""
    non_void_elements = {"p", "div", "span", "a", "ul", "li", "h1", "h2", "h3"}

    for tag in root.iter():
        tag_name = tag.tag.split("}")[-1] if '}' in tag.tag else tag.tag
        if tag_name in non_void_elements and tag.text is None and len(tag) == 0:
            tag.text = ""

def standardize_html_tag(content):
    """确保<html>标签包含必要的属性和值"""
    html_match = re.search(r'<html\b([^>]*)>', content, re.IGNORECASE)
    if not html_match:
        return content

    html_attrs = html_match.group(1)
    attrs_dict = {}

    for attr_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', html_attrs):
        attrs_dict[attr_match.group(1).lower()] = attr_match.group(2)

    if "xmlns" not in attrs_dict:
        attrs_dict["xmlns"] = "http://www.w3.org/1999/xhtml"
    if "xml:lang" not in attrs_dict:
        attrs_dict["xml:lang"] = "zh-Hans"

    new_attrs = ' '.join([f'{k}="{v}"' for k, v in attrs_dict.items()])
    new_html_tag = f'<html {new_attrs}>'

    return content.replace(html_match.group(0), new_html_tag)

def clean_head_section(root, xhtml_ns):
    """清理head部分，只保留title和stylesheet链接"""
    head = root.find(f".//{{{xhtml_ns}}}head")
    if head is None:
        return

    elements_to_keep = []

    title = head.find(f".//{{{xhtml_ns}}}title")
    if title is not None:
        elements_to_keep.append(title)

    for link in head.findall(f".//{{{xhtml_ns}}}link"):
        rel_attr = link.get("rel", "").lower()
        if "stylesheet" in rel_attr:
            elements_to_keep.append(link)

    head.clear()
    for element in elements_to_keep:
        head.append(element)

def update_title_from_h2(root, xhtml_ns):
    """将h2-span文本复制到title标签"""
    head = root.find(f".//{{{xhtml_ns}}}head")
    if head is None:
        return

    title = head.find(f".//{{{xhtml_ns}}}title")
    if title is None:
        title = etree.Element(f"{{{xhtml_ns}}}title")
        head.insert(0, title)

    h2 = root.find(f".//{{{xhtml_ns}}}h2")
    if h2 is None:
        return

    span = h2.find(f".//{{{xhtml_ns}}}span")
    if span is not None and span.text:
        title.text = span.text.strip()
    elif h2.text:
        title.text = h2.text.strip()

def format_epub_xhtml_file(input_path, output_path, indent_size=4):
    """格式化EPUB XHTML文件（精确控制版）"""
    try:
        # 读取原始内容
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        # 提取原始标题
        raw_title = extract_title_from_raw_content(raw_content)
        skip_body_processing = should_skip_body_formatting(raw_title) if raw_title else False

        if skip_body_processing:
            print(f"⏩ 跳过body处理: {os.path.basename(input_path)} - '{raw_title}'")

        # 标准化<html>标签属性
        processed_content = standardize_html_tag(raw_content)

        # 分离声明与主体内容
        xml_decl, doctype, body_content = extract_declarations(processed_content)

        # 强制使用标准声明
        xml_decl = STANDARD_XML_DECLARATION
        doctype = STANDARD_DOCTYPE

        # ==== 关键修改：所有文件都解析文档 ====
        # 使用不改变空白的解析器
        parser = etree.XMLParser(
            remove_blank_text=False,
            resolve_entities=False,
            recover=True
        )

        # 创建包含完整文档的内容
        full_body = f"<root>{body_content}</root>"  # 包裹根元素确保解析有效
        root = etree.fromstring(full_body.encode('utf-8'), parser)

        # 获取实际使用的命名空间
        namespaces = root[0].nsmap if len(root) > 0 else {}
        xhtml_ns = namespaces.get(None, "http://www.w3.org/1999/xhtml")

        # 获取真正的html根元素
        html_root = root.find(f".//{{{xhtml_ns}}}html")
        if html_root is None:
            html_root = root.find(".//html") or root[0]

        # ==== 清理head部分（所有文件都执行） ====
        clean_head_section(html_root, xhtml_ns)

        # ==== 条件性更新标题 ====
        if not skip_body_processing:
            update_title_from_h2(html_root, xhtml_ns)

        # ==== 条件性body处理 ====
        if not skip_body_processing:
            # 处理自闭合标签
            processed_body = format_self_closing_tags(body_content)
            root = etree.fromstring(f"<root>{processed_body}</root>".encode('utf-8'), parser)
            html_root = root.find(f".//{{{xhtml_ns}}}html") or root[0]

            # 修复自闭合标签
            fix_self_closing_tags(html_root)

            # 应用缩进
            etree.indent(html_root, space=" " * indent_size)

        # 序列化主体
        serialized_body = etree.tostring(
            html_root,
            encoding="utf-8",
            xml_declaration=False,
            pretty_print=not skip_body_processing,
            method="xml"
        ).decode('utf-8')

        # 移除包裹的根元素
        if serialized_body.startswith('<root>'):
            serialized_body = serialized_body[6:-7]

        # 后处理：恢复单独成行的空标签
        if not skip_body_processing:
            serialized_body = re.sub(
                r'<(/?)(p|div|span|a|ul|li|h1|h2|h3|br)([^>]*)>\s*</\2>',
                r'<\1\2\3></\2>', 
                serialized_body
            )

        # 组合最终内容
        full_content = f"{xml_decl}\n{doctype}\n{serialized_body}"

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)

        return True, None

    except Exception as e:
        return False, f"解析失败: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='EPUB XHTML文件批量格式化（按文件名排序）')
    parser.add_argument('source_dir', help='源文件目录')
    parser.add_argument('--indent', type=int, default=4, help='缩进空格数（默认4）')
    args = parser.parse_args()

    # 创建输出目录
    source_dir = os.path.abspath(args.source_dir)
    base_name = os.path.basename(source_dir)
    parent_dir = os.path.dirname(source_dir)
    output_dir = os.path.join(parent_dir, f"{base_name}_formatted")
    os.makedirs(output_dir, exist_ok=True)

    print(f"🔍🔍 扫描目录: {source_dir}")
    print(f"📂📂 输出目录: {output_dir}")
    errors = []

    # 获取所有XHTML文件
    file_list = []
    for filename in os.listdir(source_dir):
        if filename.lower().endswith(('.xhtml', '.html', '.xml')):
            file_list.append(filename)

    # 按文件名自然排序
    file_list.sort(key=lambda f: [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', f)])

    print(f"📊📊 找到 {len(file_list)} 个文件，按文件名排序处理...")

    for filename in file_list:
        input_file = os.path.join(source_dir, filename)
        output_file = os.path.join(output_dir, filename)

        success, error = format_epub_xhtml_file(input_file, output_file, args.indent)

        if success:
            print(f"✅ 成功: {filename}")
        else:
            print(f"❌❌ 失败: {filename} - {error}")
            errors.append(filename)

    print(f"\n🎉🎉 完成！处理文件: {len(file_list) - len(errors)}/{len(file_list)} 个")
    if errors:
        print(f"⚠️ 失败文件: {', '.join(errors)}")

if __name__ == "__main__":
    main()