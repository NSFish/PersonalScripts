#!/bin/bash

# 检查是否提供了目录参数
if [ -z "$1" ]; then
    echo "错误：请提供一个目录路径作为参数"
    exit 1
fi

directory="$1"

# 检查目录是否存在
if [ ! -d "$directory" ]; then
    echo "错误：目录 '$directory' 不存在"
    exit 1
fi

# 进入目标目录
cd "$directory" || exit

# 查找并解压所有zip和cbz文件
for archive_file in *.zip *.cbz; do
    # 检查文件是否存在（避免在没有匹配时处理字面量"*.zip"或"*.cbz"）
    [ -f "$archive_file" ] || continue
    
    echo "处理 '$archive_file'"
    
    # 获取文件的基本名称（不包含扩展名）
    base_name="${archive_file%.*}"
    
    # 创建同名文件夹（如果不存在）
    if [ ! -d "$base_name" ]; then
        mkdir -p "$base_name"
    fi
    
    # 解压到同名文件夹中
    unzip -q -d "$base_name" "$archive_file"
    
    echo "成功解压 '$archive_file' 到 '$base_name/'"
done

echo "解压完成"