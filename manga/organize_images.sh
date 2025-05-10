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

# 遍历当前目录下的所有图片文件
for file in *.jpg; do
    # 提取两个下划线之间的部分
    subfolder=$(echo "$file" | cut -d '_' -f 2)

    # 检查子文件夹是否存在，如果不存在则创建
    if [ ! -d "$subfolder" ]; then
        mkdir "$subfolder"
    fi

    # 移动图片到对应的子文件夹
    mv "$file" "$subfolder/"
done