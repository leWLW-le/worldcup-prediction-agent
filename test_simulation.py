#!/usr/bin/env python3
"""Test the simulation API with LLM explanation enabled."""

import requests
import json
from datetime import datetime

# API endpoint
url = "http://localhost:8000/api/v1/simulation/predict"

# Build test groups data (same as Streamlit dashboard)
def build_test_groups():
    """构建测试用的小组数据"""
    teams_data = [
        # Group A
        [
            {"team_id": 1, "team_name": "Brazil", "elo_rating": 2100.0, "player_value": 600.0, "recent_form": 0.8, "injury_rate": 0.1},
            {"team_id": 2, "team_name": "Germany", "elo_rating": 1950.0, "player_value": 500.0, "recent_form": 0.7, "injury_rate": 0.15},
            {"team_id": 3, "team_name": "Japan", "elo_rating": 1750.0, "player_value": 350.0, "recent_form": 0.6, "injury_rate": 0.2},
            {"team_id": 4, "team_name": "Egypt", "elo_rating": 1650.0, "player_value": 300.0, "recent_form": 0.5, "injury_rate": 0.25}
        ],
        # Group B
        [
            {"team_id": 5, "team_name": "France", "elo_rating": 2050.0, "player_value": 580.0, "recent_form": 0.75, "injury_rate": 0.12},
            {"team_id": 6, "team_name": "Argentina", "elo_rating": 2000.0, "player_value": 550.0, "recent_form": 0.85, "injury_rate": 0.08},
            {"team_id": 7, "team_name": "Australia", "elo_rating": 1700.0, "player_value": 320.0, "recent_form": 0.55, "injury_rate": 0.18},
            {"team_id": 8, "team_name": "Saudi Arabia", "elo_rating": 1600.0, "player_value": 280.0, "recent_form": 0.45, "injury_rate": 0.22}
        ],
        # Group C
        [
            {"team_id": 9, "team_name": "Spain", "elo_rating": 1980.0, "player_value": 520.0, "recent_form": 0.72, "injury_rate": 0.1},
            {"team_id": 10, "team_name": "Portugal", "elo_rating": 1920.0, "player_value": 480.0, "recent_form": 0.68, "injury_rate": 0.14},
            {"team_id": 11, "team_name": "South Korea", "elo_rating": 1720.0, "player_value": 340.0, "recent_form": 0.58, "injury_rate": 0.19},
            {"team_id": 12, "team_name": "Morocco", "elo_rating": 1680.0, "player_value": 310.0, "recent_form": 0.62, "injury_rate": 0.17}
        ],
        # Group D
        [
            {"team_id": 13, "team_name": "England", "elo_rating": 1960.0, "player_value": 510.0, "recent_form": 0.7, "injury_rate": 0.13},
            {"team_id": 14, "team_name": "Italy", "elo_rating": 1900.0, "player_value": 470.0, "recent_form": 0.65, "injury_rate": 0.16},
            {"team_id": 15, "team_name": "Mexico", "elo_rating": 1740.0, "player_value": 360.0, "recent_form": 0.6, "injury_rate": 0.2},
            {"team_id": 16, "team_name": "Iran", "elo_rating": 1620.0, "player_value": 290.0, "recent_form": 0.48, "injury_rate": 0.23}
        ],
        # Group E
        [
            {"team_id": 17, "team_name": "Netherlands", "elo_rating": 1940.0, "player_value": 490.0, "recent_form": 0.69, "injury_rate": 0.11},
            {"team_id": 18, "team_name": "Belgium", "elo_rating": 1880.0, "player_value": 460.0, "recent_form": 0.64, "injury_rate": 0.15},
            {"team_id": 19, "team_name": "USA", "elo_rating": 1760.0, "player_value": 370.0, "recent_form": 0.63, "injury_rate": 0.18},
            {"team_id": 20, "team_name": "Senegal", "elo_rating": 1660.0, "player_value": 305.0, "recent_form": 0.52, "injury_rate": 0.21}
        ],
        # Group F
        [
            {"team_id": 21, "team_name": "Croatia", "elo_rating": 1860.0, "player_value": 440.0, "recent_form": 0.66, "injury_rate": 0.14},
            {"team_id": 22, "team_name": "Denmark", "elo_rating": 1840.0, "player_value": 430.0, "recent_form": 0.61, "injury_rate": 0.16},
            {"team_id": 23, "team_name": "Canada", "elo_rating": 1710.0, "player_value": 330.0, "recent_form": 0.56, "injury_rate": 0.19},
            {"team_id": 24, "team_name": "Ghana", "elo_rating": 1640.0, "player_value": 295.0, "recent_form": 0.49, "injury_rate": 0.24}
        ],
        # Group G
        [
            {"team_id": 25, "team_name": "Uruguay", "elo_rating": 1820.0, "player_value": 420.0, "recent_form": 0.62, "injury_rate": 0.15},
            {"team_id": 26, "team_name": "Switzerland", "elo_rating": 1800.0, "player_value": 410.0, "recent_form": 0.59, "injury_rate": 0.17},
            {"team_id": 27, "team_name": "Poland", "elo_rating": 1730.0, "player_value": 350.0, "recent_form": 0.57, "injury_rate": 0.2},
            {"team_id": 28, "team_name": "Cameroon", "elo_rating": 1630.0, "player_value": 285.0, "recent_form": 0.47, "injury_rate": 0.25}
        ],
        # Group H
        [
            {"team_id": 29, "team_name": "Colombia", "elo_rating": 1780.0, "player_value": 400.0, "recent_form": 0.6, "injury_rate": 0.16},
            {"team_id": 30, "team_name": "Sweden", "elo_rating": 1770.0, "player_value": 390.0, "recent_form": 0.58, "injury_rate": 0.18},
            {"team_id": 31, "team_name": "Serbia", "elo_rating": 1740.0, "player_value": 355.0, "recent_form": 0.54, "injury_rate": 0.21},
            {"team_id": 32, "team_name": "Tunisia", "elo_rating": 1610.0, "player_value": 275.0, "recent_form": 0.46, "injury_rate": 0.26}
        ],
        # Group I
        [
            {"team_id": 33, "team_name": "Chile", "elo_rating": 1760.0, "player_value": 380.0, "recent_form": 0.57, "injury_rate": 0.19},
            {"team_id": 34, "team_name": "Austria", "elo_rating": 1750.0, "player_value": 365.0, "recent_form": 0.56, "injury_rate": 0.2},
            {"team_id": 35, "team_name": "Turkey", "elo_rating": 1700.0, "player_value": 325.0, "recent_form": 0.53, "injury_rate": 0.22},
            {"team_id": 36, "team_name": "Algeria", "elo_rating": 1600.0, "player_value": 270.0, "recent_form": 0.44, "injury_rate": 0.27}
        ],
        # Group J
        [
            {"team_id": 37, "team_name": "Ecuador", "elo_rating": 1740.0, "player_value": 355.0, "recent_form": 0.55, "injury_rate": 0.2},
            {"team_id": 38, "team_name": "Norway", "elo_rating": 1730.0, "player_value": 345.0, "recent_form": 0.54, "injury_rate": 0.21},
            {"team_id": 39, "team_name": "Ukraine", "elo_rating": 1710.0, "player_value": 335.0, "recent_form": 0.52, "injury_rate": 0.23},
            {"team_id": 40, "team_name": "Nigeria", "elo_rating": 1590.0, "player_value": 265.0, "recent_form": 0.43, "injury_rate": 0.28}
        ],
        # Group K
        [
            {"team_id": 41, "team_name": "Peru", "elo_rating": 1720.0, "player_value": 340.0, "recent_form": 0.53, "injury_rate": 0.21},
            {"team_id": 42, "team_name": "Czech Republic", "elo_rating": 1710.0, "player_value": 330.0, "recent_form": 0.51, "injury_rate": 0.22},
            {"team_id": 43, "team_name": "Scotland", "elo_rating": 1690.0, "player_value": 315.0, "recent_form": 0.5, "injury_rate": 0.24},
            {"team_id": 44, "team_name": "Ivory Coast", "elo_rating": 1580.0, "player_value": 260.0, "recent_form": 0.42, "injury_rate": 0.29}
        ],
        # Group L
        [
            {"team_id": 45, "team_name": "Venezuela", "elo_rating": 1700.0, "player_value": 325.0, "recent_form": 0.52, "injury_rate": 0.22},
            {"team_id": 46, "team_name": "Wales", "elo_rating": 1690.0, "player_value": 320.0, "recent_form": 0.5, "injury_rate": 0.23},
            {"team_id": 47, "team_name": "Russia", "elo_rating": 1680.0, "player_value": 310.0, "recent_form": 0.49, "injury_rate": 0.25},
            {"team_id": 48, "team_name": "Costa Rica", "elo_rating": 1570.0, "player_value": 255.0, "recent_form": 0.41, "injury_rate": 0.3}
        ]
    ]
    
    # Convert to format expected by API
    groups = []
    for i, group_teams in enumerate(teams_data):
        groups.append({
            "group_name": f"Group {chr(ord('A') + i)}",
            "teams": group_teams
        })
    
    return groups


# Request payload
payload = {
    "groups": build_test_groups(),
    "seed": 42,
    "enable_attention_adjustment": True,
    "generate_final_explanation": True
}

print(" Sending simulation request...")
print(f"URL: {url}")
print(f"Payload: {json.dumps(payload, indent=2)[:500]}...")
print("\nWaiting for response (this may take 30-60 seconds)...\n")

try:
    # Send POST request with timeout
    response = requests.post(url, json=payload, timeout=120)
    
    print(f"Response received!")
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\nSimulation Results:")
        print(f"  - Champion: {result.get('tournament_winner_name')}")
        print(f"  - Runner-up: {result.get('runner_up_name')}")
        print(f"  - Final Score: {result.get('final_score')}")
        print(f"  - Total Matches: {result.get('total_matches')}")
        
        # Check for LLM explanation
        final_explanation = result.get('final_explanation')
        if final_explanation:
            print(f"\nLLM Explanation Generated Successfully!")
            print(f"  - Confidence Score: {final_explanation.get('confidence_score', 'N/A')}")
            print(f"  - Prediction Summary: {final_explanation.get('prediction_summary', 'N/A')[:100]}...")
        else:
            print(f"\nNo LLM explanation found")
        
        print(f"\nFull Response Body:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\nError Response (status {response.status_code}):")
        print(response.text)
    
except requests.exceptions.Timeout:
    print("Request timed out after 120 seconds")
    print("The server might be processing the request or stuck.")
    
except requests.exceptions.ConnectionError as e:
    print(f"Connection error: {e}")
    print("Make sure FastAPI is running on http://localhost:8000")
    
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
