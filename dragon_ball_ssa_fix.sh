# TODO: 
# 1. 龙珠 Z 的第 273 集和龙珠 GT 的特典并不是 UTF-16LE 而是 UTF-8 with BOM，转换会失败，因此需要能预读文件的编码再予以处理
# 2. 文件开头是否有需要移除的空格也需要检查

# =======================================七龙珠=====================================================
# 字幕文件编码为 UTF-8 with BOM，而 BOM 在非 Windows 设备上是多余的，移除掉
cd 01\ ドラゴンボール字幕/
find . -name "*.ssa" -exec sed -i '1s/^\xEF\xBB\xBF//' {} +
cd ..

# =======================================龙珠 Z=====================================================
cd 02\ ドラゴンボールゼット字幕/
# 将 UTF-16LE 转换成 UTF-8
# 如果显式指定 -f 为 UTF-16LE，转换出来的文件编码会是 UTF-8 with BOM
# 故使用 UTF-16，原理未知 https://stackoverflow.com/a/11571759/2135264
# iconv 不支持直接修改源文件，因此将输出文件加上后缀 .utf8
find . -name "*.ssa" -exec sh -c 'iconv -f UTF-16 -t UTF-8 "{}" > "{}.utf8"' \;

# 删除之前的 .ssa 文件
find . -name "*.ssa" -print0 | xargs -0 rm

# 移除 .utf8 后缀
find . -name "*.utf8" -exec rename 's/\.utf8$//' {} +

# 移除文件首行 [Script Info] 之前的空格
find . -name "*.ssa" -exec sed -i '1s/.//' {} +;

cd ..

# =======================================龙珠 GT=====================================================
cd 03\ ドラゴンボールジーティー字幕/

find . -name "*.ssa" -exec sh -c 'iconv -f UTF-16 -t UTF-8 "{}" > "{}.utf8"' \;
find . -name "*.ssa" -print0 | xargs -0 rm
find . -name "*.utf8" -exec rename 's/\.utf8$//' {} +

cd ..