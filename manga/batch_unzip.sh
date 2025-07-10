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

# 查找并解压所有zip文件
for zip_file in *.zip; do
    # 检查文件是否存在（避免在没有匹配时处理字面量"*.zip"）
    [ -e "$zip_file" ] || continue
    
    echo "处理 '$zip_file'"
    
    # 获取zip文件的基本名称（不包含扩展名）
    base_name="${zip_file%.*}"
    
    # 直接解压到当前目录
    unzip -q "$zip_file"
    
    # 重命名解压出的文件夹（如果需要）
    # 注意：此脚本假设zip内的文件夹名与zip文件名一致
    
    echo "成功解压 '$zip_file'"
done

echo "解压完成"    