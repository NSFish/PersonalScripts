#!/opt/homebrew/bin/bash

# 检查是否提供了文件夹路径参数
if [ $# -ne 1 ]; then
    echo "使用方法: $0 <xhtml 文件夹路径>"
    exit 1
fi

XHTML_DIR="$1"

# 检查文件夹是否存在
if [ ! -d "$XHTML_DIR" ]; then
    echo "错误: 文件夹 '$XHTML_DIR' 不存在"
    exit 1
fi

# 获取传入文件夹的父目录
PARENT_DIR=$(dirname "$(realpath "$XHTML_DIR")")
if [ -z "$PARENT_DIR" ]; then
    echo "错误: 无法获取文件夹的父目录"
    exit 1
fi

# 获取文件夹基名用于路径前缀
FOLDER_NAME=$(basename "$XHTML_DIR")

# 检查是否安装了 xmlstarlet
if ! command -v xmlstarlet &> /dev/null; then
    echo "错误: 未找到 xmlstarlet，请先使用 'brew install xmlstarlet' 安装"
    exit 1
fi

# 获取所有 xhtml 文件并按文件名排序
XHTML_FILES=$(find "$XHTML_DIR" -maxdepth 1 -type f -name "*.xhtml" | sort)

# 检查是否有 xhtml 文件
if [ -z "$XHTML_FILES" ]; then
    echo "错误: 在 '$XHTML_DIR' 中未找到任何 xhtml 文件"
    exit 1
fi

# 初始化计数器
volume_count=0
chapter_count=0
playorder=0
current_volume_id=""

# 用于存储当前卷的章节内容
current_volume_chapters=$(mktemp)

# 临时文件用于存储导航点数据
navpoints=$(mktemp)

# 处理每个 xhtml 文件
while IFS= read -r file; do
    # 提取文件名（用于 href）
    filename=$(basename "$file")
    
    # 使用 xmlstarlet 提取 title 内容
    title=$(xmlstarlet sel -N xhtml="http://www.w3.org/1999/xhtml" \
              -t -v "/xhtml:html/xhtml:head/xhtml:title" "$file" 2>/dev/null)
    
    if [ -z "$title" ]; then
        echo "警告: 无法从文件 '$filename' 中提取标题，已跳过"
        continue
    fi
    
    # 增加 playorder
    playorder=$((playorder + 1))
    
    # 判断是卷还是章，使用严格的匹配规则
    # 要求"第"和"卷"之间不能有空格
    if echo "$title" | grep -qP '^第[^ 章]+卷$'; then
        # 如果当前有未完成的卷，先关闭它
        if [ -n "$current_volume_id" ]; then
            # 写入当前卷的所有章节
            cat "$current_volume_chapters" >> "$navpoints"
            # 关闭当前卷（与卷开始标签同级缩进）
            echo "        </navPoint>" >> "$navpoints"
            # 清空章节临时文件
            > "$current_volume_chapters"
        fi
        
        # 处理新卷（分卷 navPoint 比 navMap 多缩进 4 空格）
        volume_count=$((volume_count + 1))
        volume_id=$(printf "volume_%03d" $volume_count)
        current_volume_id=$volume_id
        
        # 卷开始标签：在 navMap 内缩进 4 空格（相对于 ncx 总缩进 8 空格）
        echo "        <navPoint id=\"$volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
        # 卷内元素：比卷多缩进 4 空格（共 12 空格）
        echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
        # 修改路径：添加文件夹名前缀
        echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
    
    # 要求"第"和"章"之间不能有空格
    elif echo "$title" | grep -qP '^第[^ 卷]+章'; then
        # 处理章
        chapter_count=$((chapter_count + 1))
        chapter_id=$(printf "chapter_%03d" $chapter_count)
        
        # 如果有当前卷，章节属于卷
        if [ -n "$current_volume_id" ]; then
            # 章节标签：比卷多缩进 4 空格（共 12 空格）
            echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
            # 章节内元素：比章节多缩进 4 空格（共 16 空格）
            echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
            echo "                <content src=\"$FOLDER_NAME/$filename\"/>" >> "$current_volume_chapters"
            echo "            </navPoint>" >> "$current_volume_chapters"
        else
            # 没有卷，章节直接作为 navMap 子节点（缩进 8 空格）
            echo "        <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$navpoints"
            echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
            echo "        </navPoint>" >> "$navpoints"
        fi
        
    else
        # 无法分辨的标题，当作章节处理
        echo "注意: 文件 '$filename' 的标题 '$title' 无法分辨类型，当作章节处理"
        chapter_count=$((chapter_count + 1))
        chapter_id=$(printf "chapter_%03d" $chapter_count)
        
        # 如果有当前卷，章节属于卷
        if [ -n "$current_volume_id" ]; then
            # 章节标签：比卷多缩进 4 空格（共 12 空格）
            echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
            # 章节内元素：比章节多缩进 4 空格（共 16 空格）
            echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
            echo "                <content src=\"$FOLDER_NAME/$filename\"/>" >> "$current_volume_chapters"
            echo "            </navPoint>" >> "$current_volume_chapters"
        else
            # 没有卷，章节直接作为 navMap 子节点（缩进 8 空格）
            echo "        <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$navpoints"
            echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
            echo "        </navPoint>" >> "$navpoints"
        fi
    fi
done <<< "$XHTML_FILES"

# 处理最后一个未关闭的卷
if [ -n "$current_volume_id" ]; then
    # 写入最后一卷的所有章节
    cat "$current_volume_chapters" >> "$navpoints"
    # 关闭最后一卷（与开始标签同级缩进）
    echo "        </navPoint>" >> "$navpoints"
fi

# 清理章节临时文件
rm "$current_volume_chapters"

# 生成 toc.ncx 文件（确保 ncx 子节点缩进统一）
cat << EOF > "$PARENT_DIR/toc.ncx"
<?xml version="1.0" encoding="utf-8" standalone="no"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content=""/>
        <meta name="dtb:depth" content="$((volume_count > 0 ? 2 : 1))"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle>
        <text>目录</text>
    </docTitle>
    <navMap>
$(cat "$navpoints")
    </navMap>
</ncx>
EOF

# 清理临时文件
rm "$navpoints"

# 输出结果信息
echo "已在 '$PARENT_DIR' 目录生成 toc.ncx 文件，包含:"
[ $volume_count -gt 0 ] && echo " - $volume_count 个分卷"
echo " - $chapter_count 个章节"