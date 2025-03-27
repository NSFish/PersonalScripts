#!/bin/bash

# 检查路径参数
if [ $# -eq 0 ]; then
    echo "错误：请指定目标目录路径"
    echo "用法：$0 /目标目录路径"
    exit 1
fi

target_dir="$1"

# 验证路径有效性
if [ ! -d "$target_dir" ]; then
    echo "错误：路径 '$target_dir' 不存在或不是目录"
    exit 1
fi

# 递归遍历所有子目录（包括根目录）
find "$target_dir" -type d ! -name ".*" -print0 | while IFS= read -r -d $'\0' dir; do
    count=0
    # 处理当前目录下的非隐藏文件
    while IFS= read -r -d $'\0' file; do
        # 提取扩展名
        ext="${file##*.}"
        [ "$ext" = "$(basename "$file")" ] && ext="" || ext=".$ext"
        # 生成三位序号
        newname=$(printf "%02d%s" "$count" "$ext")
        # 执行重命名
        mv -n -- "$file" "$(dirname "$file")/$newname"
        ((count++))
    done < <(find "$dir" -maxdepth 1 -type f ! -name ".*" -print0 | sort -zV)
done