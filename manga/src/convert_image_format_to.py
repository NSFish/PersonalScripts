import os
import shutil
import subprocess
import sys

from _common import natural_key

# primage 的 -f 接受 jpeg/png/webp/avif，jpg 需映射为 jpeg
VALID_FORMATS = ('jpg', 'jpeg', 'png', 'webp', 'avif')


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

    # 只处理文件，按文件名自然升序排序
    file_list = sorted(
        (f for f in os.listdir(input_folder)
         if os.path.isfile(os.path.join(input_folder, f))),
        key=natural_key,
    )

    # 遍历排序后的文件列表
    failures = 0
    for filename in file_list:
        if not filename.lower().endswith(exts):
            continue
        input_path = os.path.join(input_folder, filename)
        name, _ = os.path.splitext(filename)
        output_path = os.path.join(output_folder, f"{name}.{out_format}")

        # 使用 primage 转换格式（-q 90 保证高质量；primage 重新编码，默认不带原图元数据）
        primage_fmt = "jpeg" if out_format in ("jpg", "jpeg") else out_format
        try:
            subprocess.run([
                "primage", "-f", primage_fmt, "-q", "90", "-o", output_path, input_path
            ], check=True, capture_output=True, text=True)
            print(f"✅ 转换成功: {input_path} -> {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ 转换失败: {filename}，错误: {e.stderr}")
            failures += 1

    return failures


def main():
    if len(sys.argv) != 3:
        print(f"用法: python {sys.argv[0]} <输出图片格式> <图片文件夹路径>")
        print(f"支持的格式: {'/'.join(VALID_FORMATS)}")
        sys.exit(1)
    out_format = sys.argv[1].lower()
    input_folder = sys.argv[2]
    if out_format not in VALID_FORMATS:
        print(f"❌ 错误：不支持的输出格式 '{out_format}'（支持: {'/'.join(VALID_FORMATS)}）")
        sys.exit(1)
    # 检查输入文件夹是否存在
    if not os.path.isdir(input_folder):
        print(f"❌ 错误：输入文件夹 '{input_folder}' 不存在或不是有效文件夹")
        sys.exit(1)
    failures = convert_images(input_folder, out_format)
    if failures:
        print(f"\n❌ 共 {failures} 张图片转换失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
