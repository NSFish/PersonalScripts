#!/opt/homebrew/bin/bash

# 功能：递归修改指定目录（含所有子目录）中的 .jpeg 图片扩展名为 .jpg

# 检查参数
if [ $# -eq 0 ]; then
    echo "错误：请提供目标目录路径"
    echo "示例：$0 ~/Pictures"
    exit 1
fi

target_dir="$1"
count=0

# 预处理基础目录格式（确保结尾有且只有一个斜杠）
if [ "${target_dir: -1}" != "/" ]; then
    base_dir="$target_dir/"
else
    base_dir="$target_dir"
fi

# 使用进程替换避免子shell问题
while IFS= read -r -d $'\0' file; do
    # 提取相对路径（移除基础目录前缀）
    relative_path="${file#$base_dir}"
    
    # 生成新文件名（保留原名，仅替换扩展名）
    new_filename="${file%.*}.jpg"  # 直接修改完整路径的扩展名
    
    # 执行重命名
    mv -- "$file" "$new_filename" 2>/dev/null
    
    # 显示精简路径的重命名信息
    echo "${relative_path%.*}.jpeg -> ${relative_path%.*}.jpg"
    
    # 计数器递增
    ((count++))
done < <(find "$target_dir" -type f \( -iname "*.jpeg" \) -print0)

echo "操作完成！共修改 $count 个文件"