#!/usr/bin/env python3
"""Render 部署就绪检查脚本

验证项目是否具备通过 GitHub + Render 部署的全部条件。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PASS = 0
FAIL = 0


def check(ok: bool, label: str):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}")


def main():
    print("=" * 60)
    print("Render 部署就绪检查")
    print("=" * 60)

    # ── 1. render.yaml 存在 ──
    render_yaml_exists = os.path.isfile("render.yaml")
    check(render_yaml_exists, "render.yaml 存在")

    # ── 读取 render.yaml 内容 ──
    render_content = ""
    if render_yaml_exists:
        with open("render.yaml", "r", encoding="utf-8") as f:
            render_content = f.read()

    # ── 2. render.yaml 包含 worldcup-backend ──
    check("worldcup-backend" in render_content, "render.yaml 包含 worldcup-backend")

    # ── 3. render.yaml 包含 worldcup-frontend ──
    check("worldcup-frontend" in render_content, "render.yaml 包含 worldcup-frontend")

    # ── 4. backend startCommand 使用 $PORT ──
    backend_port = bool(re.search(
        r"startCommand:.*uvicorn.*\$PORT", render_content
    ))
    check(backend_port, "backend startCommand 使用 $PORT")

    # ── 5. frontend startCommand 使用 $PORT ──
    frontend_port = bool(re.search(
        r"startCommand:.*streamlit.*\$PORT", render_content
    ))
    check(frontend_port, "frontend startCommand 使用 $PORT")

    # ── 6. frontend 环境变量包含 BACKEND_URL ──
    has_backend_url = "BACKEND_URL" in render_content
    check(has_backend_url, "frontend 环境变量包含 BACKEND_URL")

    # ── 7. debug_dashboard.py 使用 BACKEND_URL ──
    dashboard_file = "debug_dashboard.py"
    dashboard_ok = False
    if os.path.isfile(dashboard_file):
        with open(dashboard_file, "r", encoding="utf-8") as f:
            dashboard_content = f.read()
        dashboard_ok = "BACKEND_URL" in dashboard_content
    check(dashboard_ok, "debug_dashboard.py 使用 BACKEND_URL")

    # ── 8. main.py 配置 CORS ──
    main_file = "main.py"
    cors_ok = False
    if os.path.isfile(main_file):
        with open(main_file, "r", encoding="utf-8") as f:
            main_content = f.read()
        cors_ok = "CORSMiddleware" in main_content
    check(cors_ok, "main.py 配置 CORS")

    # ── 9. requirements.txt 存在 ──
    check(os.path.isfile("requirements.txt"), "requirements.txt 存在")

    # ── 10. .env.example 存在 ──
    check(os.path.isfile(".env.example"), ".env.example 存在")

    # ── 11. .gitignore 忽略 .env ──
    gitignore_ok = False
    if os.path.isfile(".gitignore"):
        with open(".gitignore", "r", encoding="utf-8") as f:
            gi = f.read()
        gitignore_ok = bool(re.search(r"^\.env", gi, re.MULTILINE))
    check(gitignore_ok, ".gitignore 忽略 .env")

    # ── 12. data/final_agent_result.json 存在 ──
    check(os.path.isfile("data/final_agent_result.json"),
          "data/final_agent_result.json 存在")

    # ── 13. models/tree_predictor.pkl 存在 ──
    check(os.path.isfile("models/tree_predictor.pkl"),
          "models/tree_predictor.pkl 存在")

    # ── 14. models/feature_network_v2_latest.pth 存在 ──
    check(os.path.isfile("models/feature_network_v2_latest.pth"),
          "models/feature_network_v2_latest.pth 存在")

    # ── 15. 不包含真实 API Key ──
    real_key_found = False
    skip_dirs = {".venv", ".git", "__pycache__", "node_modules"}
    skip_exts = {".pyc", ".pth", ".pkl", ".db", ".sqlite", ".sqlite3", ".md"}
    skip_files = {".env", ".env.local", ".env.example", ".gitignore"}
    # 匹配 sk- 后跟至少20位混合字符（排除 sk-xxxx 纯占位符）
    key_pattern = re.compile(r"sk-(?=[a-zA-Z0-9]*[a-zA-Z])(?=[a-zA-Z0-9]*\d)[a-zA-Z0-9]{20,}")

    for root_dir, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname in skip_files:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in skip_exts:
                continue
            fpath = os.path.join(root_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    if key_pattern.search(content):
                        real_key_found = True
                        print(f"  [WARN] 疑似真实 key: {fpath}")
            except Exception:
                pass

    check(not real_key_found, "不包含真实 API Key (sk-...)")

    # ── 汇总 ──
    total = PASS + FAIL
    print()
    print("=" * 60)
    print(f"结果: {PASS}/{total} 通过, {FAIL} 失败")
    print("=" * 60)

    if FAIL == 0:
        print("[OK] Render 部署就绪检查全部通过!")
        return 0
    else:
        print("[FAIL] 有检查未通过，请修复后重试。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
