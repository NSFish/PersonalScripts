"""批量把 zip 压缩包内的图片转为 AVIF。

已并入 convert_image_format_to.py，本脚本仅为兼容老用法的薄垫片：
实际执行 `convert_image_format_to.py avif <输入文件夹>`，输出到输入父目录的 `result/`。
"""
import sys


def main() -> None:
    if len(sys.argv) != 2:
        print(f"使用方法: python3 {sys.argv[0]} /path/to/输入文件夹")
        sys.exit(1)
    print("ℹ️ 本脚本已并入 convert_image_format_to.py，转交它执行（固定 avif 格式）")
    import convert_image_format_to as converter

    sys.exit(converter.main(["avif", sys.argv[1]]))


if __name__ == '__main__':
    main()
