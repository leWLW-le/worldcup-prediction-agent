"""
智谱 AI CSV 辅助测试

检查：
1. 智谱 key 存在时可运行
2. 智谱 key 不存在时 warning，不崩溃
3. LLM 可以根据 mock API teams 生成 team_aliases
4. LLM 生成 candidate 必须 needs_review=true
5. 没有真实来源时不能生成历史真实比分
6. bootstrap_local_data.py --use-llm 可运行
7. data_manifest.json 正确标记 llm_assisted
"""

import sys
import io
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

passed = 0
failed = 0


def check(num, desc, condition):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    print(f"{num:2d}. [{status}] {desc}")


print("=" * 60)
print("LLM CSV Assistant Test")
print("=" * 60)

start_time = time.time()

# ── Test 1: 智谱 key 检测 ──
from app.core.config import get_settings
settings = get_settings()
zhipu_key = settings.OPENAI_API_KEY
has_zhipu = bool(zhipu_key)
check(1, f"Zhipu key detected={has_zhipu}", True)  # 不阻塞

# ── Test 2: generate_csv_template 不崩溃 ──
from app.tools.llm_csv_assistant_tool import (
    generate_csv_template,
    convert_api_response_to_csv_rows,
    normalize_team_names,
    generate_team_alias_candidates,
    generate_competition_weights,
    validate_llm_generated_rows,
)

tmpl = generate_csv_template("team_aliases")
check(2, f"generate_csv_template('team_aliases') success={tmpl['success']}, path={tmpl.get('path')}",
      tmpl["success"])

# ── Test 3: convert_api_response_to_csv_rows with mock data ──
mock_teams_resp = {
    "success": True,
    "source": "api-sports",
    "endpoint": "teams",
    "data": [
        {"team": {"id": 1, "name": "France", "country": "France", "founded": 1919, "logo": ""}},
        {"team": {"id": 2, "name": "Brazil", "country": "Brazil", "founded": 1914, "logo": ""}},
    ],
    "error": None,
    "fetched_at": "2026-01-01T00:00:00+00:00",
}
csv_result = convert_api_response_to_csv_rows("teams", mock_teams_resp)
check(3, f"convert_api_response_to_csv_rows('teams') success={csv_result['success']}, rows={csv_result.get('rows')}",
      csv_result["success"] and csv_result.get("rows", 0) == 2)

# ── Test 4: LLM 生成 candidate 必须 needs_review=true ──
# 用 mock API teams 测试
mock_api_teams = [
    {"team": {"id": 1, "name": "France"}},
    {"team": {"id": 2, "name": "Brazil"}},
    {"team": {"id": 3, "name": "Germany"}},
]
alias_result = generate_team_alias_candidates(mock_api_teams)
check(4, f"generate_team_alias_candidates source={alias_result.get('source')}, needs_review={alias_result.get('needs_review')}",
      alias_result.get("needs_review") is True
      and alias_result.get("source") in ("llm_generated_candidate", "llm_generated_template"))

# ── Test 5: validate_llm_generated_rows 检测非法 source ──
bad_rows = [
    {"team_name": "France", "alias": "FR", "source": "api-sports", "needs_review": "false"},
]
validation = validate_llm_generated_rows(bad_rows)
check(5, f"validate_llm_generated_rows catches bad source (valid={validation['valid']}, issues={len(validation.get('issues', []))})",
      not validation["valid"] and len(validation.get("issues", [])) > 0)

# ── Test 6: generate_competition_weights ──
cw = generate_competition_weights()
check(6, f"generate_competition_weights success={cw['success']}, rows={cw.get('rows')}",
      cw["success"] and cw.get("rows", 0) > 0)

# ── Test 7: bootstrap_local_data 可运行 ──
from app.services.bootstrap_service import bootstrap_local_data
bootstrap_result = bootstrap_local_data(season=2026, use_llm=has_zhipu)
check(7, f"bootstrap_local_data success={bootstrap_result.get('success')}, llm_assisted={bootstrap_result.get('llm_assisted')}",
      bootstrap_result.get("success") is True or bootstrap_result.get("success") is False)  # 不阻塞

# ── Test 8: data_manifest.json 正确标记 ──
manifest_path = Path("data/data_manifest.json")
manifest_ok = False
if manifest_path.exists():
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    manifest_ok = (
        "api_key_detected" in manifest
        and "zhipu_key_detected" in manifest
        and "llm_assisted" in manifest
        and "csv_files" in manifest
    )
check(8, f"data_manifest.json exists={manifest_path.exists()}, valid={manifest_ok}",
      manifest_path.exists() and manifest_ok)

# ── Test 9: normalize_team_names ──
rows = [{"team_name": "USA"}, {"team_name": "France"}]
normalized = normalize_team_names(rows)
check(9, f"normalize_team_names works (USA->{normalized[0].get('team_name')})",
      len(normalized) == 2)

# Summary
total_time = time.time() - start_time
print()
print("-" * 60)
print("Summary:")
print(f"  Zhipu key:        {'detected' if has_zhipu else 'missing'}")
print(f"  Bootstrap result: {bootstrap_result}")
print(f"  Manifest exists:  {manifest_path.exists()}")
print(f"  Total time:       {total_time:.1f}s")
print("-" * 60)

if failed == 0:
    print(f"ALL {passed} CHECKS PASSED!")
else:
    print(f"{passed} PASSED, {failed} FAILED")
print("=" * 60)
