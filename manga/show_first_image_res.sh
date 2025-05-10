#!/bin/bash

# 检查是否传入一个参数
if [ $# -ne 1 ]; then
    echo "用法: $0 文件夹路径"
    exit 1
fi

# 赋值传入的参数
folder_path=$1

# 检查文件夹是否存在
if [ ! -d "$folder_path" ]; then
    echo "指定的文件夹 $folder_path 不存在。"
    exit 1
fi

# 遍历指定文件夹下的所有子文件夹
for sub_folder in "$folder_path"/*; do
    if [ -d "$sub_folder" ]; then
        sub_folder_name=$(basename "$sub_folder")
        # 获取子文件夹中的所有图片文件，并按文件名排序
        image_files=($(find "$sub_folder" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | sort))
        # 如果子文件夹中有至少两张图片
        if [ ${#image_files[@]} -ge 2 ]; then
            second_image="${image_files[1]}"
            # 使用 identify 命令获取图片的宽度和高度
            size=$(identify -format "%w*%h" "$second_image")
            echo "$sub_folder_name: $size"
        fi
    fi
done