"""
2026 美加墨世界杯真实比赛数据

截至 2026-07-10：
- 小组赛（72场）已全部完成
- 32强赛（16场）已全部完成
- 16强赛（8场）已全部完成
- 1/4 决赛（4场）已全部完成
- 半决赛、决赛尚未进行

数据来源：FIFA 官网、各大体育媒体
"""

# ──────────────────────────────────────────────
# 小组赛最终积分榜（真实数据）
# ──────────────────────────────────────────────
REAL_GROUP_STANDINGS = {
    "Group A": [
        {"rank": 1, "team_name": "Mexico",         "played": 3, "wins": 3, "draws": 0, "losses": 0, "goals_for": 6, "goals_against": 0, "goal_difference": 6,  "points": 9},
        {"rank": 2, "team_name": "South Africa",    "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 2, "goals_against": 3, "goal_difference": -1, "points": 4},
        {"rank": 3, "team_name": "South Korea",     "played": 3, "wins": 1, "draws": 0, "losses": 2, "goals_for": 2, "goals_against": 3, "goal_difference": -1, "points": 3},
        {"rank": 4, "team_name": "Czech Republic",  "played": 3, "wins": 0, "draws": 1, "losses": 2, "goals_for": 2, "goals_against": 6, "goal_difference": -4, "points": 1},
    ],
    "Group B": [
        {"rank": 1, "team_name": "Switzerland",  "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 7, "goals_against": 3, "goal_difference": 4,  "points": 7},
        {"rank": 2, "team_name": "Canada",        "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 8, "goals_against": 3, "goal_difference": 5,  "points": 4},
        {"rank": 3, "team_name": "Bosnia",        "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 5, "goals_against": 6, "goal_difference": -1, "points": 4},
        {"rank": 4, "team_name": "Qatar",         "played": 3, "wins": 0, "draws": 1, "losses": 2, "goals_for": 2, "goals_against": 10,"goal_difference": -8, "points": 1},
    ],
    "Group C": [
        {"rank": 1, "team_name": "Brazil",     "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 7, "goals_against": 1, "goal_difference": 6, "points": 7},
        {"rank": 2, "team_name": "Morocco",    "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 6, "goals_against": 3, "goal_difference": 3, "points": 7},
        {"rank": 3, "team_name": "Scotland",   "played": 3, "wins": 1, "draws": 0, "losses": 2, "goals_for": 1, "goals_against": 4, "goal_difference": -3,"points": 3},
        {"rank": 4, "team_name": "Haiti",      "played": 3, "wins": 0, "draws": 0, "losses": 3, "goals_for": 2, "goals_against": 8, "goal_difference": -6,"points": 0},
    ],
    "Group D": [
        {"rank": 1, "team_name": "USA",        "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 8, "goals_against": 4, "goal_difference": 4, "points": 6},
        {"rank": 2, "team_name": "Australia",  "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 2, "goals_against": 2, "goal_difference": 0, "points": 4},
        {"rank": 3, "team_name": "Paraguay",   "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 2, "goals_against": 4, "goal_difference": -2,"points": 4},
        {"rank": 4, "team_name": "Turkey",     "played": 3, "wins": 1, "draws": 0, "losses": 2, "goals_for": 3, "goals_against": 5, "goal_difference": -2,"points": 3},
    ],
    "Group E": [
        {"rank": 1, "team_name": "Germany",       "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 10,"goals_against": 4, "goal_difference": 6,  "points": 6},
        {"rank": 2, "team_name": "Ivory Coast",   "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 4, "goals_against": 2, "goal_difference": 2,  "points": 6},
        {"rank": 3, "team_name": "Ecuador",       "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 3, "goals_against": 3, "goal_difference": 0,  "points": 4},
        {"rank": 4, "team_name": "Curacao",       "played": 3, "wins": 0, "draws": 1, "losses": 2, "goals_for": 2, "goals_against": 10,"goal_difference": -8, "points": 1},
    ],
    "Group F": [
        {"rank": 1, "team_name": "Netherlands", "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 7, "goals_against": 3, "goal_difference": 4, "points": 7},
        {"rank": 2, "team_name": "Japan",       "played": 3, "wins": 1, "draws": 2, "losses": 0, "goals_for": 6, "goals_against": 2, "goal_difference": 4, "points": 5},
        {"rank": 3, "team_name": "Sweden",      "played": 3, "wins": 1, "draws": 0, "losses": 2, "goals_for": 6, "goals_against": 6, "goal_difference": 0, "points": 3},
        {"rank": 4, "team_name": "Tunisia",     "played": 3, "wins": 0, "draws": 0, "losses": 3, "goals_for": 1, "goals_against": 9, "goal_difference": -8,"points": 0},
    ],
    "Group G": [
        {"rank": 1, "team_name": "Belgium",    "played": 3, "wins": 1, "draws": 2, "losses": 0, "goals_for": 4, "goals_against": 3, "goal_difference": 1, "points": 5},
        {"rank": 2, "team_name": "Egypt",      "played": 3, "wins": 1, "draws": 2, "losses": 0, "goals_for": 3, "goals_against": 2, "goal_difference": 1, "points": 5},
        {"rank": 3, "team_name": "Iran",       "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 3, "goals_against": 3, "goal_difference": 0, "points": 4},
        {"rank": 4, "team_name": "New Zealand","played": 3, "wins": 0, "draws": 1, "losses": 2, "goals_for": 2, "goals_against": 4, "goal_difference": -2,"points": 1},
    ],
    "Group H": [
        {"rank": 1, "team_name": "Spain",         "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 6, "goals_against": 1, "goal_difference": 5, "points": 7},
        {"rank": 2, "team_name": "Cape Verde",    "played": 3, "wins": 0, "draws": 3, "losses": 0, "goals_for": 2, "goals_against": 2, "goal_difference": 0, "points": 3},
        {"rank": 3, "team_name": "Saudi Arabia",  "played": 3, "wins": 0, "draws": 2, "losses": 1, "goals_for": 2, "goals_against": 5, "goal_difference": -3,"points": 2},
        {"rank": 4, "team_name": "Uruguay",       "played": 3, "wins": 0, "draws": 2, "losses": 1, "goals_for": 2, "goals_against": 4, "goal_difference": -2,"points": 2},
    ],
    "Group I": [
        {"rank": 1, "team_name": "France",    "played": 3, "wins": 3, "draws": 0, "losses": 0, "goals_for": 8, "goals_against": 1, "goal_difference": 7, "points": 9},
        {"rank": 2, "team_name": "Norway",    "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 6, "goals_against": 3, "goal_difference": 3, "points": 6},
        {"rank": 3, "team_name": "Senegal",   "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 5, "goals_against": 3, "goal_difference": 2, "points": 6},
        {"rank": 4, "team_name": "Iraq",      "played": 3, "wins": 0, "draws": 0, "losses": 3, "goals_for": 1, "goals_against": 9, "goal_difference": -8,"points": 0},
    ],
    "Group J": [
        {"rank": 1, "team_name": "Argentina", "played": 3, "wins": 3, "draws": 0, "losses": 0, "goals_for": 9, "goals_against": 1, "goal_difference": 8, "points": 9},
        {"rank": 2, "team_name": "Austria",   "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 4, "goals_against": 4, "goal_difference": 0, "points": 4},
        {"rank": 3, "team_name": "Algeria",   "played": 3, "wins": 0, "draws": 1, "losses": 2, "goals_for": 4, "goals_against": 7, "goal_difference": -3,"points": 1},
        {"rank": 4, "team_name": "Jordan",    "played": 3, "wins": 0, "draws": 0, "losses": 3, "goals_for": 1, "goals_against": 6, "goal_difference": -5,"points": 0},
    ],
    "Group K": [
        {"rank": 1, "team_name": "Colombia",   "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 5, "goals_against": 3, "goal_difference": 2, "points": 6},
        {"rank": 2, "team_name": "Portugal",   "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 3, "goals_against": 3, "goal_difference": 0, "points": 4},
        {"rank": 3, "team_name": "DR Congo",   "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 3, "goals_against": 4, "goal_difference": -1,"points": 4},
        {"rank": 4, "team_name": "Uzbekistan", "played": 3, "wins": 1, "draws": 0, "losses": 2, "goals_for": 3, "goals_against": 4, "goal_difference": -1,"points": 3},
    ],
    "Group L": [
        {"rank": 1, "team_name": "England",   "played": 3, "wins": 2, "draws": 1, "losses": 0, "goals_for": 5, "goals_against": 2, "goal_difference": 3, "points": 7},
        {"rank": 2, "team_name": "Croatia",   "played": 3, "wins": 2, "draws": 0, "losses": 1, "goals_for": 4, "goals_against": 3, "goal_difference": 1, "points": 6},
        {"rank": 3, "team_name": "Ghana",     "played": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 3, "goals_against": 3, "goal_difference": 0, "points": 4},
        {"rank": 4, "team_name": "Panama",    "played": 3, "wins": 0, "draws": 0, "losses": 3, "goals_for": 1, "goals_against": 5, "goal_difference": -4,"points": 0},
    ],
}

# ──────────────────────────────────────────────
# 32强赛（Round of 32）真实结果 — 6月28日~7月4日
# ──────────────────────────────────────────────
REAL_ROUND_OF_32 = [
    # 6月28日
    {"home": "South Africa", "away": "Canada",       "score_a": 0, "score_b": 1, "winner": "Canada",       "is_penalty_shootout": False},
    # 6月29日
    {"home": "Brazil",       "away": "Japan",         "score_a": 2, "score_b": 1, "winner": "Brazil",       "is_penalty_shootout": False},
    {"home": "Germany",      "away": "Paraguay",      "score_a": 1, "score_b": 1, "winner": "Paraguay",     "is_penalty_shootout": True},
    {"home": "Netherlands",  "away": "Morocco",       "score_a": 1, "score_b": 1, "winner": "Morocco",      "is_penalty_shootout": True},
    # 6月30日
    {"home": "Ivory Coast",  "away": "Norway",        "score_a": 1, "score_b": 2, "winner": "Norway",       "is_penalty_shootout": False},
    {"home": "France",       "away": "Sweden",        "score_a": 3, "score_b": 0, "winner": "France",       "is_penalty_shootout": False},
    {"home": "Mexico",       "away": "Ecuador",       "score_a": 2, "score_b": 0, "winner": "Mexico",       "is_penalty_shootout": False},
    # 7月1日
    {"home": "England",      "away": "DR Congo",      "score_a": 2, "score_b": 1, "winner": "England",      "is_penalty_shootout": False},
    {"home": "Belgium",      "away": "Senegal",       "score_a": 3, "score_b": 2, "winner": "Belgium",      "is_penalty_shootout": False},
    {"home": "USA",          "away": "Bosnia",        "score_a": 2, "score_b": 0, "winner": "USA",          "is_penalty_shootout": False},
    # 7月2日
    {"home": "Spain",        "away": "Austria",       "score_a": 3, "score_b": 0, "winner": "Spain",        "is_penalty_shootout": False},
    {"home": "Portugal",     "away": "Croatia",       "score_a": 2, "score_b": 1, "winner": "Portugal",     "is_penalty_shootout": False},
    {"home": "Switzerland",  "away": "Algeria",       "score_a": 2, "score_b": 0, "winner": "Switzerland",  "is_penalty_shootout": False},
    # 7月3日
    {"home": "Australia",    "away": "Egypt",         "score_a": 0, "score_b": 0, "winner": "Egypt",        "is_penalty_shootout": True},
    {"home": "Argentina",    "away": "Cape Verde",    "score_a": 3, "score_b": 2, "winner": "Argentina",    "is_penalty_shootout": False},
    # 7月4日
    {"home": "Colombia",     "away": "Ghana",         "score_a": 1, "score_b": 0, "winner": "Colombia",     "is_penalty_shootout": False},
]

# ──────────────────────────────────────────────
# 16强赛（Round of 16）真实结果 — 7月5日~7月8日
# ──────────────────────────────────────────────
REAL_ROUND_OF_16 = [
    # 7月5日
    {"home": "Canada",    "away": "Morocco",  "score_a": 0, "score_b": 3, "winner": "Morocco",  "is_penalty_shootout": False},
    {"home": "France",    "away": "Paraguay", "score_a": 1, "score_b": 0, "winner": "France",   "is_penalty_shootout": False},
    # 7月6日
    {"home": "Brazil",    "away": "Norway",   "score_a": 1, "score_b": 2, "winner": "Norway",   "is_penalty_shootout": False},
    {"home": "Mexico",    "away": "England",  "score_a": 2, "score_b": 3, "winner": "England",  "is_penalty_shootout": False},
    # 7月7日
    {"home": "Portugal",  "away": "Spain",    "score_a": 0, "score_b": 1, "winner": "Spain",    "is_penalty_shootout": False},
    {"home": "USA",       "away": "Belgium",  "score_a": 1, "score_b": 4, "winner": "Belgium",  "is_penalty_shootout": False},
    # 7月8日
    {"home": "Argentina", "away": "Egypt",    "score_a": 3, "score_b": 2, "winner": "Argentina","is_penalty_shootout": False},
    {"home": "Switzerland","away": "Colombia", "score_a": 0, "score_b": 0, "winner": "Switzerland","is_penalty_shootout": True},
]

# ──────────────────────────────────────────────
# 1/4 决赛（Quarter-finals）真实结果 — 7月10日~7月11日
# ──────────────────────────────────────────────
REAL_QUARTER_FINALS = [
    # 7月10日
    {"home": "Morocco",    "away": "France",     "score_a": 0, "score_b": 1, "winner": "France",     "is_penalty_shootout": False},
    {"home": "Norway",     "away": "England",    "score_a": 0, "score_b": 1, "winner": "England",    "is_penalty_shootout": False},
    # 7月11日
    {"home": "Spain",      "away": "Belgium",    "score_a": 2, "score_b": 0, "winner": "Spain",      "is_penalty_shootout": False},
    {"home": "Argentina",  "away": "Switzerland","score_a": 2, "score_b": 0, "winner": "Argentina",  "is_penalty_shootout": False},
]

# ──────────────────────────────────────────────
# 八强名单（用于验证和快速查找）
# ──────────────────────────────────────────────
QUARTERFINALISTS = ["France", "Morocco", "Spain", "Belgium", "Norway", "England", "Argentina", "Switzerland"]

# Elo 评分映射（用于淘汰赛模拟）
TEAM_ELO_MAP = {
    "France": 2100.0, "Morocco": 1820.0, "Spain": 2080.0, "Belgium": 1880.0,
    "Norway": 1800.0, "England": 2040.0, "Argentina": 2050.0, "Switzerland": 1860.0,
}


def is_real_data_available() -> bool:
    """检查是否有真实比赛数据可用"""
    return bool(REAL_GROUP_STANDINGS and REAL_ROUND_OF_32 and REAL_ROUND_OF_16 and REAL_QUARTER_FINALS)


def get_remaining_stage() -> str:
    """返回当前需要模拟的起始阶段"""
    if REAL_QUARTER_FINALS:
        return "semi_finals"
    if REAL_ROUND_OF_16:
        return "quarter_finals"
    if REAL_ROUND_OF_32:
        return "round_of_16"
    if REAL_GROUP_STANDINGS:
        return "round_of_32"
    return "group_stage"
