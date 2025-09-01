#!/bin/bash

if [ $# -ne 1 ]; then
    echo "错误：请提供目标文件夹路径作为参数。"
    echo "用法：$0 /目标/文件夹路径"
    exit 1
fi

parent_dir="$1"

if [ ! -d "$parent_dir" ]; then
    echo "错误：文件夹 '$parent_dir' 不存在。"
    exit 1
fi

# 修复：使用 \0 分隔符处理含空格的路径
find "$parent_dir" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d $'\0' folder; do
    folder_name=$(basename "$folder")
    parent_path=$(dirname "$folder")
    zip_path="${folder}.zip"

    # ▼ 新增逻辑：检查同名压缩包是否存在 ▼
    if [ -e "$zip_path" ]; then
        echo "⚠️ 跳过 '$folder_name'：已存在同名压缩包"
        continue  # 跳过当前子文件夹
    fi

    echo "正在压缩: $folder_name"
    
    # 进入父目录后再压缩，避免路径解析问题
    (cd "$parent_path" && zip -r -q "$zip_path" "$folder_name" -x "*.DS_Store" -x "__MACOSX*")
    
    if [ $? -eq 0 ]; then
        echo "✅ 已创建: ${folder_name}.zip"
    else
        echo "❌ 压缩失败: $folder_name"
    fi
done

echo "操作完成！"