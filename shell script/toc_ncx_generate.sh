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
XHTML_FILES=()
while IFS= read -r -d $'\0' file; do
    XHTML_FILES+=("$file")
done < <(find "$XHTML_DIR" -maxdepth 1 -type f -name "*.xhtml" -print0 | sort -z)

# 检查是否有 xhtml 文件
if [ ${#XHTML_FILES[@]} -eq 0 ]; then
    echo "错误: 在 '$XHTML_DIR' 中未找到任何 xhtml 文件"
    exit 1
fi

# 初始化计数器
volume_count=0
chapter_count=0
playorder=0
current_volume_id=""
volume_part_count=0
extra_count=0

# 用于存储当前卷的章节内容
current_volume_chapters=$(mktemp)

# 临时文件用于存储导航点数据
navpoints=$(mktemp)

# 获取文件总数，用于确定章节ID宽度
total_chapters=${#XHTML_FILES[@]}
# 计算ID宽度（总章节数的位数）
if [ $total_chapters -lt 10 ]; then
    chapter_width=1
elif [ $total_chapters -lt 100 ]; then
    chapter_width=2
elif [ $total_chapters -lt 1000 ]; then
    chapter_width=3
elif [ $total_chapters -lt 10000 ]; then
    chapter_width=4
elif [ $total_chapters -lt 100000 ]; then
    chapter_width=5
else
    chapter_width=6
fi

# 处理每个 xhtml 文件
for file in "${XHTML_FILES[@]}"; do
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
    
    # 判断是卷/部/番外还是章
    # 卷/部：要求"第X卷/部"后必须跟空格或结束
    if echo "$title" | grep -qP '^第[^ ]+[卷部](\s|$)'; then
        volume_part_count=$((volume_part_count + 1))
        # 如果当前有未完成的卷，先关闭它
        if [ -n "$current_volume_id" ]; then
            # 写入当前卷的所有章节
            cat "$current_volume_chapters" >> "$navpoints"
            # 关闭当前卷
            echo "        </navPoint>" >> "$navpoints"
            # 清空章节临时文件
            > "$current_volume_chapters"
        fi
        
        # 处理新卷（卷、部、番外统一使用volume_前缀）
        volume_count=$((volume_count + 1))
        # 卷ID固定为2位数字（最多99卷）
        volume_id=$(printf "volume_%02d" $volume_count)
        current_volume_id=$volume_id
        
        # 卷开始标签
        echo "        <navPoint id=\"$volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
        echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
        echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
    
    # 番外：要求"番外"后必须跟空格或结束
    elif echo "$title" | grep -qP '^番外(\s|$)'; then
        extra_count=$((extra_count + 1))
        # 如果当前有未完成的卷，先关闭它
        if [ -n "$current_volume_id" ]; then
            # 写入当前卷的所有章节
            cat "$current_volume_chapters" >> "$navpoints"
            # 关闭当前卷
            echo "        </navPoint>" >> "$navpoints"
            # 清空章节临时文件
            > "$current_volume_chapters"
        fi
        
        # 处理番外（与卷/部同级）
        volume_count=$((volume_count + 1))
        # 番外ID固定为2位数字（最多99卷）
        volume_id=$(printf "volume_%02d" $volume_count)
        current_volume_id=$volume_id
        
        # 番外开始标签
        echo "        <navPoint id=\"$volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
        echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
        echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
    
    # 章识别
    elif echo "$title" | grep -qP '^第[^ ]+章(\s|$)'; then
        # 处理章
        chapter_count=$((chapter_count + 1))
        # 章节ID宽度根据总章节数动态确定
        chapter_id=$(printf "chapter_%0${chapter_width}d" $chapter_count)
        
        # 如果有当前卷/番外，章节属于它
        if [ -n "$current_volume_id" ]; then
            # 章节标签：比卷多缩进 4 空格
            echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
            echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
            echo "                <content src=\"$FOLDER_NAME/$filename\"/>" >> "$current_volume_chapters"
            echo "            </navPoint>" >> "$current_volume_chapters"
        else
            # 没有卷，章节直接作为 navMap 子节点
            echo "        <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$navpoints"
            echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
            echo "        </navPoint>" >> "$navpoints"
        fi
        
    else
        # 无法分辨的标题，当作章节处理
        echo "注意: 文件 '$filename' 的标题 '$title' 无法分辨类型，当作章节处理"
        chapter_count=$((chapter_count + 1))
        chapter_id=$(printf "chapter_%0${chapter_width}d" $chapter_count)
        
        # 如果有当前卷/番外，章节属于它
        if [ -n "$current_volume_id" ]; then
            # 章节标签：比卷多缩进 4 空格
            echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
            echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
            echo "                <content src=\"$FOLDER_NAME/$filename\"/>" >> "$current_volume_chapters"
            echo "            </navPoint>" >> "$current_volume_chapters"
        else
            # 没有卷，章节直接作为 navMap 子节点
            echo "        <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$navpoints"
            echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$FOLDER_NAME/$filename\"/>" >> "$navpoints"
            echo "        </navPoint>" >> "$navpoints"
        fi
    fi
done

# 处理最后一个未关闭的卷/番外
if [ -n "$current_volume_id" ]; then
    # 写入最后一卷的所有章节
    cat "$current_volume_chapters" >> "$navpoints"
    # 关闭最后一卷
    echo "        </navPoint>" >> "$navpoints"
fi

# 清理章节临时文件
rm "$current_volume_chapters"

# 生成 toc.ncx 文件
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
if [ $volume_count -gt 0 ]; then
    # 输出统计信息
    if [ $volume_part_count -gt 0 ] && [ $extra_count -gt 0 ]; then
        echo " - $volume_count 个分部 ($volume_part_count 个卷/部 + $extra_count 个番外)"
    elif [ $volume_part_count -gt 0 ]; then
        # 确定是卷还是部
        if find "$XHTML_DIR" -maxdepth 1 -type f -name "*.xhtml" -exec grep -qP '^第[^ ]+卷(\s|$)' {} \; ; then
            echo " - $volume_count 个分卷"
        else
            echo " - $volume_count 个分部"
        fi
    elif [ $extra_count -gt 0 ]; then
        echo " - $volume_count 个番外"
    else
        echo " - $volume_count 个分部"
    fi
fi
echo " - $chapter_count 个章节 (ID宽度: $chapter_width)"