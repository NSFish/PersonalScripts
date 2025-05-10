#!/bin/bash

# 检查是否提供了文件夹路径作为参数
if [ $# -eq 0 ]; then
    echo "错误：请提供要检查的文件夹路径作为参数。"
    exit 1
fi

folder_path="$1"

# 遍历指定文件夹下的所有子文件夹
for subfolder in "$folder_path"/*; do
    if [ -d "$subfolder" ]; then
        # 获取当前子文件夹中所有 .jpg 文件
        jpg_files=("$subfolder"/*.jpg)
        number_array=()

        # 提取文件名中的数字部分
        for file in "${jpg_files[@]}"; do
            filename=$(basename "$file")
            num="${filename%.*}"
            if [[ $num =~ ^[0-9]+$ ]]; then
                number_array+=("$num")
            fi
        done

        # 若没有符合要求的图片，跳过该子文件夹
        if [ ${#number_array[@]} -eq 0 ]; then
            continue
        fi

        # 对数字数组进行排序
        IFS=$'\n' sorted_numbers=($(sort -n <<<"${number_array[*]}"))
        unset IFS

        is_consistent=true
        prev_num=-1
        for num in "${sorted_numbers[@]}"; do
            if [ "$prev_num" != "-1" ]; then
                expected_num=$(echo "$prev_num + 1" | bc)
                if [ "$(echo "$expected_num == $num" | bc)" -ne 1 ]; then
                    is_consistent=false
                    break
                fi
            fi
            prev_num=$num
        done

        if [ "$is_consistent" = false ]; then
            echo "子文件夹 $subfolder 中的图片命名违背规则。"
        fi
    fi
done