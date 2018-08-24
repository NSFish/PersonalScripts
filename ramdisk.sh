#!/bin/bash
# 设置 ram disk 的名称
RAMDISK=Ramdisk

# 设置 ram disk 的大小，这里是 1024 MB
SIZE=1024  

# 分配给 ramdisk 相应大小的空间
diskutil erasevolume HFS+ $RAMDISK `hdiutil attach -nomount ram://$[SIZE*2048]` 

# 打开元数据索引，如果你使用 Xcode 内部的调试工具这是必须的。因为调试工具使用元数据索引来查询符号连接
mdutil -i on /Volumes/$RAMDISK