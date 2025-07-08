#!/opt/homebrew/bin/bash
set -euo pipefail

target_dir="${1:-}"
error_log=()
renamed_log=()
renamed_files=()
rename_map=()

if [[ -z "$target_dir" ]]; then
    echo "Usage: $0 <directory>" >&2
    exit 1
fi

cd "$target_dir" || exit

mapfile -t files < <(find . -maxdepth 1 \( ! -name '.' ! -name '.*' ! -name 'source.txt' \) -print0 | sort -z | xargs -0 basename -a)
total=${#files[@]}
width=${#total}

# 优化后的序号提取逻辑
for file in "${files[@]}"; do
    # 尝试匹配纯数字前缀 (原逻辑)
    if [[ "$file" =~ ^[0]*([0-9]+)([^[:alnum:]]*)(.*) ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[3]}"
        
    # 新增：尝试匹配"第XXX话/集"格式
    elif [[ "$file" =~ ^第[0]*([0-9]+)[话集章回节]([^[:alnum:]]*)(.*) ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[3]}"
        
    # 新增：尝试匹配"Episode XXX"等英文格式
    elif [[ "$file" =~ [Ee]pisode[[:space:]]*0*([0-9]+)([^[:alnum:]]*)(.*) ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[3]}"
        
    # 新增：尝试匹配其他常见格式
    elif [[ "$file" =~ [Cc]hapter[[:space:]]*0*([0-9]+)([^[:alnum:]]*)(.*) ]] || \
         [[ "$file" =~ [Pp]art[[:space:]]*0*([0-9]+)([^[:alnum:]]*)(.*) ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[3]}"
        
    else
        error_log+=("无法提取序号: '$file'")
        renamed_files+=("$file")
        continue
    fi

    num=$((10#$num_str))
    printf -v num_padded "%0${width}d" "$num"
    
    # 清理剩余部分开头的标点/空格
    shopt -s extglob
    rest="${rest##+([[:punct:][:space:]])}"
    shopt -u extglob

    # 处理字母数字与汉字之间的空格
    processed_rest=""
    prev_char_type=""
    
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
        
        # 添加空格规则
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
        rename_map+=("$file -> $new_name")
        renamed_files+=("$new_name")
    else
        renamed_files+=("$file")
    fi
done

# 其余代码保持不变...
{
    IFS=$'\n' sorted_files=($(printf '%s\n' "${renamed_files[@]}" | sort -n -k1))
    
    for file in "${sorted_files[@]}"; do
        echo "$file"
    done
} > source.txt

echo "已生成 source.txt 文件"

if [[ ${#rename_map[@]} -gt 0 ]]; then
    echo -e "\n📁📁 重命名映射关系："
    printf "  %s\n" "${rename_map[@]}"
fi

if [[ ${#error_log[@]} -gt 0 ]]; then
    echo -e "\n❌❌❌❌ 发现以下错误：" >&2
    for err in "${error_log[@]}"; do
        echo "  - $err" >&2
    done
    exit 10
fi

echo -e "\n操作完成！"