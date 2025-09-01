"""
图片裁剪与拼接脚本
用法: script.py -u|-d|-l|-r <number> <image1_path> <image2_path>
选项:
  -u, --up      向上裁剪拼接
  -d, --down    向下裁剪拼接
  -l, --left    向左裁剪拼接
  -r, --right   向右裁剪拼接
参数:
  number: 裁剪尺寸（像素）
  image1_path: 第一张图片路径
  image2_path: 第二张图片路径
示例: script.py -u 300 image1.jpg image2.jpg
"""

import sys
import argparse
import os
from PIL import Image

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='图片裁剪与拼接工具', add_help=False)
    
    # 方向参数（互斥组）
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-u', '--up', action='store_true', help='向上裁剪拼接')
    group.add_argument('-d', '--down', action='store_true', help='向下裁剪拼接')
    group.add_argument('-l', '--left', action='store_true', help='向左裁剪拼接')
    group.add_argument('-r', '--right', action='store_true', help='向右裁剪拼接')
    
    # 其他参数
    parser.add_argument('number', type=int, help='裁剪尺寸（像素）')
    parser.add_argument('image1_path', help='第一张图片路径')
    parser.add_argument('image2_path', help='第二张图片路径')
    parser.add_argument('-h', '--help', action='help', help='显示帮助信息')
    
    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        print(f"参数错误: {e}")
        print(__doc__)
        sys.exit(1)
    
    # 确定方向
    if args.up:
        direction = 'up'
    elif args.down:
        direction = 'down'
    elif args.left:
        direction = 'left'
    elif args.right:
        direction = 'right'
    else:
        raise ValueError("必须指定一个方向参数")
    
    return direction, args.number, args.image1_path, args.image2_path

def process_images(direction, number, img1_path, img2_path):
    """处理图片裁剪与拼接"""
    # 打开图片
    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)
    
    # 获取图片尺寸
    width1, height1 = img1.size
    width2, height2 = img2.size
    
    # 验证图片尺寸是否相同
    if (width1, height1) != (width2, height2):
        raise ValueError("两张图片的尺寸必须完全相同")
    
    # 根据方向验证数字参数有效性
    if direction in ['up', 'down']:
        if number >= height1:
            raise ValueError(f"当方向为 '{direction}' 时，数字必须小于图片高度 ({height1})")
    else:  # left 或 right
        if number >= width1:
            raise ValueError(f"当方向为 '{direction}' 时，数字必须小于图片宽度 ({width1})")
    
    # 根据方向进行裁剪和拼接
    if direction == 'up':
        # 从img1裁剪顶部部分，高度为number
        part_a = img1.crop((0, 0, width1, number))
        # 从img2裁剪底部部分，高度为height2 - number
        part_b = img2.crop((0, number, width2, height2))
        # 垂直拼接
        result = Image.new('RGB', (width1, height1))
        result.paste(part_a, (0, 0))
        result.paste(part_b, (0, number))
        
    elif direction == 'down':
        # 从img1裁剪底部部分，高度为number
        part_a = img1.crop((0, height1 - number, width1, height1))
        # 从img2裁剪顶部部分，高度为height2 - number
        part_b = img2.crop((0, 0, width2, height2 - number))
        # 垂直拼接
        result = Image.new('RGB', (width1, height1))
        result.paste(part_b, (0, 0))
        result.paste(part_a, (0, height2 - number))
        
    elif direction == 'left':
        # 从img1裁剪左侧部分，宽度为number
        part_a = img1.crop((0, 0, number, height1))
        # 从img2裁剪右侧部分，宽度为width2 - number
        part_b = img2.crop((number, 0, width2, height2))
        # 水平拼接
        result = Image.new('RGB', (width1, height1))
        result.paste(part_a, (0, 0))
        result.paste(part_b, (number, 0))
        
    elif direction == 'right':
        # 从img1裁剪右侧部分，宽度为number
        part_a = img1.crop((width1 - number, 0, width1, height1))
        # 从img2裁剪左侧部分，宽度为width2 - number
        part_b = img2.crop((0, 0, width2 - number, height2))
        # 水平拼接
        result = Image.new('RGB', (width1, height1))
        result.paste(part_b, (0, 0))
        result.paste(part_a, (width2 - number, 0))
    
    return result

def main():
    try:
        # 解析参数
        direction, number, img1_path, img2_path = parse_args()
        
        # 处理图片
        result_image = process_images(direction, number, img1_path, img2_path)
        
        # 获取输入图片的目录（使用第一张图片的目录）
        output_dir = os.path.dirname(img1_path)
        # 如果输入图片没有目录（当前目录），则使用当前工作目录
        if not output_dir:
            output_dir = os.getcwd()
        
        # 生成输出文件名（保留原始图片的扩展名）
        _, ext = os.path.splitext(img1_path)
        output_filename = f"result_{direction}_{number}{ext}"
        # 拼接输出路径（放在输入图片的旁边）
        output_path = os.path.join(output_dir, output_filename)
        
        # 保存结果
        result_image.save(output_path)
        print(f"处理成功！结果已保存为: {output_path}")
        
    except Exception as e:
        print(f"错误: {e}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()