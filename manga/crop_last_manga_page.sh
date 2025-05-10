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

# 遍历文件夹中的每个子文件夹
for subfolder in "$folder_path"/*/; do
    # 获取子文件夹中按文件名排序的最后一张图片
    last_image=$(find "$subfolder" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.avif" \) | sort | tail -n 1)
    if [ -n "$last_image" ]; then
        # 获取图片的宽度和高度
        dimensions=$(identify -format "%w %h" "$last_image")
        width=$(echo "$dimensions" | cut -d ' ' -f 1)
        height=$(echo "$dimensions" | cut -d ' ' -f 2)

        # 检查图片宽度和高度是否符合 800x1271 或 900x1429 条件
        if ( [ "$width" -eq 800 ] && [ "$height" -gt 1271 ] ) || ( [ "$width" -eq 900 ] && [ "$height" -gt 1429 ] ); then
            # 获取图片文件名和扩展名
            filename=$(basename "$last_image")
            extension="${filename##*.}"
            filename_no_ext="${filename%.*}"

            # 备份原始图片
            mv "$last_image" "${subfolder}${filename_no_ext}_bak.${extension}"

            if [ "$width" -eq 800 ]; then
                # 截取 800x1271 部分
                magick "${subfolder}${filename_no_ext}_bak.${extension}" -crop 800x1271+0+0 "${subfolder}${filename}"
                echo "处理完成 (800x1271): $last_image"
            elif [ "$width" -eq 900 ]; then
                # 截取 900x1429 部分
                magick "${subfolder}${filename_no_ext}_bak.${extension}" -crop 900x1429+0+0 "${subfolder}${filename}"
                echo "处理完成 (900x1429): $last_image"
            fi
        fi
    fi
done