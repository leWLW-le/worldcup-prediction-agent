"""
手动全量刷新脚本

流程: 刷新 fixtures → 识别存活球队 → Monte Carlo 模拟 → 更新 final_agent_result.json

用法:
    python scripts/run_full_refresh.py
    python scripts/run_full_refresh.py --season 2026 --simulations 10000
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="全量刷新: 赛程→存活球队→模拟→结果")
    parser.add_argument("--season", type=int, default=2026, help="世界杯赛季")
    parser.add_argument("--simulations", type=int, default=10000, help="Monte Carlo 模拟次数")
    args = parser.parse_args()

    from app.services.scheduled_refresh_service import run_full_refresh_pipeline

    print("=" * 60)
    print(f"全量刷新 — season={args.season}, simulations={args.simulations}")
    print("=" * 60)

    result = run_full_refresh_pipeline(
        season=args.season,
        n_simulations=args.simulations,
    )

    # 打印结果摘要
    print("\n" + "=" * 60)
    if result.get("success"):
        print("全量刷新完成 ✓")
    else:
        print("全量刷新部分失败 ✗")

    for step_name, step_data in result.get("steps", {}).items():
        status = "✓" if step_data.get("success") else "✗"
        print(f"  [{status}] {step_name}")
        if step_name == "identify_surviving" and step_data.get("success"):
            print(f"       stage={step_data.get('stage')}, "
                  f"surviving={step_data.get('surviving_teams')}, "
                  f"eliminated={step_data.get('eliminated_count')}")
        if step_name == "simulation" and step_data.get("success"):
            print(f"       top={step_data.get('top_champion')} "
                  f"({(step_data.get('top_probability') or 0) * 100:.1f}%), "
                  f"n={step_data.get('n_simulations')}")

    print("=" * 60)


if __name__ == "__main__":
    main()
