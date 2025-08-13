#!/bin/bash

# 检查是否提供了文件夹路径参数
if [ $# -ne 1 ]; then
    echo "使用方法: $0 <xhtml文件夹路径>"
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
# 检查是否安装了xmlstarlet
if ! command -v xmlstarlet &> /dev/null; then
    echo "错误: 未找到xmlstarlet，请先使用 'brew install xmlstarlet' 安装"
    exit 1
fi
# 获取所有xhtml文件并按文件名排序
XHTML_FILES=$(find "$XHTML_DIR" -maxdepth 1 -type f -name "*.xhtml" | sort)
# 检查是否有xhtml文件
if [ -z "$XHTML_FILES" ]; then
    echo "错误: 在 '$XHTML_DIR' 中未找到任何xhtml文件"
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
# 处理每个xhtml文件
while IFS= read -r file; do
    # 提取文件名（用于href）
    filename=$(basename "$file")
    
    # 使用xmlstarlet提取title内容
    title=$(xmlstarlet sel -N xhtml="http://www.w3.org/1999/xhtml" \
              -t -v "/xhtml:html/xhtml:head/xhtml:title" "$file" 2>/dev/null)
    
    if [ -z "$title" ]; then
        echo "警告: 无法从文件 '$filename' 中提取标题，已跳过"
        continue
    fi
    
    # 增加playorder
    playorder=$((playorder + 1))
    
    # 判断是卷还是章，无法分辨的当作章节处理
    if echo "$title" | grep -q "第.*卷"; then
        # 如果当前有未完成的卷，先关闭它
        if [ -n "$current_volume_id" ]; then
            # 写入当前卷的所有章节
            cat "$current_volume_chapters" >> "$navpoints"
            # 关闭当前卷（与卷开始标签同级缩进）
            echo "        </navPoint>" >> "$navpoints"
            # 清空章节临时文件
            > "$current_volume_chapters"
        fi
        
        # 处理新卷（分卷navPoint比navMap多缩进4空格）
        volume_count=$((volume_count + 1))
        volume_id=$(printf "volume_%03d" $volume_count)
        current_volume_id=$volume_id
        
        # 卷开始标签：在navMap内缩进4空格（相对于ncx总缩进8空格）
        echo "        <navPoint id=\"$volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
        # 卷内元素：比卷多缩进4空格（共12空格）
        echo "            <navLabel><text>$title</text></navLabel>" >> "$navpoints"
        echo "            <content src=\"$filename\"/>" >> "$navpoints"
        
    elif echo "$title" | grep -q "第.*章"; then
        # 处理章
        chapter_count=$((chapter_count + 1))
        chapter_id=$(printf "chapter_%03d" $chapter_count)
        
        # 如果没有当前卷，创建一个默认卷
        if [ -z "$current_volume_id" ]; then
            volume_count=$((volume_count + 1))
            current_volume_id=$(printf "volume_%03d" $volume_count)
            # 默认卷开始标签：在navMap内缩进4空格
            echo "        <navPoint id=\"$current_volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
            # 默认卷内元素：缩进12空格
            echo "            <navLabel><text>默认卷</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$filename\"/>" >> "$navpoints"
            playorder=$((playorder + 1))
        fi
        
        # 章节标签：比卷多缩进4空格（共12空格）
        echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
        # 章节内元素：比章节多缩进4空格（共16空格）
        echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
        echo "                <content src=\"$filename\"/>" >> "$current_volume_chapters"
        echo "            </navPoint>" >> "$current_volume_chapters"
        
    else
        # 无法分辨的标题，当作章节处理
        echo "注意: 文件 '$filename' 的标题 '$title' 无法分辨类型，当作章节处理"
        chapter_count=$((chapter_count + 1))
        chapter_id=$(printf "chapter_%03d" $chapter_count)
        
        # 如果没有当前卷，创建一个默认卷
        if [ -z "$current_volume_id" ]; then
            volume_count=$((volume_count + 1))
            current_volume_id=$(printf "volume_%03d" $volume_count)
            # 默认卷开始标签：在navMap内缩进4空格
            echo "        <navPoint id=\"$current_volume_id\" playOrder=\"$playorder\">" >> "$navpoints"
            # 默认卷内元素：缩进12空格
            echo "            <navLabel><text>默认卷</text></navLabel>" >> "$navpoints"
            echo "            <content src=\"$filename\"/>" >> "$navpoints"
            playorder=$((playorder + 1))
        fi
        
        # 章节标签：比卷多缩进4空格（共12空格）
        echo "            <navPoint id=\"$chapter_id\" playOrder=\"$playorder\">" >> "$current_volume_chapters"
        # 章节内元素：比章节多缩进4空格（共16空格）
        echo "                <navLabel><text>$title</text></navLabel>" >> "$current_volume_chapters"
        echo "                <content src=\"$filename\"/>" >> "$current_volume_chapters"
        echo "            </navPoint>" >> "$current_volume_chapters"
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
# 生成toc.ncx文件（确保ncx子节点缩进统一）
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
echo "已在 '$PARENT_DIR' 目录生成 toc.ncx 文件，包含:"
echo " - $volume_count 个分卷"
echo " - $chapter_count 个章节"