#!/opt/homebrew/bin/bash

# 检查是否提供了文件夹参数
if [ $# -ne 1 ]; then
    echo "使用方法: $0 <文件夹A路径>"
    exit 1
fi

INPUT_DIR="$1"

# 检查文件夹是否存在
if [ ! -d "$INPUT_DIR" ]; then
    echo "错误: 文件夹 '$INPUT_DIR' 不存在"
    exit 1
fi

# 支持的图片文件扩展名
IMAGE_EXTENSIONS=("jpg" "jpeg" "png" "gif" "bmp" "webp" "tiff")

# 处理所有按文件名排序的zip和cbz文件
find "$INPUT_DIR" -maxdepth 1 -type f \( -name "*.zip" -o -name "*.cbz" \) -print0 | \
  sort -z | \
  while IFS= read -r -d '' file; do
    # 获取文件名（不含扩展名）作为子文件夹名
    filename=$(basename "$file")
    base_name="${filename%.*}"
    temp_dir=$(mktemp -d)
    
    echo "正在处理: $filename"
    
    # 解压文件到临时目录
    unzip -q -o "$file" -d "$temp_dir" 2> /tmp/unzip_error
    unzip_exit=$?
    
    # 检查解压是否成功
    if [ $unzip_exit -ne 0 ]; then
        error_msg=$(</tmp/unzip_error)
        echo "❌ 解压 $filename 失败: ${error_msg:0:100}"  # 截断长错误信息
        rm -rf "$temp_dir"
        rm -f /tmp/unzip_error
        continue
    fi
    rm -f /tmp/unzip_error
    
    # 创建输出子文件夹（直接在输入文件夹中）
    output_subdir="${INPUT_DIR}/${base_name}"
    mkdir -p "$output_subdir"
    
    # 尝试移动图片文件
    moved_count=0
    for ext in "${IMAGE_EXTENSIONS[@]}"; do
        # 查找并移动图片，同时计数
        count=$(find "$temp_dir" -type f -iname "*.$ext" -exec mv {} "$output_subdir/" \; -print | wc -l)
        moved_count=$((moved_count + count))
    done
    
    # 检查是否成功移动了图片
    if [ $moved_count -gt 0 ]; then
        echo "✅ 解压 $filename 成功 (移动了 $moved_count 张图片)"
    else
        # 没有移动任何图片，删除空文件夹
        rmdir "$output_subdir" 2>/dev/null
        echo "❌ 解压 $filename 失败: 未找到支持的图片文件"
    fi
    
    # 清理临时目录
    rm -rf "$temp_dir"
done

echo "处理完成！"