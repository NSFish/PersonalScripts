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
    
    # 获取非隐藏文件列表（排除以点开头的文件）
    files=()
    while IFS= read -r -d $'\0' file; do
        # 去掉前面的 "./" 路径部分
        file="${file#./}"
        # 排除隐藏文件（以点开头的文件）
        [[ "$file" = .* ]] && continue
        files+=("$file")
    done < <(find . -maxdepth 1 -type f -print0 | sort -V -z)
    
    # 统计文件数量
    file_count=${#files[@]}
    
    # 没有文件时直接返回
    if [[ $file_count -eq 0 ]]; then
        [[ "$VERBOSE" == true ]] && echo "  目录为空，跳过处理"
        cd - >/dev/null
        return
    fi

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
    original_names=("${files[@]}")
    
    # Dry-run模式只显示操作
    if [[ "$DRY_RUN" == true ]]; then
        for ((i=0; i<file_count; i++)); do
            file="${original_names[$i]}"
            # 安全处理扩展名
            if [[ "$file" =~ \.([^.]+)$ ]]; then
                ext="${BASH_REMATCH[1]}"
                new_name="$(printf "%0${digit_count}d.%s" $i "$ext")"
            else
                new_name="$(printf "%0${digit_count}d" $i)"
            fi
            echo "  ✅  \"$file\" -> \"$new_name\""
        done
        cd - >/dev/null
        return
    fi
    
    # 实际执行的两步重命名
    count=0
    for file in "${original_names[@]}"; do
        # 安全处理扩展名
        if [[ "$file" =~ \.([^.]+)$ ]]; then
            ext="${BASH_REMATCH[1]}"
            new_name="temp_$(printf "%0${digit_count}d.%s" $count "$ext")"
        else
            new_name="temp_$(printf "%0${digit_count}d" $count)"
        fi
        mv -- "$file" "$new_name" 2>/dev/null
        ((count++))
    done
    
    count=0
    # 获取临时文件列表（安全方式）
    temp_files=()
    while IFS= read -r -d $'\0' file; do
        file="${file#./}"
        # 排除隐藏文件（以点开头的文件）
        [[ "$file" = .* ]] && continue
        temp_files+=("$file")
    done < <(find . -maxdepth 1 -name 'temp_*' -print0 | sort -V -z)
    
    for file in "${temp_files[@]}"; do
        # 处理最终文件名
        if [[ "$file" =~ \.([^.]+)$ ]]; then
            ext="${BASH_REMATCH[1]}"
            new_name="$(printf "%0${digit_count}d.%s" $count "$ext")"
        else
            new_name="$(printf "%0${digit_count}d" $count)"
        fi
        
        original_name="${original_names[$count]}"
        echo "✅  \"$original_name\" -> \"$new_name\""
        mv -- "$file" "$new_name" 2>/dev/null
        ((count++))
    done
    
    cd - >/dev/null
}

# 主程序
main() {
    parse_args "$@"
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "🏃 运行模式: 预览 (dry-run)"
        echo "  注: 不会实际修改文件"
    else
        echo "🏃‍♂️ 运行模式: 实际执行"
    fi
    
    [[ "$VERBOSE" == true ]] && echo "🔍 扫描目录: $target_dir"
    
    # 使用进程替换避免子Shell问题
    while IFS= read -r dir; do
        [[ "$dir" == "$target_dir" ]] && continue
        process_directory "$dir"
    done < <(find "$target_dir" -type d)
}

# 启动程序
main "$@"