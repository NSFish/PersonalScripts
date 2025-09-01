#!/bin/bash

# 主控制脚本：按顺序执行图片整理、中文数字转换、重命名和压缩操作

# 检查参数
if [ $# -ne 1 ]; then
    echo "错误：请提供目标文件夹路径作为参数。"
    echo "用法：$0 <目标文件夹路径>"
    exit 1
fi

target_dir="$1"

# 验证目标文件夹是否存在
if [ ! -d "$target_dir" ]; then
    echo "错误：文件夹 '$target_dir' 不存在。"
    exit 1
fi

# 获取当前脚本所在目录
script_dir=$(dirname "$(realpath "$0")")

# 按顺序执行四个步骤
echo "步骤1：整理图片到子文件夹..."
"$script_dir/organize_images.sh" "$target_dir"

echo -e "\n步骤2：转换中文数字文件夹名..."
"$script_dir/convert_chinese_numbers_to_arab.sh" "$target_dir"

echo -e "\n步骤3：重命名子文件夹中的图片..."
"$script_dir/rename_manga_pages.sh" "$target_dir"

echo -e "\n步骤4：压缩子文件夹..."
"$script_dir/zip_sub_folders.sh" "$target_dir"

echo -e "\n✅ 所有操作已完成！"