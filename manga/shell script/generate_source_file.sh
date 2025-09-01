#!/opt/homebrew/bin/bash
# 脚本功能：规范化目标目录中的文件/文件夹名称
# 主要处理逻辑：
# 1. 提取序号：支持多种格式（纯数字前缀、"第XXX话/集"、"Episode XXX"等）
# 2. 格式化序号：根据文件总数自动确定序号位数
# 3. 清理名称：
#    - 去除开头连续的标点符号和空格
#    - 去除结尾的连续空格
#    - 在数字与汉字间自动添加空格（特别处理"4个测试"→"4 个测试"）
# 4. 生成新名称："{格式化序号} {清理后的名称}"
# 5. 记录重命名操作并生成source.txt排序列表
# 修复问题：
# - 特别处理数字和汉字之间添加空格的情况
# - 优化边界空格处理，避免多余空格
# - 增强序号提取能力

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

# 增强的序号提取逻辑
for file in "${files[@]}"; do
    # 尝试匹配纯数字前缀
    if [[ "$file" =~ ^[0]*([0-9]+)[^0-9]*(.*)$ ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        
    # 尝试匹配"第XXX话/集"格式
    elif [[ "$file" =~ ^第[0]*([0-9]+)[话集章回节](.*)$ ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        
    # 尝试匹配"Episode XXX"等英文格式
    elif [[ "$file" =~ [Ee]pisode[[:space:]]*0*([0-9]+)(.*)$ ]]; then
        num_str="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        
    else
        error_log+=("无法提取序号: '$file'")
        renamed_files+=("$file")
        continue
    fi

    num=$((10#$num_str))
    printf -v num_padded "%0${width}d" "$num"
    
    # 清理名称：去除开头标点/空格和结尾空格
    shopt -s extglob
    rest="${rest##+([[:punct:][:space:]])}"  # 移除开头连续标点和空格
    rest="${rest%%+([[:space:]])}"           # 移除结尾连续空格
    shopt -u extglob

    # 特别处理：在数字和汉字之间添加空格
    processed_rest=""
    prev_char=""
    
    for (( i=0; i<${#rest}; i++ )); do
        char="${rest:$i:1}"
        
        # 当前字符是汉字且前一个字符是数字
        if [[ "$char" =~ [\p{Han}] && "$prev_char" =~ [0-9] ]]; then
            processed_rest+=" $char"
        # 当前字符是数字且前一个字符是汉字
        elif [[ "$char" =~ [0-9] && "$prev_char" =~ [\p{Han}] ]]; then
            processed_rest+=" $char"
        else
            processed_rest+="$char"
        fi
        
        prev_char="$char"
    done
    
    # 再次清理可能产生的多余空格
    processed_rest=$(echo "$processed_rest" | sed -E 's/ +/ /g; s/^ //; s/ $//')
    
    new_name="${num_padded} ${processed_rest}"
    
    # 执行重命名
    if [[ "$file" != "$new_name" ]]; then
        if ! mv -vn -- "$file" "$new_name"; then
            error_log+=("重命名失败: '$file' -> '$new_name'")
            renamed_files+=("$file")
        else
            renamed_log+=("$file -> $new_name")
            rename_map+=("$file -> $new_name")
            renamed_files+=("$new_name")
        fi
    else
        renamed_files+=("$file")
    fi
done

# 生成排序列表
{
    printf "%s\n" "${renamed_files[@]}" | sort -n -k1
} > source.txt

echo "已生成 source.txt 文件"

# 输出重命名日志
if [[ ${#rename_map[@]} -gt 0 ]]; then
    echo -e "\n📁 重命名映射关系："
    printf "  %s\n" "${rename_map[@]}"
fi

# 错误处理
if [[ ${#error_log[@]} -gt 0 ]]; then
    echo -e "\n❌ 发现以下错误：" >&2
    for err in "${error_log[@]}"; do
        echo "  - $err" >&2
    done
    exit 10
fi

echo -e "\n操作完成！"