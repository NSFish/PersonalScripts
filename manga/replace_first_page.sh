#!/opt/homebrew/bin/bash

# 参数校验
if [ $# -ne 2 ]; then
    echo "错误：必须提供两个文件夹路径作为参数"
    echo "用法：$0 <源文件夹A> <目标文件夹B>"
    exit 1
fi

dirA="$1"
dirB="$2"

# 检查源文件夹是否存在
if [ ! -d "$dirA" ]; then
    echo "错误：源文件夹 $dirA 不存在"
    exit 1
fi

# 遍历源文件夹的所有一级子文件夹
find "$dirA" -mindepth 1 -maxdepth 1 -type d | while read -r subdir; do
    # 提取子文件夹名称
    subdir_name=$(basename "$subdir")
    
    # 查找源文件（支持多种图片格式）
    source_file=$(find "$subdir" -maxdepth 1 -type f \( -name "00.jpg" -o -name "00.jpeg" -o -name "00.png" -o -name "00.gif" \) | head -n 1)

    # 跳过无目标文件的子文件夹
    if [ -z "$source_file" ]; then
        echo "跳过：$subdir 中未找到 00 图片"
        continue
    fi

    # 构建目标路径
    target_subdir="$dirB/$subdir_name"
    target_file="$target_subdir/$(basename "$source_file")"

    # 创建目标子文件夹
    mkdir -p "$target_subdir" || {
        echo "错误：无法创建目录 $target_subdir"
        continue
    }

    # 关键修改：删除目标目录所有00.*文件（无论扩展名）[3,4](@ref)
    find "$target_subdir" -maxdepth 1 -type f \( -name "00" -o -name "00.*" \) -exec rm -f {} +
    echo "已清理目标目录中的旧00图片: $target_subdir"

    # 复制新文件
    if cp -f "$source_file" "$target_file"; then
        echo "复制成功：$source_file → $target_file"
    else
        echo "错误：复制 $source_file 失败"
    fi
done

echo "操作完成"
exit 0