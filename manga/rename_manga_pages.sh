#!/opt/homebrew/bin/bash

# 初始化变量
DRY_RUN=false
VERBOSE=false
target_dir=""

# 帮助信息函数
show_help() {
    echo "用法: $0 [选项] <目标目录>"
    echo "重命名目标目录下的文件为按数字排序的文件名"
    echo ""
    echo "选项:"
    echo "  -n, --dry-run    显示重命名操作但不实际执行"
    echo "  -v, --verbose    显示详细处理过程"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/folder          # 执行重命名"
    echo "  $0 -n /path/to/folder       # 预览重命名操作"
    echo "  $0 -v /path/to/folder       # 显示详细处理过程"
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                if [[ -z "$target_dir" ]]; then
                    target_dir="$1"
                else
                    echo "错误：只能指定一个目标目录" >&2
                    show_help
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    if [[ -z "$target_dir" ]]; then
        echo "错误：请指定目标目录" >&2
        show_help
        exit 1
    fi
}

# 主处理函数
process_directory() {
    local dir="$1"
    
    [[ "$VERBOSE" == true ]] && echo "🛠 正在处理文件夹: $dir"
    
    cd "$dir" || return
    
    # 获取自然排序后的文件列表
    files=$(ls | sort -V)
    
    # 统计文件数量
    file_count=$(echo "$files" | wc -w | tr -d '[:space:]')
    
    # 确定编号位数
    digit_count=0
    temp_count=$file_count
    while [[ $temp_count -gt 0 ]]; do
        temp_count=$((temp_count / 10))
        digit_count=$((digit_count + 1))
    done
    
    # 确保至少使用两位数
    [[ "$digit_count" -lt 2 ]] && digit_count=2
    
    # 创建数组存储原始文件名
    original_names=()
    while IFS= read -r file; do
        original_names+=("$file")
    done <<< "$files"
    
    # Dry-run模式只显示操作
    if [[ "$DRY_RUN" == true ]]; then
        echo "📋 文件夹 $dir 的预览操作:"
        for ((i=0; i<${#original_names[@]}; i++)); do
            ext="${original_names[$i]##*.}"
            new_name="$(printf "%0${digit_count}d.%s" $i "$ext")"
            echo "  ✅  \"${original_names[$i]}\" -> \"$new_name\""
        done
        cd - >/dev/null
        return
    fi
    
    # 实际执行的两步重命名
    count=0
    for file in $files; do
        ext="${file##*.}"
        mv "$file" "temp_$(printf "%0${digit_count}d" $count).$ext" 2>/dev/null
        ((count++))
    done
    
    count=0
    ls | grep '^temp_' | sort -V | while read -r temp_file; do
        ext="${temp_file##*.}"
        new_name="$(printf "%0${digit_count}d.%s" $count "$ext")"
        original_name="${original_names[$count]}"
        echo "✅  \"$original_name\" -> \"$new_name\""
        mv "$temp_file" "$new_name" 2>/dev/null
        ((count++))
    done
    
    cd - >/dev/null
}

# 主程序
main() {
    parse_args "$@"
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "🏃‍♂️ 运行模式: 预览 (dry-run)"
        echo "  注: 不会实际修改文件"
    else
        echo "🏃‍♂️ 运行模式: 实际执行"
    fi
    
    [[ "$VERBOSE" == true ]] && echo "🔍 扫描目录: $target_dir"
    
    find "$target_dir" -type d | while read -r dir; do
        [[ "$dir" == "$target_dir" ]] && continue
        process_directory "$dir"
    done
}

# 启动程序
main "$@"