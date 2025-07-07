#!/opt/homebrew/bin/bash

target_dir="$1"

find "$target_dir" -type d | while read dir; do
    [ "$dir" = "$target_dir" ] && continue

    echo "🛠  正在处理文件夹: $dir"
    
    cd "$dir" || continue

    # 获取自然排序后的文件列表
    files=$(ls | sort -V)

    # 统计文件数量
    file_count=$(echo "$files" | wc -w | tr -d '[:space:]')

    # 确定编号所需的最少位数
    digit_count=0
    temp_count=$file_count
    while [ $temp_count -gt 0 ]; do
        temp_count=$((temp_count / 10))
        digit_count=$((digit_count + 1))
    done

    # 确保至少使用两位数
    if [ "$digit_count" -lt 2 ]; then
        digit_count=2
    fi

    # 创建数组存储原始文件名
    original_names=()
    while IFS= read -r file; do
        original_names+=("$file")
    done <<< "$files"

    # 两步重命名防覆盖（临时文件法）
    count=0
    for file in $files; do
        ext="${file##*.}"
        mv "$file" "temp_$(printf "%0${digit_count}d" $count).$ext" 2>/dev/null
        ((count++))
    done

    # 正式重命名
    count=0
    ls | grep '^temp_' | sort -V | while read temp_file; do
        ext="${temp_file##*.}"
        new_name="$(printf "%0${digit_count}d.%s" $count "$ext")"
        
        # 获取对应的原始文件名
        original_name="${original_names[$count]}"
        
        # 添加重命名成功提示
        echo "✅  \"$original_name\" -> \"$new_name\""
        
        mv "$temp_file" "$new_name" 2>/dev/null
        ((count++))
    done

    cd - >/dev/null
done