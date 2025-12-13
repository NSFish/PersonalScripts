#!/opt/homebrew/bin/bash

# ==============================================
# macOS 图片宽度检测脚本（优化版）
# 功能：统计指定文件夹中图片的主流宽度，并按文件名排序列出不符合的图片
# 支持格式：jpg/jpeg/png/gif/bmp/tiff 等 sips 支持的图片格式
# ==============================================

# 检查参数是否正确
if [ $# -ne 1 ]; then
    echo "用法：$0 <图片文件夹路径>"
    echo "示例：$0 ~/Pictures/my_images"
    exit 1
fi

# 定义目标文件夹（处理绝对路径/相对路径）
TARGET_DIR=$(cd "$1" 2>/dev/null && pwd)
if [ -z "$TARGET_DIR" ] || [ ! -d "$TARGET_DIR" ]; then
    echo "错误：文件夹 '$1' 不存在或无法访问！"
    exit 1
fi

# 定义支持的图片后缀（可根据需要扩展）
SUPPORT_FORMATS=("jpg" "jpeg" "png" "avif" "webp")

# 临时文件存储宽度和文件名映射
TEMP_FILE=$(mktemp /tmp/image_widths.XXXXXX)
trap 'rm -f "$TEMP_FILE"' EXIT  # 脚本退出时删除临时文件

# 遍历文件夹中的图片文件，获取宽度
echo "正在扫描文件夹：$TARGET_DIR"
echo "支持的图片格式：${SUPPORT_FORMATS[*]}"
echo "----------------------------------------"

for fmt in "${SUPPORT_FORMATS[@]}"; do
    # 查找对应格式的文件（不区分大小写）
    find "$TARGET_DIR" -maxdepth 1 -type f -iname "*.$fmt" | while read -r img_file; do
        if [ -f "$img_file" ]; then
            # 使用 sips 获取图片宽度（macOS 内置工具）
            width=$(sips -g pixelWidth "$img_file" 2>/dev/null | grep pixelWidth | awk '{print $2}')
            # 过滤无效宽度（如非图片文件）
            if [ -n "$width" ] && [ "$width" -gt 0 ] 2>/dev/null; then
                # 存储 宽度:文件名 到临时文件
                echo "$width:$(basename "$img_file")" >> "$TEMP_FILE"
            fi
        fi
    done
done

# 检查是否找到图片
if [ ! -s "$TEMP_FILE" ]; then
    echo "错误：文件夹中未找到支持的图片文件！"
    exit 1
fi

# 统计出现次数最多的宽度（主流宽度）
main_width=$(awk -F: '{print $1}' "$TEMP_FILE" | sort | uniq -c | sort -nr | head -n1 | awk '{print $2}')
main_count=$(awk -F: '{print $1}' "$TEMP_FILE" | grep -c "^$main_width$")
total_count=$(wc -l < "$TEMP_FILE")

# 收集不符合主流宽度的图片并按文件名从小到大排序
unmatched_files=$(awk -F: -v main="$main_width" '$1 != main {print $2}' "$TEMP_FILE" | sort | tr '\n' '、' | sed 's/、$//')

# 输出结果
echo "扫描完成！共检测到 $total_count 张图片"
echo "----------------------------------------"
echo "主流图片宽度：$main_width 像素（共 $main_count 张）"

if [ -n "$unmatched_files" ]; then
    echo "不符合的图片（按文件名排序）：$unmatched_files"
else
    echo "所有图片宽度均为 $main_width 像素"
fi

exit 0