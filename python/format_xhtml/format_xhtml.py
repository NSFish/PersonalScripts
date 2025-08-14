#!/usr/bin/env python3

"""
EPUB XHTML文件格式化工具（支持文件名排序处理）
功能：
1. 按文件名顺序处理文件（从小到大）
2. 标准化头部声明（XML + DOCTYPE）
3. 修复自闭合标签并保持换行
4. 4空格缩进格式化
5. 将h2-span文本复制到title
6. 清理head部分
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
STANDARD_HTML_ATTRS = 'xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-Hans"'

# XHTML命名空间
XHTML_NS = "http://www.w3.org/1999/xhtml"

def extract_declarations(content):
    """分离XML声明和DOCTYPE声明（修复版）"""
    xml_declaration = ""
    doctype = ""
    body_start = 0
    
    # 查找第一个有效的XML声明位置（忽略前面的非法内容）
    xml_match = re.search(r'<\?xml[^>]*\?>', content)
    if xml_match:
        # 移除声明前所有内容（包括非法标签）
        body_start = xml_match.end()
        xml_declaration = xml_match.group(0).strip()
    
    # 在XML声明后查找DOCTYPE
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
    
    # 提取现有属性
    for attr_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', html_attrs):
        attrs_dict[attr_match.group(1).lower()] = attr_match.group(2)
    
    # 确保必要属性存在
    if "xmlns" not in attrs_dict:
        attrs_dict["xmlns"] = "http://www.w3.org/1999/xhtml"
    if "xml:lang" not in attrs_dict:
        attrs_dict["xml:lang"] = "zh-Hans"
    
    # 重建<html>标签
    new_attrs = ' '.join([f'{k}="{v}"' for k, v in attrs_dict.items()])
    new_html_tag = f'<html {new_attrs}>'
    
    return content.replace(html_match.group(0), new_html_tag)

def clean_head_section(root):
    """清理head部分，只保留title和stylesheet链接"""
    # 查找head元素
    head = root.find(f".//{{{XHTML_NS}}}head")
    if head is None:
        return
    
    # 保留的元素列表
    elements_to_keep = []
    
    # 查找现有的title元素
    title = head.find(f".//{{{XHTML_NS}}}title")
    if title is not None:
        elements_to_keep.append(title)
    
    # 查找所有样式表链接
    for link in head.findall(f".//{{{XHTML_NS}}}link"):
        rel_attr = link.get("rel", "").lower()
        if "stylesheet" in rel_attr:
            elements_to_keep.append(link)
    
    # 清空head并重新添加要保留的元素
    head.clear()
    for element in elements_to_keep:
        head.append(element)

def update_title_from_h2(root):
    """将h2-span文本复制到title标签"""
    # 查找head中的title元素
    head = root.find(f".//{{{XHTML_NS}}}head")
    if head is None:
        return
    
    title = head.find(f".//{{{XHTML_NS}}}title")
    if title is None:
        title = etree.Element(f"{{{XHTML_NS}}}title")
        head.insert(0, title)
    
    # 查找第一个h2元素
    h2 = root.find(f".//{{{XHTML_NS}}}h2")
    if h2 is None:
        return
    
    # 查找h2中的第一个span
    span = h2.find(f".//{{{XHTML_NS}}}span")
    if span is not None and span.text:
        title.text = span.text.strip()
    elif h2.text:
        title.text = h2.text.strip()

def format_epub_xhtml_file(input_path, output_path, indent_size=4):
    """格式化EPUB XHTML文件（修复版）"""
    try:
        # 文本模式读取
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        # 标准化<html>标签属性
        raw_content = standardize_html_tag(raw_content)
        
        # 分离声明与主体内容
        xml_decl, doctype, body_content = extract_declarations(raw_content)
        
        # 强制使用标准声明
        xml_decl = STANDARD_XML_DECLARATION
        doctype = STANDARD_DOCTYPE
        
        # 处理自闭合标签
        processed_body = format_self_closing_tags(body_content)
        
        # 解析XML主体
        parser = etree.XMLParser(
            remove_blank_text=True,
            resolve_entities=False,
            recover=True
        )
        
        # 将处理后的内容编码回UTF-8
        processed_bytes = processed_body.encode('utf-8')
        root = etree.fromstring(processed_bytes, parser)
        
        # 修复自闭合标签
        fix_self_closing_tags(root)
        
        # 清理head部分
        clean_head_section(root)
        
        # 更新title内容
        update_title_from_h2(root)
        
        # 应用缩进
        etree.indent(root, space=" " * indent_size)
        
        # 序列化主体
        formatted_body = etree.tostring(
            root,
            encoding="utf-8",
            xml_declaration=False,
            pretty_print=True,
            method="xml"
        ).decode('utf-8')
        
        # 后处理：恢复单独成行的空标签
        formatted_body = re.sub(
            r'<(/?)(p|div|span|a|ul|li|h1|h2|h3|br)([^>]*)>\s*</\2>',
            r'<\1\2\3></\2>', 
            formatted_body
        )
        
        # 组合最终内容
        full_content = f"{xml_decl}\n{doctype}\n{formatted_body}"
        
        # 文本模式写入
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
            
        return True, None
        
    except Exception as e:
        return False, f"解析失败: {str(e)}"

if __name__ == "__main__":
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
    
    print(f"🔍 扫描目录: {source_dir}")
    print(f"📂 输出目录: {output_dir}")
    errors = []
    
    # 获取所有XHTML文件（保留原始扩展名）
    file_list = []
    for filename in os.listdir(source_dir):
        if filename.lower().endswith(('.xhtml', '.html', '.xml')):
            file_list.append(filename)
    
    # 按文件名自然排序
    file_list.sort(key=lambda f: [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', f)])
    
    print(f"📊 找到 {len(file_list)} 个文件，按文件名排序处理...")
    
    for filename in file_list:
        input_file = os.path.join(source_dir, filename)
        # 保持原始文件扩展名
        output_file = os.path.join(output_dir, filename)
        
        success, error = format_epub_xhtml_file(input_file, output_file, args.indent)
        
        if success:
            print(f"✅ 成功: {filename}")
        else:
            print(f"❌ 失败: {filename} - {error}")
            errors.append(filename)
    
    print(f"\n🎉 完成！处理文件: {len(file_list) - len(errors)}/{len(file_list)} 个")
    if errors:
        print(f"⚠️ 失败文件: {', '.join(errors)}")