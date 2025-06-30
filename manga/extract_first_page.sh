#!/bin/bash

# 检查参数数量是否正确
if [ "$#" -ne 2 ]; then
    echo "请提供源文件夹和目标文件夹作为参数"
    exit 1
fi

# 获取源文件夹和目标文件夹路径（作为参数传入）
SRC_DIR="$1"
DEST_DIR="$2"

# 验证源文件夹是否存在
if [ ! -d "$SRC_DIR" ]; then
    echo "错误：源文件夹 '$SRC_DIR' 不存在"
    exit 1
fi

# 创建目标文件夹（如果不存在）
mkdir -p "$DEST_DIR"

# 获取所有子文件夹
SUB_DIRS=$(find "$SRC_DIR" -mindepth 1 -type d)

# 遍历每个子文件夹
for sub_dir in $SUB_DIRS; do
    # 获取子文件夹名称
    sub_dir_name=$(basename "$sub_dir")
    
    # 获取子文件夹中的所有图片文件（按文件名排序）
    # 支持常见的图片格式，可根据需要添加更多格式
    image_files=$(find "$sub_dir" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" -o -iname "*.bmp" \) | sort)
    
    # 检查是否有图片文件
    if [ -n "$image_files" ]; then
        # 获取第一张图片（排序后的第一个）
        first_image=$(echo "$image_files" | head -n 1)
        
        # 获取图片扩展名
        ext="${first_image##*.}"
        
        # 构建新文件名（使用子文件夹名称）
        new_name="${sub_dir_name}.${ext}"
        
        # 复制第一张图片到目标文件夹
        cp "$first_image" "$DEST_DIR/$new_name"
        
        echo "已复制: $first_image -> $DEST_DIR/$new_name"
    else
        echo "警告：子文件夹 '$sub_dir' 中没有找到图片文件"
    fi
done

echo "操作完成！提取的图片已保存到 '$DEST_DIR'"