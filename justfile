# manga 回归测试：用 pytest 跑 manga/tests 下全部用例
test:
    uv run --project manga pytest -c manga/pyproject.toml

# 同步 manga/src/*.py 到 manga/bin/ 命令垫片（新增/删除/重命名脚本，或改垫片模板后跑一次；平时改代码不用跑）
binsync:
    uv run --project manga python manga/src/_binsync.py
