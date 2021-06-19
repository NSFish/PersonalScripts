# 删除名侦探柯南字幕文件中的无用文案

# 0. 将所有字幕文件由 UTF-8 with BOM 转换为 UTF-8
# 字幕文件编码为 UTF-8 with BOM，而 BOM 在非 Windows 设备上是多余的
# find . -name "*.ass" -exec sed -i '1s/^\xEF\xBB\xBF//' {} +

# # 1. 删除 [Aegisub Project Garbage] section
# # 9 行内容加本 section 底部的空行
# find . -name "*.ass" -exec sed -i '/\[Aegisub Project Garbage\]/, +10d' {} +

# # 2. 删除注释
# find . -name "*.ass" -exec sed -i '/Comment:/d' {} +

# # 3. 删除字幕组相关信息
# #    3.1 标题处显示的论坛、微信公众号
# #    3.2 OP、ED 后赞助商处显示的字幕组名
# find . -name "*.ass" -exec sed -i '/银色子弹字幕组/d' {} +
# find . -name "*.ass" -exec sed -i '/讨论群/d' {} +

# # 4. 删除"Staff_2"，也就是银色子弹字幕组成员的名单（包括 ED 结尾的特别鸣谢）
# # 发现部分剧集中把字幕组成员归入了 Staff_1，也就是日方制作人员中，这部分只好手动删除
# find . -name "*.ass" -exec sed -i '/Staff_2/d' {} +

# # 5. 删除"数码重映 第X集"的提示
# find . -name "*.ass" -exec sed -i '/数码重映/d' {} +

# # 6. 删除"不允许用于任何商业用途"
# find . -name "*.ass" -exec sed -i '/商业用途/d' {} +

