import os
import re
import shutil
import subprocess
import sys

def natural_sort_key(s):
    """生成自然排序的key，处理文件名中的数字"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def convert_images(input_folder, out_format):
    # 获取输出文件夹路径
    base_dir = os.path.dirname(os.path.abspath(input_folder))
    folder_name = os.path.basename(os.path.abspath(input_folder))
    output_folder = os.path.join(base_dir, f"{folder_name}_{out_format}")

    # 如果输出文件夹存在，删除后重新创建
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder)

    # 支持的图片格式
    exts = ('.webp', '.avif', '.png', '.jpeg', '.jpg')

    # 获取文件夹内所有文件并按文件名自然升序排序
    file_list = os.listdir(input_folder)
    file_list.sort(key=natural_sort_key)  # 按自然排序（兼容数字）从小到大

    # 遍历排序后的文件列表
    for filename in file_list:
        if filename.lower().endswith(exts):
            input_path = os.path.join(input_folder, filename)
            name, _ = os.path.splitext(filename)
            output_path = os.path.join(output_folder, f"{name}.{out_format}")

            # 使用imagemagick的magick命令进行转换，并去除 profile 和 metadata
            try:
                subprocess.run([
                    "magick", input_path, "-strip", output_path
                ], check=True, capture_output=True, text=True)
                print(f"✅ 转换成功: {input_path} -> {output_path}")
            except subprocess.CalledProcessError as e:
                print(f"❌ 转换失败: {filename}，错误: {e.stderr}")

def main():
    if len(sys.argv) != 3:
        print("用法: python convert_image_format_to.py <输出图片格式> <图片文件夹路径>")
        sys.exit(1)
    out_format = sys.argv[1].lower()
    input_folder = sys.argv[2]
    # 检查输入文件夹是否存在
    if not os.path.isdir(input_folder):
        print(f"❌ 错误：输入文件夹 '{input_folder}' 不存在或不是有效文件夹")
        sys.exit(1)
    convert_images(input_folder, out_format)

if __name__ == "__main__":
    main()