import argparse
import os
from PIL import Image

def parse_arguments():
    parser = argparse.ArgumentParser(description='水平或垂直拼接图片')

    # 创建互斥参数组
    direction_group = parser.add_mutually_exclusive_group(required=True)
    direction_group.add_argument('-H', '--horizontal', 
                                action='store_true', 
                                help='水平拼接（需图片高度一致）')
    direction_group.add_argument('-V', '--vertical', 
                                action='store_true', 
                                help='垂直拼接（需图片宽度一致）')

    # 添加位置参数
    parser.add_argument('image1', help='第一张图片路径')
    parser.add_argument('image2', help='第二张图片路径')

    return parser.parse_args()

def validate_images(image1_path, image2_path, direction):
    """验证图片存在性和尺寸匹配"""
    if not (os.path.exists(image1_path) and os.path.exists(image2_path)):
        raise FileNotFoundError("输入的图片路径不存在")

    with Image.open(image1_path) as img1, Image.open(image2_path) as img2:
        width1, height1 = img1.size
        width2, height2 = img2.size

        if direction == 'horizontal':
            if height1 != height2:
                raise ValueError(f"水平拼接要求图片高度一致，当前高度分别为：{height1}px 和 {height2}px")
            return (width1 + width2, height1)
        else:
            if width1 != width2:
                raise ValueError(f"垂直拼接要求图片宽度一致，当前宽度分别为：{width1}px 和 {width2}px")
            return (width1, height1 + height2)

def merge_images(direction, image1_path, image2_path):
    """执行图片拼接"""
    with Image.open(image1_path) as img1, Image.open(image2_path) as img2:
        if direction == 'horizontal':
            new_img = Image.new('RGB', (img1.width + img2.width, img1.height))
            new_img.paste(img1, (0, 0))
            new_img.paste(img2, (img1.width, 0))
        else:
            new_img = Image.new('RGB', (img1.width, img1.height + img2.height))
            new_img.paste(img1, (0, 0))
            new_img.paste(img2, (0, img1.height))
        return new_img

def main():
    try:
        args = parse_arguments()
        direction = 'horizontal' if args.horizontal else 'vertical'

        # 验证图片参数
        output_size = validate_images(args.image1, args.image2, direction)

        # 执行拼接
        merged_image = merge_images(direction, args.image1, args.image2)

        # 生成输出路径
        base_dir = os.path.dirname(os.path.commonprefix([args.image1, args.image2]))
        output_name = f"merged_{os.path.basename(args.image1)}_{os.path.basename(args.image2)}.jpg"
        output_path = os.path.join(base_dir, output_name)

        merged_image.save(output_path)
        print(f"拼接成功！图片已保存至：{output_path}")

    except Exception as e:
        print(f"错误：{str(e)}")
        print("用法示例：python script.py -H image1.jpg image2.jpg")

if __name__ == "__main__":
    main()