# manga 回归测试：用 pytest 跑 manga/tests 下全部用例
test:
    uv run --project manga pytest -c manga/pyproject.toml
