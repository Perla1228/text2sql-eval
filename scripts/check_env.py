"""环境自检脚本：验证 Python / 依赖 / sqlite / API Key 是否就绪。

用法：
    python scripts/check_env.py
退出码：0 全绿，1 有未通过项。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"[{mark}] {name}" + (f"  -> {detail}" if detail else ""))
    return ok


def main() -> int:
    results: list[bool] = []

    # 1. Python 版本
    py_ver = sys.version_info
    ok = py_ver >= (3, 11)
    results.append(check("Python >= 3.11", ok, f"当前 {py_ver.major}.{py_ver.minor}.{py_ver.micro}"))

    # 2. 关键依赖
    try:
        import evalscope

        results.append(check("evalscope 可导入", True, evalscope.__version__))
    except Exception as e:  # noqa: BLE001
        results.append(check("evalscope 可导入", False, str(e)))

    for mod in ("pandas", "dotenv", "streamlit"):
        try:
            __import__(mod)
            results.append(check(f"{mod} 可导入", True))
        except Exception as e:  # noqa: BLE001
            results.append(check(f"{mod} 可导入", False, str(e)))

    # 3. sqlite3
    try:
        import sqlite3

        results.append(check("sqlite3 可用", True, sqlite3.sqlite_version))
    except Exception as e:  # noqa: BLE001
        results.append(check("sqlite3 可用", False, str(e)))

    # 4. 加载 .env 并检查 API Key
    try:
        from dotenv import load_dotenv

        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            keys = {
                "DASHSCOPE_API_KEY": os.getenv("DASHSCOPE_API_KEY"),
                "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
                "ZHIPU_API_KEY": os.getenv("ZHIPU_API_KEY"),
            }
            present = [k for k, v in keys.items() if v and not v.startswith("sk-your-") and v != "your-zhipu-key-here"]
            if present:
                results.append(check(".env 中至少一个 API Key 已配置", True, ", ".join(present)))
            else:
                results.append(check(".env 中至少一个 API Key 已配置", False, "请复制 .env.example 为 .env 并填入真实 key"))
        else:
            results.append(check(".env 中至少一个 API Key 已配置", False, f"未找到 {env_path}，请复制 .env.example 为 .env"))
    except Exception as e:  # noqa: BLE001
        results.append(check("加载 .env", False, str(e)))

    print()
    if all(results):
        print(f"{GREEN}环境自检全部通过，可以开工。{RESET}")
        return 0
    print(f"{YELLOW}有未通过项，请按上面的 FAIL 提示修复后重试。{RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
