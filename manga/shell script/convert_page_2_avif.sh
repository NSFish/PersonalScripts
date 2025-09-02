#!/opt/homebrew/bin/bash

# 检查参数和依赖
if [ $# -ne 1 ]; then
    echo "用法: $0 <源文件夹路径>"
    exit 1
fi

if ! command -v magick &>/dev/null; then
    echo "错误: ImageMagick 未安装或版本过低"
    exit 1
fi

source_dir="$1"
target_dir="${source_dir}_avif"

# 处理更多格式并自然排序
all_files=$(find "$source_dir" -type f -not -path '*/\.*')
convert_files=$(echo "$all_files" | grep -iE '\.(jpg|jpeg|webp|png)$')
copy_files=$(echo "$all_files" | grep -ivE '\.(jpg|jpeg|webp|png)$')

total_files=$(echo "$all_files" | wc -l)
processed=0

echo "开始处理 $total_files 个文件..."

# 转换图像文件
echo "$convert_files" | sort -V | while IFS= read -r file; do
    relative_path="${file#$source_dir/}"
    output_file="$target_dir/${relative_path%.*}.avif"
    output_dir=$(dirname "$output_file")
    
    mkdir -p "$output_dir" || { echo "目录创建失败: $output_dir"; exit 1; }
    
    # 显示进度
    processed=$((processed+1))
    echo -ne "进度: $processed/$total_files ($(printf "%.1f" $(echo "scale=2; $processed/$total_files*100" | bc)))% \r"
    
    # 转换图像
    magick "$file" -strip "$output_file" || {
        echo "警告: 转换失败 - $file" >&2
    }
done

# 复制其他文件 - 修改部分
if [ -n "$copy_files" ]; then  # 检查是否有文件需要复制
    echo "$copy_files" | sort -V | while IFS= read -r file; do
        relative_path="${file#$source_dir/}"
        output_file="$target_dir/$relative_path"
        output_dir=$(dirname "$output_file")
        
        mkdir -p "$output_dir" || { echo "目录创建失败: $output_dir"; exit 1; }
        
        # 显示进度
        processed=$((processed+1))
        echo -ne "进度: $processed/$total_files ($(printf "%.1f" $(echo "scale=2; $processed/$total_files*100" | bc)))% \r"
        
        # 复制文件
        cp "$file" "$output_file" || {
            echo "警告: 复制失败 - $file" >&2
        }
    done
else
    echo "没有需要复制的非图像文件"
fi

echo -ne "\n处理完成. 目标目录: $target_dir\n"