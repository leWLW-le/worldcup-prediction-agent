"""测试从 DB 读取淘汰赛数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.fixture_repository import FixtureRepository
from app.tools.bracket_tool import BracketTool
from app.tools.match_predictor_tool import MatchPredictorTool

repo = FixtureRepository()
ko = repo.get_knockout_fixtures()
print(f"DB knockout fixtures: {len(ko)}")

bt = BracketTool(seed=42)
predictor = MatchPredictorTool(seed=42)
result = bt._build_from_db_knockout_data(ko, {}, predictor)
kp = result['knockout_predictions']

rounds = {}
for m in kp:
    rounds[m['round']] = rounds.get(m['round'], 0) + 1
print(f"Rounds: {rounds}")

for round_name in ['round_of_32', 'round_of_16', 'quarter_finals', 'semi_finals', 'final']:
    matches = [m for m in kp if m['round'] == round_name]
    if matches:
        print(f"\n--- {round_name} ---")
        for m in matches:
            print(f"  {m['home_team']} {m['predicted_score']} {m['away_team']} | "
                  f"source={m['source']} | winner={m['winner']}")

print(f"\nChampion: {result['champion']}")
print(f"Runner-up: {result['runner_up']}")
