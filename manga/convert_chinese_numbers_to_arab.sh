#!/opt/homebrew/bin/bash
# 中文数字文件夹重命名工具

# 初始化变量
DRY_RUN=false  # 默认执行模式
FOLDER_PATH=""
VERBOSE=false   # 控制详细输出

# 帮助信息
show_help() {
    echo "用法: $0 [选项] <文件夹路径>"
    echo "将指定文件夹下的子文件夹名称从中文数字格式转换为阿拉伯数字格式"
    echo ""
    echo "选项:"
    echo "  -n, --dry-run    显示重命名操作但不实际执行 (预览模式)"
    echo "  -v, --verbose    显示详细处理过程"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/folders          (执行重命名)"
    echo "  $0 --dry-run /path/to/folders  (预览模式)"
    echo "  $0 -v /path/to/folders         (详细执行模式)"
}

# 检查Bash版本
check_bash_version() {
    local major_version=${BASH_VERSION%%.*}
    if [[ $major_version -lt 4 ]]; then
        echo "错误: 需要Bash 4.0或更高版本" >&2
        exit 1
    fi
}

# 解析命令行参数
parse_args() {
    echo "===== 开始解析命令行参数 =====" >&2
    echo "参数列表: $*" >&2
    
    while [[ $# -gt 0 ]]; do
        echo "--- 处理参数: $1" >&2
        case "$1" in
            -n|--dry-run)
                DRY_RUN=true
                echo "  设置为预览模式" >&2
                ;;
            -v|--verbose)
                VERBOSE=true
                echo "  启用详细模式" >&2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                if [[ -n "$FOLDER_PATH" ]]; then
                    echo "错误：只能指定一个文件夹路径" >&2
                    show_help
                    exit 1
                fi
                FOLDER_PATH="$1"
                echo "  设置文件夹路径: $FOLDER_PATH" >&2
                ;;
        esac
        shift
        echo "--- 剩余参数: $*" >&2
    done
    
    if [[ -z "$FOLDER_PATH" ]]; then
        echo "错误：请指定文件夹路径" >&2
        show_help
        exit 1
    fi
    
    echo "===== 参数解析完成 =====" >&2
    echo "DRY_RUN: $DRY_RUN" >&2
    echo "FOLDER_PATH: $FOLDER_PATH" >&2
    echo "VERBOSE: $VERBOSE" >&2
}

# 检查路径有效性
check_path() {
    echo "===== 检查路径 =====" >&2
    echo "正在检查路径：'$FOLDER_PATH'" >&2
    
    if [[ ! -e "$FOLDER_PATH" ]]; then
        echo "错误：路径不存在" >&2
        exit 1
    fi
    
    if [[ ! -d "$FOLDER_PATH" ]]; then
        echo "错误：路径存在但不是目录" >&2
        exit 1
    fi
    
    if [[ ! -w "$FOLDER_PATH" ]]; then
        echo "错误：没有修改目录的权限" >&2
        exit 1
    fi
    
    echo "路径检查通过：$FOLDER_PATH" >&2
}

# 中文数字映射表
declare -A chinese_numbers=(
    ["$(printf "\\u4e00")"]="1"  # 一
    ["$(printf "\\u4e8c")"]="2"  # 二
    ["$(printf "\\u4e09")"]="3"  # 三
    ["$(printf "\\u56db")"]="4"  # 四
    ["$(printf "\\u4e94")"]="5"  # 五
    ["$(printf "\\u516d")"]="6"  # 六
    ["$(printf "\\u4e03")"]="7"  # 七
    ["$(printf "\\u516b")"]="8"  # 八
    ["$(printf "\\u4e5d")"]="9"  # 九
    ["$(printf "\\u96f6")"]="0"  # 零
    ["$(printf "\\u5341")"]="10" # 十
    ["$(printf "\\u767e")"]="100" # 百
    ["$(printf "\\u5343")"]="1000" # 千
    ["$(printf "\\u4e07")"]="10000" # 万
    ["$(printf "\\u4ebf")"]="100000000" # 亿
)

# 单位字符的Unicode码点
units="$(printf "\\u5341")|$(printf "\\u767e")|$(printf "\\u5343")|$(printf "\\u4e07")|$(printf "\\u4ebf")"

# 中文数字转换函数
convert_chinese_number() {
    local chinese="$1"
    local result=0
    local temp_digit=0
    local char
    local digit_val
    
    if [[ $VERBOSE == true ]]; then
        echo "===== 转换中文数字: '$chinese' =====" >&2
    fi
    
    if [[ ${#chinese} -eq 1 ]]; then
        digit_val="${chinese_numbers[$chinese]}"
        if [[ -n "$digit_val" ]]; then
            echo "$digit_val"
            return 0
        else
            echo "错误：无法识别字符 '$chinese'" >&2
            return 1
        fi
    fi
    
    for ((i=0; i<${#chinese}; i++)); do
        char="${chinese:$i:1}"
        digit_val="${chinese_numbers[$char]}"
        
        if [[ $char =~ ^($units)$ ]]; then
            if [[ $temp_digit -ne 0 ]]; then
                result=$((result + temp_digit * digit_val))
                temp_digit=0
            elif [[ $result -eq 0 ]]; then
                result=$digit_val
            else
                echo "错误：连续单位字符 '$char'" >&2
                return 1
            fi
        elif [[ -n "$digit_val" ]]; then
            if [[ $temp_digit -eq 0 ]]; then
                temp_digit=$digit_val
            else
                temp_digit=$((temp_digit * 10 + digit_val))
            fi
        else
            echo "错误：未知字符 '$char'" >&2
            return 1
        fi
    done
    
    result=$((result + temp_digit))
    echo "$result"
    return 0
}

# 文件夹处理函数
process_folder() {
    local folder="$1"
    local folder_name=$(basename "$folder")
    local old_path="$folder"
    local new_name=""
    local new_path=""
    
    if [[ $folder_name =~ ^第(.+)话$ ]]; then
        local chinese_num="${BASH_REMATCH[1]}"
        local arabic_num=$(convert_chinese_number "$chinese_num")
        
        if [[ $? -eq 0 ]]; then
            new_name="第 $arabic_num 话"
            new_path="$(dirname "$folder")/$new_name"
            
            echo "$folder_name -> $new_name"
            
            if [[ $DRY_RUN == true ]]; then
                echo "  (预览) 重命名: $old_path -> $new_path" >&2
            else
                echo "  执行重命名: $old_path -> $new_path" >&2
                
                if [[ -e "$new_path" ]]; then
                    echo "  警告：目标文件夹已存在，跳过" >&2
                else
                    mv "$old_path" "$new_path"
                    if [[ $? -eq 0 ]]; then
                        echo "  重命名成功" >&2
                    else
                        echo "  错误：重命名失败" >&2
                    fi
                fi
            fi
        else
            echo "跳过 $folder_name: 数字转换失败" >&2
        fi
    elif [[ $VERBOSE == true ]]; then
        echo "跳过 $folder_name: 不符合格式" >&2
    fi
}

# 主程序
main() {
    check_bash_version
    parse_args "$@"
    check_path
    
    echo "===== 开始处理文件夹 =====" >&2
    echo "文件夹路径: $FOLDER_PATH" >&2
    
    local mode_text="执行模式"
    if [[ $DRY_RUN == true ]]; then
        mode_text="预览模式"
    fi
    echo "操作模式: $mode_text" >&2
    
    for folder in "$FOLDER_PATH"/*; do
        if [[ -d "$folder" ]]; then
            process_folder "$folder"
        fi
    done
    
    echo "===== 处理完成 =====" >&2
}

# 启动程序
main "$@"