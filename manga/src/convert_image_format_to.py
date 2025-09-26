import os
import shutil
import subprocess
import sys

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

    # 遍历输入文件夹
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(exts):
            input_path = os.path.join(input_folder, filename)
            name, _ = os.path.splitext(filename)
            output_path = os.path.join(output_folder, f"{name}.{out_format}")

            # 使用imagemagick的magick命令进行转换，并去除 profile 和 metadata
            try:
                subprocess.run([
                    "magick", input_path, "-strip", output_path
                ], check=True)
                print(f"✅ 转换成功: {input_path} -> {output_path}")
            except subprocess.CalledProcessError as e:
                print(f"❌ 转换失败: {filename}，错误: {e}")

def main():
    if len(sys.argv) != 3:
        print("用法: python convert_image_format_to_jpg.py <输出图片格式> <图片文件夹路径>")
        sys.exit(1)
    out_format = sys.argv[1].lower()
    input_folder = sys.argv[2]
    convert_images(input_folder, out_format)

if __name__ == "__main__":
    main()