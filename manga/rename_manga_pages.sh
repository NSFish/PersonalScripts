#!/opt/homebrew/bin/bash

target_dir="$1"

find "$target_dir" -type d | while read dir; do
    [ "$dir" = "$target_dir" ] && continue

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

    # 两步重命名防覆盖（临时文件法）
    count=0
    for file in $files; do
        ext="${file##*.}"
        mv "$file" "temp_$(printf "%0${digit_count}d" $count).$ext" 2>/dev/null
        ((count++))
    done

    # 正式重命名
    count=0
    ls | sort -V | while read temp_file; do
        ext="${temp_file##*.}"
        mv "$temp_file" "$(printf "%0${digit_count}d.%s" $count "$ext")" 2>/dev/null
        ((count++))
    done

    cd - >/dev/null
done