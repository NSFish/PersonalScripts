#!/bin/bash

# 检查是否传入两个参数
if [ $# -ne 2 ]; then
    echo "用法: $0 文件夹A 文件夹B"
    exit 1
fi

# 赋值传入的参数
folder_a=$1
folder_b=$2

# 检查文件夹A和文件夹B是否存在
if [ ! -d "$folder_a" ]; then
    echo "文件夹 $folder_a 不存在。"
    exit 1
fi

if [ ! -d "$folder_b" ]; then
    echo "文件夹 $folder_b 不存在。"
    exit 1
fi

# 遍历文件夹B中的子文件夹
for subfolder_b in "$folder_b"/*; do
    if [ -d "$subfolder_b" ]; then
        # 从文件夹名中用正则截取三位数数字作为序列号
        folder_name=$(basename "$subfolder_b")
        if [[ $folder_name =~ ([0-9]{3}) ]]; then
            serial_number=${BASH_REMATCH[1]}
            # 使用 find 命令查找匹配的文件夹
            matched_folder=$(find "$folder_a" -maxdepth 1 -type d -name "$serial_number*" | head -n 1)
            if [ -n "$matched_folder" ]; then
                # 找到文件夹A中对应子文件夹下的第一张图片
                first_image=$(find "$matched_folder" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | head -n 1)
                if [ -n "$first_image" ]; then
                    # 复制第一张图片到文件夹B中对应的子文件夹
                    cp "$first_image" "$subfolder_b"
                    echo "已复制 $first_image 到 $subfolder_b"
                fi
            else
                echo "未找到匹配的文件夹，序列号: $serial_number"
            fi
        fi
    fi
done