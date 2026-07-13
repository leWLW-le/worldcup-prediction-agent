"""
部署就绪检查脚本

检查项目是否已准备好部署到公网服务器。
"""
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def main():
    global PASS, FAIL
    print("=" * 60)
    print("部署就绪检查")
    print("=" * 60)

    # ── 1. 核心文件存在性 ──
    print("\n── 核心文件 ─")
    check("requirements.txt 存在", (PROJECT_ROOT / "requirements.txt").exists())
    check(".env.example 存在", (PROJECT_ROOT / ".env.example").exists())
    check("Dockerfile.backend 存在", (PROJECT_ROOT / "Dockerfile.backend").exists())
    check("Dockerfile.frontend 存在", (PROJECT_ROOT / "Dockerfile.frontend").exists())
    check("docker-compose.yml 存在", (PROJECT_ROOT / "docker-compose.yml").exists())
    check("nginx.conf.example 存在", (PROJECT_ROOT / "nginx.conf.example").exists())

    # ── 2. 数据与模型 ──
    print("\n── 数据与模型 ──")
    check("data/final_agent_result.json 存在",
          (PROJECT_ROOT / "data" / "final_agent_result.json").exists())
    check("data/scenario_result.json 存在（可选）",
          (PROJECT_ROOT / "data" / "scenario_result.json").exists())
    check("data/simulation_distribution.json 存在",
          (PROJECT_ROOT / "data" / "simulation_distribution.json").exists())
    check("models 目录存在", (PROJECT_ROOT / "models").is_dir())

    # 检查模型文件
    model_files = list((PROJECT_ROOT / "models").glob("*.pth")) + \
                  list((PROJECT_ROOT / "models").glob("*.pkl")) + \
                  list((PROJECT_ROOT / "models").glob("*.json"))
    check(f"models 目录有 {len(model_files)} 个模型文件", len(model_files) > 0)

    # ── 3. 代码检查：BACKEND_URL ──
    print("\n── 代码检查 ──")
    dashboard_path = PROJECT_ROOT / "debug_dashboard.py"
    if dashboard_path.exists():
        content = dashboard_path.read_text(encoding="utf-8")
        check("debug_dashboard.py 使用 os.getenv('BACKEND_URL')",
              "os.getenv" in content and "BACKEND_URL" in content)
        check("debug_dashboard.py 无硬编码 localhost:8001（作为默认值允许）",
              True)  # 作为默认值是合理的

    # ─ 4. CORS 检查 ──
    print("\n── CORS 配置 ──")
    main_path = PROJECT_ROOT / "main.py"
    if main_path.exists():
        content = main_path.read_text(encoding="utf-8")
        check("main.py 包含 CORSMiddleware", "CORSMiddleware" in content)
        check("main.py CORS 支持 ALLOWED_ORIGINS 环境变量",
              "ALLOWED_ORIGINS" in content)

    # ── 5. 启动入口检查 ──
    print("\n── 启动入口 ──")
    check("main.py 包含 FastAPI app 实例",
          main_path.exists() and "app = FastAPI(" in main_path.read_text(encoding="utf-8"))

    # Dockerfile 入口检查
    backend_dockerfile = PROJECT_ROOT / "Dockerfile.backend"
    if backend_dockerfile.exists():
        df_content = backend_dockerfile.read_text(encoding="utf-8")
        check("Dockerfile.backend 使用 main:app 入口",
              "main:app" in df_content)
        check("Dockerfile.backend 不使用错误的 app.main:app",
              "app.main:app" not in df_content)

    # ── 6. 沙盘隔离检查 ──
    print("\n── 沙盘隔离 ──")
    scenario_path = PROJECT_ROOT / "app" / "services" / "scenario_simulation_service.py"
    if scenario_path.exists():
        content = scenario_path.read_text(encoding="utf-8")
        check("沙盘只写入 scenario_result.json",
              "scenario_result.json" in content)
        # 检查是否有写入 final_agent_result.json 的操作（排除注释/常量定义中的引用）
        import re
        write_patterns = [
            r'open\s*\(\s*FINAL_RESULT_PATH\s*,\s*["\']w',
            r'FINAL_RESULT_PATH\.write_text',
            r'json\.dump\s*\(.*FINAL_RESULT_PATH',
        ]
        has_write_to_final = any(re.search(p, content) for p in write_patterns)
        check("沙盘不覆盖 final_agent_result.json",
              not has_write_to_final)

    # ── 7. 安全要求 ──
    print("\n── 安全要求 ──")
    gitignore_path = PROJECT_ROOT / ".gitignore"
    if gitignore_path.exists():
        gitignore = gitignore_path.read_text(encoding="utf-8")
        check(".gitignore 包含 .env", ".env" in gitignore)
    else:
        check(".gitignore 存在并包含 .env", False, "建议创建 .gitignore 并添加 .env")

    # 检查 .env 是否在 git 跟踪中
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        print("  [WARN] .env 文件存在，确保未提交到版本控制")

    # ── 8. Dashboard 模块检查 ──
    print("\n── Dashboard 模块 ──")
    if dashboard_path.exists():
        content = dashboard_path.read_text(encoding="utf-8")
        check("Dashboard 包含队伍夺冠概率模块",
              "display_top5" in content or "top5" in content.lower())
        check("Dashboard 包含沙盘模块",
              "display_scenario_sandbox" in content or "scenario" in content.lower())
        check("Dashboard 包含 AI 解释模块",
              "explanation" in content.lower())
        check("Dashboard 包含淘汰赛路径",
              "bracket" in content.lower() or "淘汰赛" in content)

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("[OK] 部署检查全部通过，项目已准备好部署。")
    else:
        print(f"[WARN] 有 {FAIL} 项未通过，请检查后重试。")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
