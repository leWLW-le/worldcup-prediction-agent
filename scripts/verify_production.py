#!/usr/bin/env python3
"""
生产环境验证脚本

验证 Render 后端部署后所有关键接口是否正常。

用法:
    python scripts/verify_production.py --backend-url https://worldcup-backend-k2sn.onrender.com
"""
import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("[FAIL] requests 库未安装，请先 pip install requests")
    sys.exit(1)


class ProductionVerifier:
    """生产环境验证器"""

    def __init__(self, base_url: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.verbose = verbose
        self.results: List[Dict] = []
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, timeout: int = 30) -> Optional[requests.Response]:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        try:
            resp = self.session.get(url, timeout=timeout)
            return resp
        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] GET {url}: {e}")
            return None

    def _post(self, path: str, json_data: dict, timeout: int = 60) -> Optional[requests.Response]:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        try:
            resp = self.session.post(url, json=json_data, timeout=timeout)
            return resp
        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] POST {url}: {e}")
            return None

    def _record(self, test_name: str, passed: bool, detail: str = ""):
        self.results.append({"test": test_name, "passed": passed, "detail": detail})
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test_name}" + (f" — {detail}" if detail else ""))

    # ── 1. 健康检查 ──
    def verify_health(self):
        print("\n== 1. 健康检查 GET /health ==")
        resp = self._get("/health")
        if resp is None:
            self._record("health_reachable", False, "无法连接")
            return False
        if resp.status_code != 200:
            self._record("health_status", False, f"HTTP {resp.status_code}")
            return False
        data = resp.json()
        self._record("health_status", data.get("status") == "healthy",
                      f"status={data.get('status')}")
        self._record("health_database", data.get("database") == "connected",
                      f"database={data.get('database')}")
        self._record("health_backend", bool(data.get("backend")),
                      f"backend={data.get('backend')}")
        return all(r["passed"] for r in self.results[-3:])

    # ── 2. 就绪检查 ──
    def verify_ready(self):
        print("\n== 2. 就绪检查 GET /ready ==")
        resp = self._get("/ready")
        if resp is None:
            self._record("ready_reachable", False, "无法连接")
            return False
        data = resp.json()
        # 200 或 503 都算正常响应
        self._record("ready_responded", resp.status_code in (200, 503),
                      f"HTTP {resp.status_code}, status={data.get('status')}")
        if resp.status_code == 200:
            checks = data.get("checks", {})
            self._record("ready_db", checks.get("database") == "ok",
                          f"database={checks.get('database')}")
            self._record("ready_model", checks.get("model") == "loaded",
                          f"model={checks.get('model')}")
        return data.get("status") in ("ok", "degraded")

    # ── 3. HEAD / ──
    def verify_head_root(self):
        print("\n== 3. HEAD / ==")
        try:
            resp = self.session.head(f"{self.base_url}/", timeout=10)
            self._record("head_root", resp.status_code == 200,
                          f"HTTP {resp.status_code}")
            return resp.status_code == 200
        except Exception as e:
            self._record("head_root", False, str(e))
            return False

    # ── 4. 正式预测一致性 ──
    def verify_final_result(self):
        print("\n== 4. 正式预测 GET /api/v1/agent/final-result ==")
        resp = self._get(f"/api/v1/agent/final-result")
        if resp is None:
            self._record("final_result_reachable", False, "无法连接")
            return False
        if resp.status_code != 200:
            self._record("final_result_status", False, f"HTTP {resp.status_code}")
            return False

        data = resp.json()
        errors = []

        # status
        if data.get("status") != "completed":
            errors.append(f"status={data.get('status')} != completed")

        # champion 一致性
        champion = data.get("champion", "")
        predicted = data.get("predicted_champion", "")
        top5 = data.get("top5", [])
        top_candidates = data.get("top_candidates", [])
        champ_prob = data.get("champion_probability", 0)
        explanation = data.get("explanation", {})
        run_id = data.get("run_id", "")

        if champion != predicted:
            errors.append(f"champion({champion}) != predicted_champion({predicted})")

        if top5 and champion != top5[0].get("team"):
            errors.append(f"champion({champion}) != top5[0].team({top5[0].get('team')})")

        if top_candidates and champion != top_candidates[0].get("team"):
            errors.append(f"champion({champion}) != top_candidates[0].team")

        # probability 一致性
        if top5:
            top1_prob = top5[0].get("probability", 0)
            if abs(float(champ_prob) - float(top1_prob)) > 1e-8:
                errors.append(f"champion_probability({champ_prob}) != top5[0].probability({top1_prob})")

        if top_candidates:
            tc_prob = top_candidates[0].get("probability", 0)
            if abs(float(champ_prob) - float(tc_prob)) > 1e-8:
                errors.append(f"champion_probability({champ_prob}) != top_candidates[0].probability({tc_prob})")

        # explanation 一致性
        if isinstance(explanation, dict):
            if explanation.get("champion") != champion:
                errors.append(f"explanation.champion({explanation.get('champion')}) != champion({champion})")
            if explanation.get("run_id") != run_id:
                errors.append(f"explanation.run_id({explanation.get('run_id')}) != run_id({run_id})")
            # probability 字段
            expl_prob = explanation.get("probability")
            if expl_prob is not None:
                expected_pct = round(float(champ_prob) * 100, 2)
                if abs(float(expl_prob) - expected_pct) > 0.01:
                    errors.append(f"explanation.probability({expl_prob}) != champion_probability*100({expected_pct})")

        if errors:
            self._record("final_result_consistency", False, "; ".join(errors))
            return False
        else:
            self._record("final_result_consistency", True,
                          f"champion={champion}, prob={champ_prob}, run_id={run_id}")
            return True

    # ── 5. 连续稳定读取 ──
    def verify_stability(self, n: int = 5):
        print(f"\n== 5. 连续稳定读取 ({n} 次) GET /api/v1/agent/final-result ==")
        snapshots = []
        for i in range(n):
            resp = self._get("/api/v1/agent/final-result")
            if resp and resp.status_code == 200:
                data = resp.json()
                snapshots.append({
                    "run_id": data.get("run_id"),
                    "champion": data.get("champion"),
                    "champion_probability": data.get("champion_probability"),
                })
            time.sleep(0.5)

        if len(snapshots) < n:
            self._record("stability_count", False, f"只获取到 {len(snapshots)}/{n} 次")
            return False

        # 检查 run_id 不变化
        run_ids = set(s["run_id"] for s in snapshots)
        champions = set(s["champion"] for s in snapshots)
        probs = set(s["champion_probability"] for s in snapshots)

        stable = len(run_ids) == 1 and len(champions) == 1 and len(probs) == 1
        self._record("stability_run_id", len(run_ids) == 1, f"unique run_ids: {run_ids}")
        self._record("stability_champion", len(champions) == 1, f"unique champions: {champions}")
        self._record("stability_probability", len(probs) == 1, f"unique probs: {probs}")
        return stable

    # ── 6. 沙盘 pending-matches ──
    def verify_pending_matches(self):
        print("\n== 6. 沙盘 GET /api/v1/scenario/pending-matches ==")
        resp = self._get("/api/v1/scenario/pending-matches")
        if resp is None:
            self._record("pending_matches_reachable", False, "无法连接")
            return False
        data = resp.json()
        sandbox_enabled = data.get("sandbox_enabled")
        matches = data.get("matches", [])
        self._record("pending_matches_response", data.get("success") is not False,
                      f"sandbox_enabled={sandbox_enabled}, matches={len(matches)}")
        if sandbox_enabled:
            self._record("pending_matches_count", len(matches) >= 1,
                          f"matches={len(matches)}")
        return True

    # ── 7. 沙盘 simulate ──
    def verify_scenario_simulate(self):
        print("\n== 7. 沙盘 POST /api/v1/scenario/simulate ==")
        # 先获取 pending matches
        resp = self._get("/api/v1/scenario/pending-matches")
        if not resp or resp.status_code != 200:
            self._record("simulate_skip", False, "无法获取 pending-matches")
            return False

        data = resp.json()
        if not data.get("sandbox_enabled") or not data.get("matches"):
            self._record("simulate_skip", True, "沙盘未启用或无可用比赛，跳过")
            return True

        match = data["matches"][0]
        match_id = match.get("match_id", "")
        home = match.get("home_team", "")
        away = match.get("away_team", "")
        forced_winner = home  # 假设主队晋级

        resp = self._post("/api/v1/scenario/simulate", {
            "match_id": match_id,
            "forced_winner": forced_winner,
            "simulation_count": 100,
        }, timeout=120)

        if resp is None:
            self._record("simulate_reachable", False, "无法连接")
            return False

        if resp.status_code != 200:
            self._record("simulate_status", False, f"HTTP {resp.status_code}")
            return False

        sim_data = resp.json()
        if sim_data.get("success"):
            self._record("simulate_success", True,
                          f"champion={sim_data.get('scenario_prediction', {}).get('champion')}")
            return True
        else:
            self._record("simulate_success", False,
                          sim_data.get("error") or sim_data.get("message", "unknown error"))
            return False

    # ── 汇总 ──
    def print_summary(self):
        print("\n" + "=" * 60)
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        print(f"  总计: {total}  通过: {passed}  失败: {failed}")
        print("=" * 60)

        if failed > 0:
            print("\n失败项:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  [FAIL] {r['test']}: {r['detail']}")

        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="生产环境验证脚本")
    parser.add_argument("--backend-url", required=True, help="后端 URL")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--skip-simulate", action="store_true", help="跳过沙盘模拟测试")
    args = parser.parse_args()

    print(f"生产环境验证: {args.backend_url}")
    print("=" * 60)

    v = ProductionVerifier(args.backend_url, verbose=args.verbose)

    # 按顺序执行验证
    v.verify_health()
    v.verify_ready()
    v.verify_head_root()
    v.verify_final_result()
    v.verify_stability()
    v.verify_pending_matches()
    if not args.skip_simulate:
        v.verify_scenario_simulate()

    all_passed = v.print_summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
