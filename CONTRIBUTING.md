# 贡献指南

## 这个文件的用途

`CONTRIBUTING.md` 用来约束协作者如何在本仓库提交代码，避免目录结构混乱、测试入口不一致、脚本和测试职责混杂。新成员在开始改动前应先读这个文件。

## 后端结构规则

- 自动化测试统一放在 `backend/tests/`，并使用 pytest 可发现命名（`test_*.py`）。
- `backend/scripts/` 只用于工具/运维脚本，不放测试用例。

## 常用开发命令

```bash
cd backend

# 运行测试
pytest -q tests

# 运行分层依赖检查
python scripts/check_layer_dependencies.py
```
