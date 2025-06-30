#!/bin/bash

# 检查是否提供了文件夹路径作为参数
if [ $# -ne 1 ]; then
    echo "用法: $0 <文件夹路径>"
    exit 1
fi

folder_path="$1"

# 检查文件夹是否存在
if [ ! -d "$folder_path" ]; then
    echo "错误: 指定的文件夹 $folder_path 不存在。"
    exit 1
fi

# 进入指定文件夹
cd "$folder_path" || exit

# 启用不区分大小写的文件名匹配
shopt -s nocaseglob

# 遍历所有图片文件（支持jpg、jpeg、png、gif等常见格式）
for file in *.jpg *.jpeg *.png *.gif *.bmp; do
    # 跳过不存在的文件（当没有匹配文件时）
    [ -f "$file" ] || continue

    # 使用grep提取两个下划线之间的最长部分
    subfolder=$(echo "$file" | grep -oP '_(.*)_' | tr -d '_')

    # 检查是否成功提取子文件夹名
    if [ -n "$subfolder" ]; then
        # 检查子文件夹是否存在，如果不存在则创建
        if [ ! -d "$subfolder" ]; then
            mkdir -p "$subfolder"
        fi
        
        # 移动文件到对应的子文件夹
        mv "$file" "$subfolder/"
        echo "已移动: $file → $subfolder/"
    else
        echo "警告: 无法从 '$file' 中提取子文件夹名（格式不符合要求）"
    fi
done

# 恢复默认的大小写敏感匹配
shopt -u nocaseglob