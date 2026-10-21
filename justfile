# 回归测试：跑 tests/ 下全部用例
test:
    uv run pytest

# 同步全仓库脚本到根目录 bin/ 命令垫片（新增/删除/重命名脚本，或改垫片模板后跑一次；平时改代码不用跑）
binsync:
    uv run --project . python tools/binsync.py
