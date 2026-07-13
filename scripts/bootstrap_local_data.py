"""
本地 CSV 数据初始化脚本

用法:
    cd J:\project\worldcup
    .venv\Scripts\python.exe scripts\bootstrap_local_data.py --season 2026 --use-llm
    .venv\Scripts\python.exe scripts\bootstrap_local_data.py --season 2026 --no-llm
"""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.bootstrap_service import bootstrap_local_data


def main():
    parser = argparse.ArgumentParser(description="Bootstrap local CSV data from API-Sports")
    parser.add_argument("--season", type=int, default=2026, help="World Cup season (default: 2026)")
    parser.add_argument("--use-llm", action="store_true", default=True, help="Use ZhipuAI to assist (default)")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM assistance")
    args = parser.parse_args()

    use_llm = not args.no_llm

    print(f"[bootstrap] season={args.season}, use_llm={use_llm}")
    result = bootstrap_local_data(season=args.season, use_llm=use_llm)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
