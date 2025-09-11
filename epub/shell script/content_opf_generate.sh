#!/bin/bash

# 检查是否提供了目标文件夹参数
if [ $# -ne 1 ]; then
    echo "使用方法: $0 <目标文件夹路径>"
    exit 1
fi

# 检查目标文件夹是否存在
TARGET_DIR="$1"
if [ ! -d "$TARGET_DIR" ]; then
    echo "错误: 文件夹 '$TARGET_DIR' 不存在"
    exit 1
fi

# 检查是否安装了必要工具
if ! command -v xmlstarlet &> /dev/null; then
    echo "Error: xmlstarlet not found. Please install it first with:"
    echo "brew install xmlstarlet"
    exit 1
fi

# 生成UUID (保留破折号，使用默认格式)
NEW_UUID=$(uuidgen)

# 定义content.opf文件路径
OPF_FILE="$TARGET_DIR/content.opf"

# 创建content.opf文件头部（包含新生成的UUID）
cat > "$OPF_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uuid_id">
    <metadata xmlns:opf="http://www.idpf.org/2007/opf"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier opf:scheme="uuid" id="uuid_id">$NEW_UUID</dc:identifier>
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
EOF

# 按顺序添加manifest项：toc、cover、css
echo "        <item id=\"toc\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\"/>" >> "$OPF_FILE"
echo "        <item id=\"cover\" href=\"cover.jpg\" media-type=\"image/jpeg\"/>" >> "$OPF_FILE"
echo "        <item id=\"style\" href=\"style.css\" media-type=\"text/css\"/>" >> "$OPF_FILE"

# 遍历目标文件夹下的Text子文件夹中的XHTML文件添加到manifest（放在最后）
TEXT_DIR="$TARGET_DIR/Text"
if [ -d "$TEXT_DIR" ]; then
    for xhtml_file in "$TEXT_DIR"/*.xhtml; do
        if [ -f "$xhtml_file" ]; then
            # 获取文件名（不含路径和扩展名）
            filename=$(basename "$xhtml_file")
            item_id="${filename%.xhtml}"
            echo "        <item id=\"$item_id\" href=\"Text/$filename\" media-type=\"application/xhtml+xml\"/>" >> "$OPF_FILE"
        fi
    done
else
    echo "警告: 未找到Text文件夹 '$TEXT_DIR'，可能导致manifest不完整"
fi

# 继续添加spine部分（已移除guide部分）
cat >> "$OPF_FILE" <<EOF
    </manifest>
    <spine toc="toc">
        <itemref idref="cover" linear="no"/>
EOF

# 遍历目标文件夹下的Text子文件夹中的XHTML文件添加到spine
if [ -d "$TEXT_DIR" ]; then
    for xhtml_file in "$TEXT_DIR"/*.xhtml; do
        if [ -f "$xhtml_file" ]; then
            filename=$(basename "$xhtml_file")
            item_id="${filename%.xhtml}"
            # 为每个xhtml文件添加linear="yes"属性
            echo "        <itemref idref=\"$item_id\" linear=\"yes\"/>" >> "$OPF_FILE"
        fi
    done
fi

# 直接结束spine和package部分（已移除guide）
cat >> "$OPF_FILE" <<EOF
    </spine>
</package>
EOF

echo "已生成: $OPF_FILE"
echo "使用的UUID: $NEW_UUID"

# 检查并更新toc.ncx文件
TOC_FILE="$TARGET_DIR/toc.ncx"
if [ -f "$TOC_FILE" ]; then
    # 备份原始文件
    cp "$TOC_FILE" "${TOC_FILE}.bak"
    
    # 更新toc.ncx中的UUID
    xmlstarlet ed -L -N ncx="http://www.daisy.org/z3986/2005/ncx/" \
        --update '//ncx:meta[@name="dtb:uid"]/@content' \
        --value "$NEW_UUID" \
        "$TOC_FILE"
    
    # 检查更新是否成功
    if [ $? -eq 0 ]; then
        echo "已更新toc.ncx中的UUID: $NEW_UUID"
        echo "原始文件备份为: ${TOC_FILE}.bak"
    else
        echo "错误: 更新toc.ncx文件失败"
        echo "请检查文件格式或手动更新"
    fi
else
    echo "注意: 未找到toc.ncx文件，未进行UUID更新"
fi