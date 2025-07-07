#!/opt/homebrew/bin/bash
set -euo pipefail  # 启用严格错误处理

target_dir="${1:-}"
error_log=()       # 存储错误信息的数组
renamed_log=()     # 存储重命名日志的数组
renamed_files=()   # 存储重命名后的文件名（用于写入source.txt）
rename_map=()      # 专门存储旧名->新名映射关系

# 参数检查
if [[ -z "$target_dir" ]]; then
    echo "Usage: $0 <directory>" >&2
    exit 1
fi

cd "$target_dir" || exit

# 获取文件列表（排除隐藏文件、当前目录和source.txt）
mapfile -t files < <(find . -maxdepth 1 \( ! -name '.' ! -name '.*' ! -name 'source.txt' \) -print0 | sort -z | xargs -0 basename -a)
total=${#files[@]}
width=${#total}

# 处理每个文件/文件夹
for file in "${files[@]}"; do
    # 尝试提取序号
    if [[ "$file" =~ ^[0]*([0-9]+)([^[:alnum:]]*)(.*) ]]; then
        num_str="${BASH_REMATCH[1]}"
        num=$((10#$num_str))
        printf -v num_padded "%0${width}d" "$num"

        # 处理剩余部分（移除开头空格/标点）
        rest="${BASH_REMATCH[3]}"
        shopt -s extglob
        rest="${rest##+([[:punct:][:space:]])}"
        shopt -u extglob

        # 处理字母数字与汉字之间的空格
        processed_rest=""
        prev_char_type="" # 记录前一个字符的类型: hanzi(汉字), alnum(字母数字), other(其他)
        
        for (( i=0; i<${#rest}; i++ )); do
            char="${rest:$i:1}"
            # 判断字符类型
            if [[ "$char" =~ [\p{Han}] ]] && [[ -v BASH_VERSION ]] && (( BASH_VERSINFO[0] >= 4 )); then
                char_type="hanzi"
            elif [[ "$char" =~ [a-zA-Z0-9] ]]; then
                char_type="alnum"
            else
                char_type="other"
            fi
            
            # 添加空格规则：汉字和字母数字之间需要空格
            if [[ -n "$prev_char_type" ]]; then
                if { [[ "$prev_char_type" == "hanzi" ]] && [[ "$char_type" == "alnum" ]]; } || \
                   { [[ "$prev_char_type" == "alnum" ]] && [[ "$char_type" == "hanzi" ]]; }; then
                    processed_rest+=" "
                fi
            fi
            
            processed_rest+="$char"
            prev_char_type="$char_type"
        done
        
        new_name="${num_padded} ${processed_rest}"
        
        # 实际执行重命名
        if [[ "$file" != "$new_name" ]]; then
            mv -v -- "$file" "$new_name" >/dev/null
            renamed_log+=("$file -> $new_name")
            rename_map+=("$file -> $new_name")  # 专门存储映射关系
            renamed_files+=("$new_name")
        else
            renamed_files+=("$file")  # 未重名的文件也要加入列表
        fi
    else
        # 记录提取失败的错误
        error_log+=("无法提取序号: '$file'")
        renamed_files+=("$file")  # 即使出错也要包含在列表中
    fi
done

# 将重命名后的文件按数字顺序写入source.txt
{
    # 按数字前缀排序（忽略前导空格）
    IFS=$'\n' sorted_files=($(printf '%s\n' "${renamed_files[@]}" | sort -n -k1))
    
    # 写入文件
    for file in "${sorted_files[@]}"; do
        echo "$file"
    done
} > source.txt

echo "已生成 source.txt 文件"

# 打印重命名映射关系（仅实际发生重命名的文件）
if [[ ${#rename_map[@]} -gt 0 ]]; then
    echo -e "\n📁 重命名映射关系："
    printf "  %s\n" "${rename_map[@]}"
fi

# 统一处理错误
if [[ ${#error_log[@]} -gt 0 ]]; then
    echo -e "\n❌❌ 发现以下错误：" >&2
    for err in "${error_log[@]}"; do
        echo "  - $err" >&2
    done
    exit 10  # 自定义错误码
fi

echo -e "\n操作完成！"