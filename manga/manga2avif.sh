#!/bin/bash

# 检查参数和依赖
if [ $# -ne 1 ]; then
    echo "用法: $0 <源文件夹路径>"
    exit 1
fi

if ! command -v magick &>/dev/null; then
    echo "错误: ImageMagick 未安装或版本过低"
    exit 1
fi

source_dir="$1"
target_dir="${source_dir}_avif"

# 处理更多格式并自然排序
find "$source_dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.webp" -o -iname "*.png" \) | sort -V | while IFS= read -r file; do
    relative_path="${file#$source_dir/}"
    output_file="$target_dir/${relative_path%.*}.avif"
    output_dir=$(dirname "$output_file")
    
    mkdir -p "$output_dir" || { echo "目录创建失败: $output_dir"; exit 1; }
    
    # 转换并移除所有元数据（新增 -strip）
    magick "$file" -strip "$output_file"
done

echo "转换完成. 目标目录: $target_dir"