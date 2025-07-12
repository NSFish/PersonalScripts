#!/bin/bash

# 检查是否提供了目录参数
if [ -z "$1" ]; then
    echo "请提供一个目录作为参数"
    exit 1
fi

# 检查目录是否存在
if [ ! -d "$1" ]; then
    echo "目录 '$1' 不存在"
    exit 1
fi

# 获取绝对路径
base_dir=$(realpath "$1")

# 查找所有图片文件（支持常见图片格式，可根据需要扩展）
find "$base_dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" -o -iname "*.bmp" \) | while read -r img; do
    # 获取文件所在的子目录名
    sub_dir=$(dirname "$img")
    sub_dir_name=$(basename "$sub_dir")
    
    # 获取文件名和扩展名
    file_name=$(basename "$img")
    file_base="${file_name%.*}"
    file_ext="${file_name##*.}"
    
    # 构建基础新文件名：子目录名_原文件名.扩展名
    base_new_name="${sub_dir_name}_${file_base}"
    new_name="${base_new_name}.${file_ext}"
    target_path="${base_dir}/${new_name}"
    
    # 处理重名文件
    counter=1
    while [ -e "$target_path" ]; do
        new_name="${base_new_name}_${counter}.${file_ext}"
        target_path="${base_dir}/${new_name}"
        ((counter++))
    done
    
    # 移动文件
    mv "$img" "$target_path"
    echo "已移动: $img -> $target_path"
done

# 删除所有空的子文件夹（保留顶层目录）
find "$base_dir" -mindepth 1 -type d -empty -delete
echo "已删除所有空的子文件夹"

echo "处理完成！"    