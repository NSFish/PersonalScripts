import os
import sys
import argparse
import shutil
from PIL import Image

def is_double_page(image_path):
    """判断图片是否为双页：只要宽度大于高度就判定为双页"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            # 宽度大于高度即视为双页
            return width > height
    except Exception as e:
        print(f"分析图片 {image_path} 时出错: {e}")
        return False

def split_double_page(image_path, output_dir):
    """将双页图片拆分为单页，右侧图片文件名在前"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # 计算分割点（中间位置）
            split_pos = width // 2

            # 分割为左右两页
            left_page = img.crop((0, 0, split_pos, height))
            right_page = img.crop((split_pos, 0, width, height))

            # 获取文件名和扩展名
            filename = os.path.basename(image_path)
            name, ext = os.path.splitext(filename)

            # 保存分割后的图片，右侧用01，左侧用02，确保右侧在前
            right_path = os.path.join(output_dir, f"{name}_01{ext}")  # 右侧图片
            left_path = os.path.join(output_dir, f"{name}_02{ext}")   # 左侧图片

            right_page.save(right_path)
            left_page.save(left_path)

            print(f"已拆分: {filename} -> {os.path.basename(right_path)} (右) 和 {os.path.basename(left_path)} (左)")
            return True
    except Exception as e:
        print(f"拆分图片 {image_path} 时出错: {e}")
        return False

def process_directory(input_dir):
    """处理目录中的所有图片"""
    # 获取输入目录的父目录和名称
    input_parent = os.path.dirname(input_dir)
    input_basename = os.path.basename(input_dir)

    # 输出文件夹名称格式：输入文件夹名称_split
    # 这样能清晰对应到原始输入文件夹
    output_dir = os.path.join(input_parent, f"{input_basename}_split")
    os.makedirs(output_dir, exist_ok=True)

    # 支持的图片格式
    supported_formats = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff')

    # 遍历目录中的所有文件
    for filename in os.listdir(input_dir):
        file_path = os.path.join(input_dir, filename)

        # 只处理文件和支持的图片格式
        if os.path.isfile(file_path) and filename.lower().endswith(supported_formats):
            # 判断是否为双页
            if is_double_page(file_path):
                split_double_page(file_path, output_dir)
            else:
                # 单页图片直接复制到输出目录，保持原文件名
                try:
                    dest_path = os.path.join(output_dir, filename)
                    shutil.copy2(file_path, dest_path)
                    print(f"复制单页图片: {filename}")
                except Exception as e:
                    print(f"复制单页图片 {filename} 时出错: {e}")

    return output_dir

def main():
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='将漫画双页图片批量拆分为单页（带对应关系的输出文件夹）')
    parser.add_argument('input_dir', help='包含漫画图片的目录路径')

    # 解析参数
    args = parser.parse_args()

    # 验证输入目录是否存在
    if not os.path.isdir(args.input_dir):
        print(f"错误: 目录 '{args.input_dir}' 不存在")
        sys.exit(1)

    # 处理目录
    print(f"开始处理目录: {args.input_dir}")
    output_dir = process_directory(args.input_dir)
    print(f"处理完成，拆分后的图片保存在: {output_dir}")

if __name__ == "__main__":
    main()
