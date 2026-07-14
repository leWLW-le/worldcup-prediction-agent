"""
2026 世界杯冠军预测 · 产品展示页
深蓝 + 金色 · 卡片布局 · 全中文 · 适合答辩展示

数据源：data/final_agent_result.json（通过 API /agent/final-result 提供）
"""

import sys
import os
from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

# ==================== 常量 ====================
PROJECT_ROOT = Path(__file__).resolve().parent
FINAL_RESULT_PATH = PROJECT_ROOT / "data" / "final_agent_result.json"


def format_probability(p) -> str:
    """统一概率格式化：0-1 小数 → 百分比显示"""
    if p is None:
        return "待计算"
    p = float(p)
    if p > 1:
        # 兼容旧百分数（如 85.8），但不推荐
        return f"{p:.1f}%"
    return f"{p * 100:.1f}%"

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="2026 世界杯冠军预测",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================== 世界杯风格 CSS ====================
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background: linear-gradient(160deg, #0a1628 0%, #0f2340 40%, #132d54 100%) !important;
    color: #e0e6ed !important;
    font-family: 'Segoe UI', 'Microsoft YaHei', system-ui, sans-serif;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
footer { display: none !important; }
.block-container { padding: 0.8rem 2rem 1.5rem !important; max-width: 1500px !important; }
[data-testid="stVerticalBlock"] > [style*="gap"] { gap: 0.15rem !important; }

.hero-title { color:#ffd700; font-size:2.2rem; font-weight:800; letter-spacing:2px;
    text-shadow:0 2px 20px rgba(255,215,0,.25); margin:0; }
.hero-sub { color:#8a9bb5; font-size:.88rem; margin-top:.2rem; letter-spacing:.5px; }

.card { background:linear-gradient(135deg,rgba(15,35,64,.88),rgba(19,45,84,.78));
    border:1px solid rgba(255,215,0,.10); border-radius:14px; padding:1rem 1.4rem;
    box-shadow:0 4px 28px rgba(0,0,0,.38); backdrop-filter:blur(6px); margin-bottom:.3rem; }
.card-gold { background:linear-gradient(135deg,rgba(255,215,0,.10),rgba(255,170,0,.04));
    border:1px solid rgba(255,215,0,.28); border-radius:16px; padding:1.3rem 1.8rem;
    box-shadow:0 6px 36px rgba(255,215,0,.08); margin-bottom:.3rem; }

.lbl { color:#7a92ad; font-size:.72rem; letter-spacing:1.6px; margin-bottom:.1rem; }
.val-gold { color:#ffd700; font-size:1.8rem; font-weight:700; line-height:1.2; }
.val-white { color:#fff; font-size:1rem; }
.val-sm { color:#e0e6ed; font-size:1.1rem; font-weight:600; }

.bar-bg { background:rgba(255,255,255,.07); border-radius:6px; height:22px; position:relative; overflow:hidden; }
.bar-fill { background:linear-gradient(90deg,#ffd700,#ffaa00); height:100%; border-radius:6px; }
.bar-text { position:absolute; top:0; left:10px; line-height:22px; font-size:.78rem; font-weight:700; color:#0a1628; }

.warn-bar { background:linear-gradient(90deg,rgba(255,180,50,.14),rgba(255,180,50,.04));
    border:1px solid rgba(255,180,50,.32); border-radius:10px; padding:.55rem 1rem;
    color:#ffb432; font-weight:600; font-size:.85rem; margin-bottom:.4rem; }

div.stButton > button { background:linear-gradient(135deg,#ffd700,#e6a800) !important;
    color:#0a1628 !important; border:none !important; border-radius:10px !important;
    font-weight:700 !important; font-size:.9rem !important; padding:.45rem 1.6rem !important;
    box-shadow:0 4px 18px rgba(255,215,0,.22) !important; transition:transform .12s,box-shadow .12s !important;
    max-width:260px !important; min-height:44px !important; }
div.stButton > button:hover { transform:scale(1.03);
    box-shadow:0 6px 24px rgba(255,215,0,.32) !important; }

/* ── 冠军之路淘汰赛路径图 ── */
.road-container { display:flex; gap:0; overflow-x:auto; padding:.4rem 0; align-items:stretch; }
.road-round { flex:1; min-width:150px; display:flex; flex-direction:column; position:relative; }
.road-round-title { color:#ffd700; font-size:.7rem; font-weight:700; letter-spacing:1px;
    text-align:center; margin-bottom:.25rem; padding:.2rem 0;
    background:rgba(255,215,0,.06); border-radius:6px 6px 0 0; }
.road-matches { flex:1; display:flex; flex-direction:column; justify-content:space-around; gap:.2rem;
    padding:.15rem .2rem; position:relative; }
.road-matches::before { content:''; position:absolute; left:0; top:10%; bottom:10%; width:2px;
    background:rgba(255,255,255,.08); }
.road-match { background:rgba(255,255,255,.95); border-radius:6px; padding:.25rem .4rem;
    box-shadow:0 1px 4px rgba(0,0,0,.12); position:relative; z-index:1;
    border:1px solid rgba(200,200,200,.25); }
.road-match-green { border-left:3px solid #28a745; }
.road-match-yellow { border-left:3px solid #ffc107; }
.road-match-teams { display:flex; justify-content:space-between; align-items:center; gap:.2rem; }
.road-team { font-size:.7rem; font-weight:600; color:#1a2a3a; flex:1; text-align:center;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.road-team-winner { color:#b8860b; font-weight:800; }
.road-vs { color:#999; font-size:.55rem; margin:0 .1rem; flex-shrink:0; }
.road-score { text-align:center; font-size:.72rem; font-weight:800; margin:1px 0; }
.road-score-real { color:#28a745; }
.road-score-predict { color:#d71920; }
.road-stage-tag { display:inline-block; font-size:.5rem; padding:0 4px; border-radius:4px;
    font-weight:600; margin-top:.1rem; }
.road-tag-done { background:#d4edda; color:#155724; }
.road-tag-predict { background:#fff3cd; color:#856404; }
.road-champion-box { text-align:center; padding:.6rem .4rem;
    background:linear-gradient(135deg,rgba(255,215,0,.12),rgba(255,170,0,.06));
    border:1px solid rgba(255,215,0,.30); border-radius:10px; margin-top:.3rem; }

/* ── AI 分析过程折叠区 ── */
.steps-container { background:linear-gradient(135deg,rgba(15,35,64,.88),rgba(19,45,84,.78));
    border:1px solid rgba(255,215,0,.10); border-radius:14px; padding:1rem 1.4rem;
    box-shadow:0 4px 28px rgba(0,0,0,.38); margin-bottom:.3rem; }
.step-item { display:flex; align-items:flex-start; gap:.6rem; margin-bottom:.5rem; }
.step-num { width:28px; height:28px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; font-weight:800; font-size:.8rem; flex-shrink:0;
    background:linear-gradient(135deg,#ffd700,#e6a800); color:#0a1628; }
.step-done { background:linear-gradient(135deg,#28a745,#20c997); color:#fff; }

/* ── 统一模块卡片 ── */
.section-card {
    background: rgba(15, 38, 70, 0.82);
    border: 1px solid rgba(120, 160, 220, 0.22);
    border-radius: 18px;
    padding: 1.4rem 1.6rem;
    margin: 1.2rem 0;
    box-shadow: 0 16px 36px rgba(0,0,0,0.18);
}
.section-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #e8f2ff;
    margin-bottom: 1rem;
    letter-spacing: .02em;
}

/* ── 正式冠军预测 ── */
.official-card {
    background: linear-gradient(135deg, rgba(255, 215, 0, .14), rgba(20, 45, 80, .92));
    border: 1px solid rgba(255, 215, 0, .45);
    border-radius: 20px;
    padding: 2rem;
    text-align: center;
    box-shadow: 0 0 28px rgba(255, 215, 0, .14);
}
.official-label {
    color: #8fa6c8;
    font-size: .86rem;
    margin-bottom: .4rem;
}
.champion-name {
    font-size: 3rem;
    font-weight: 900;
    color: #ffd700;
    text-shadow: 0 0 20px rgba(255,215,0,.35);
}
.champion-prob {
    font-size: 2rem;
    font-weight: 900;
    color: #ffd700;
}

/* ── AI 冠军解读 ── */
.ai-card {
    background: rgba(20, 52, 92, .78);
    border: 1px solid rgba(88, 190, 255, .32);
    border-left: 5px solid #36d1ff;
    border-radius: 16px;
    padding: 1.3rem 1.5rem;
    margin: 1rem 0;
}
.ai-card h2,
.ai-card h3 {
    color: #eaf6ff;
    margin-top: 0;
}
.ai-card p {
    color: #d6e8ff;
    line-height: 1.85;
    font-size: 1.02rem;
}

/* ── 冠军路径沙盘 ── */
.sandbox-card {
    background: linear-gradient(135deg, rgba(87, 104, 255, .16), rgba(18, 42, 78, .92));
    border: 1px solid rgba(120, 140, 255, .42);
    border-radius: 18px;
    padding: 1.4rem 1.6rem;
    margin: 1.2rem 0;
}
.sandbox-badge {
    display: inline-block;
    padding: .28rem .65rem;
    border-radius: 999px;
    background: rgba(125, 145, 255, .22);
    color: #aebcff;
    font-weight: 800;
    font-size: .78rem;
    border: 1px solid rgba(150, 165, 255, .35);
}
.warning-note {
    background: rgba(255, 193, 7, .12);
    border: 1px solid rgba(255, 193, 7, .35);
    color: #ffe8a3;
    border-radius: 12px;
    padding: .8rem 1rem;
    margin-top: 1rem;
    font-size: .92rem;
}

/* ── 概率条 ── */
.prob-row {
    display: grid;
    grid-template-columns: 110px 1fr 70px;
    gap: .8rem;
    align-items: center;
    margin: .65rem 0;
}
.prob-track {
    height: 22px;
    border-radius: 999px;
    background: rgba(255,255,255,.08);
    overflow: hidden;
}
.prob-fill-gold {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #ffe600, #ffae00);
}
.prob-fill-blue {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #6b8cff, #4f6cff);
}

/* ── 变化标记 ── */
.delta-up {
    color: #2ee879;
    font-weight: 900;
}
.delta-down {
    color: #ff6b6b;
    font-weight: 900;
}
.delta-out {
    color: #ff6b6b;
    font-weight: 900;
    background: rgba(255, 80, 80, .12);
    border: 1px solid rgba(255, 80, 80, .28);
    padding: .18rem .5rem;
    border-radius: 8px;
}

/* ── 对比表行 ── */
.scenario-compare-row { display:flex; align-items:center; gap:.5rem; padding:.45rem .6rem;
    border-bottom:1px solid rgba(255,255,255,.04); border-radius:8px; }
.scenario-compare-row:hover { background:rgba(255,255,255,.03); }
.scenario-compare-row:last-child { border-bottom:none; }

/* ── 操作按钮区 ── */
.action-bar {
    background: rgba(15, 38, 70, 0.65);
    border: 1px solid rgba(120, 160, 220, 0.15);
    border-radius: 14px;
    padding: 1rem 1.4rem;
    margin: 0.8rem 0;
}

/* ── 模块说明文字 ── */
.section-subtitle {
    color: #9fb4d6;
    font-size: .96rem;
    line-height: 1.7;
    margin: .25rem 0 1rem 0;
}

/* ── 页面整体间距 ── */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
}
.section-card,
.sandbox-wrapper {
    margin-top: 1.4rem;
    margin-bottom: 1.6rem;
}

/* ── 沙盘模块外层 ── */
.sandbox-wrapper {
    background: linear-gradient(135deg, rgba(87,104,255,.16), rgba(18,42,78,.94));
    border: 1px solid rgba(120,140,255,.42);
    border-radius: 20px;
    padding: 1.6rem;
    margin: 1.4rem 0;
    box-shadow: 0 16px 36px rgba(0,0,0,.2);
}

/* ── 沙盘模块统一卡片（标题+内容+警告 整体包裹） ── */
.sandbox-results-card {
    background: linear-gradient(135deg, rgba(87,104,255,.16), rgba(18,42,78,.94));
    border: 1px solid rgba(120,140,255,.42);
    border-radius: 20px;
    padding: 1.4rem 1.6rem;
    margin: 1.2rem 0 1.4rem 0;
    box-shadow: 0 16px 36px rgba(0,0,0,.2);
}
.sandbox-results-card .section-title {
    margin-top: 0;
}

/* ── 模块内子卡片（无独立边框，融入外层） ── */
.module-subcard {
    background: rgba(7, 24, 50, .38);
    border: 1px solid rgba(130, 165, 220, .20);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin: 1rem 0;
}
.form-panel {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: 0;
}
.result-panel {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: .6rem 0 0 0;
}
.bracket-wrapper {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: 0;
    overflow-x: auto;
}

/* ── 对比表 ── */
.compare-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: .8rem;
}
.compare-table th {
    color: #9fb4d6;
    font-size: .9rem;
    text-align: left;
    padding: .65rem .5rem;
    border-bottom: 1px solid rgba(160, 190, 230, .22);
}
.compare-table td {
    color: #e8f2ff;
    padding: .75rem .5rem;
    border-bottom: 1px solid rgba(160, 190, 230, .10);
    font-weight: 700;
}

/* ── 淘汰赛模块 ── */
.bracket-section {
    margin: 1.4rem 0;
}

/* ── 装饰动画 ── */
@keyframes bounce-ball {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-6px); }
}
@keyframes float-mascot {
    0%, 100% { transform: translateY(0) rotate(0deg); }
    25% { transform: translateY(-4px) rotate(3deg); }
    75% { transform: translateY(2px) rotate(-2deg); }
}
@keyframes pulse-glow {
    0%, 100% { opacity: .7; }
    50% { opacity: 1; }
}
.decor-bounce {
    display: inline-block;
    animation: bounce-ball 2s ease-in-out infinite;
}
.decor-float {
    display: inline-block;
    animation: float-mascot 3s ease-in-out infinite;
}
.decor-pulse {
    animation: pulse-glow 2.5s ease-in-out infinite;
}
.section-title:hover .decor-bounce {
    animation-duration: .6s;
}

/* ─ AI 解读文字层次 ── */
.expl-section-title {
    color: #ffd866 !important;
    font-size: 1.08rem !important;
    font-weight: 800 !important;
    margin: 1.1rem 0 .45rem 0 !important;
    padding-left: .7rem;
    border-left: 3px solid #ffd866;
    line-height: 1.4;
}
.expl-body {
    color: #c8ddf5 !important;
    font-size: 1rem !important;
    line-height: 1.9 !important;
    margin: .3rem 0;
}
.expl-body strong,
.expl-body b {
    color: #e8f4ff !important;
}
.expl-list-item {
    color: #b8d4f0 !important;
    font-size: .97rem !important;
    line-height: 1.85 !important;
    padding-left: 1.2rem;
    margin: .2rem 0;
    position: relative;
}
.expl-list-item::before {
    content: "⚽";
    position: absolute;
    left: 0;
    font-size: .82rem;
}
.expl-highlight {
    color: #ffd866 !important;
    font-weight: 700 !important;
}
.expl-final {
    color: #e0f0ff !important;
    font-size: 1.04rem !important;
    font-weight: 600 !important;
    line-height: 1.9 !important;
    margin-top: .6rem;
    padding: .6rem .8rem;
    background: rgba(255,216,102,.06);
    border-radius: 10px;
    border-left: 3px solid rgba(255,216,102,.35);
}

/* ── Streamlit 表单文字颜色修复（全局加强版） ─ */
div[data-testid="stWidgetLabel"] label,
div[data-testid="stWidgetLabel"] p,
div[data-testid="stWidgetLabel"] span,
div[data-testid="stWidgetLabel"] {
    color: #e8f4ff !important;
    font-weight: 800 !important;
    font-size: 0.98rem !important;
    text-shadow: 0 1px 3px rgba(0,0,0,.3);
}
label[data-testid="stWidgetLabel"],
label[data-testid="stWidgetLabel"] span,
label[data-testid="stWidgetLabel"] p {
    color: #e8f4ff !important;
    font-weight: 800 !important;
    text-shadow: 0 1px 3px rgba(0,0,0,.3);
}
div[data-baseweb="select"] > div {
    background-color: #f0f5fc !important;
    color: #0d1f3c !important;
    border-radius: 10px !important;
    border: 1px solid rgba(150, 180, 230, .50) !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] div {
    color: #0d1f3c !important;
    font-weight: 700 !important;
}
div[role="radiogroup"] label,
div[role="radiogroup"] label span,
div[role="radiogroup"] label p,
div[role="radiogroup"] p,
div[role="radiogroup"] span,
div[role="radiogroup"] {
    color: #ffffff !important;
    font-weight: 800 !important;
    text-shadow: 0 1px 3px rgba(0,0,0,.4);
}
div[role="radiogroup"] {
    gap: 1rem !important;
}
/* selectbox / radio 外层 form 容器文字 */
div[data-testid="stForm"] label,
div[data-testid="stForm"] span,
div[data-testid="stForm"] p {
    color: #e8f4ff !important;
}
/* ── 减少连续 Streamlit 元素间距 ─ */
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"] + div[data-testid="stVerticalBlock"] {
    margin-top: -0.5rem !important;
}
/* ── 按钮文字颜色 ─ */
div[data-testid="stButton"] button {
    color: #ffffff !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #3a5fff, #1a3a8a) !important;
    border: 1px solid rgba(120,160,255,.4) !important;
    border-radius: 10px !important;
    font-size: 1rem !important;
}
div[data-testid="stButton"] button:hover {
    background: linear-gradient(135deg, #4a6fff, #2a4a9a) !important;
}
</style>
""", unsafe_allow_html=True)


# ==================== API 调用函数 ====================
def get_api_base_url() -> str:
    """从环境变量 BACKEND_URL 获取后端地址，默认指向 Render 线上地址"""
    backend_url = os.getenv("BACKEND_URL", "https://worldcup-backend-k2sn.onrender.com")
    backend_url = backend_url.rstrip("/")
    return st.session_state.get("api_base_url", f"{backend_url}/api/v1")


def fetch_final_result() -> Optional[Dict[str, Any]]:
    """从 API 获取 final_agent_result.json（前端唯一数据源）"""
    backend_url = get_api_base_url()
    api_url = f"{backend_url}/agent/final-result"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("status") in ("no_result", "error"):
            return None
        return data
    except Exception:
        # API 失败时尝试直接读取文件
        if FINAL_RESULT_PATH.exists():
            try:
                with open(FINAL_RESULT_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                return data
            except Exception:
                pass
        return None


def call_agent_api(mode: str = "llm_planner", use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """运行预测 Agent"""
    api_url = f"{get_api_base_url()}/agent/run-prediction"
    try:
        response = requests.post(
            api_url,
            json={"season": 2026, "mode": mode, "use_llm": use_llm},
            timeout=180,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接后端服务，请确认 FastAPI 已启动。")
        return None
    except requests.exceptions.Timeout:
        st.error("请求超时")
        return None
    except Exception as e:
        st.error(f"请求失败: {str(e)}")
        return None


def refresh_real_data() -> Optional[Dict[str, Any]]:
    """全量刷新：刷新赛程 → 识别存活球队 → 重新模拟 → 更新结果"""
    api_url = f"{get_api_base_url()}/data/full-refresh"
    try:
        response = requests.post(api_url, json={"season": 2026}, timeout=300)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def get_data_status() -> Optional[Dict[str, Any]]:
    """获取 canonical 数据状态"""
    api_url = f"{get_api_base_url()}/data/status"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def fetch_stage_info() -> Optional[Dict[str, Any]]:
    """获取当前赛事阶段信息（stage_info）"""
    api_url = f"{get_api_base_url()}/scenario/stage-info"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return data
        return None
    except Exception:
        return None


def fetch_scenario_pending_matches() -> Dict[str, Any]:
    """
    获取未结束的淘汰赛比赛列表（阶段感知）。
    返回完整响应：{success, matches, stage, stage_label, sandbox_enabled, sandbox_message}
    """
    api_url = f"{get_api_base_url()}/scenario/pending-matches"
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {"success": False, "matches": [], "sandbox_enabled": False,
                "sandbox_message": "无法获取比赛列表。"}


def call_scenario_simulate(match_id: str, forced_winner: str, simulation_count: int = 3000) -> Optional[Dict[str, Any]]:
    """调用沙盘推演 API"""
    api_url = f"{get_api_base_url()}/scenario/simulate"
    try:
        response = requests.post(
            api_url,
            json={"match_id": match_id, "forced_winner": forced_winner, "simulation_count": simulation_count},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        st.error("沙盘推演超时，请重试。")
        return None
    except Exception as e:
        st.error(f"沙盘推演失败: {str(e)}")
        return None


def fetch_scenario_latest() -> Optional[Dict[str, Any]]:
    """
    获取最新沙盘推演结果（含过期检测）。
    如果 is_stale=true 或 sandbox 已关闭，返回 None 并设置 session_state 提示。
    """
    api_url = f"{get_api_base_url()}/scenario/latest"
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return data
        # 过期或不可用
        if data.get("is_stale"):
            st.session_state["scenario_stale_message"] = data.get("message", "沙盘结果已过期。")
        return None
    except Exception:
        return None


# ==================== 辅助函数 ====================
def normalize_stage(stage: str) -> str:
    s = stage.lower()
    if any(k in s for k in ["round_of_32", "r32", "round of 32"]):
        return "32强"
    if any(k in s for k in ["round_of_16", "r16", "round of 16"]):
        return "16强"
    if any(k in s for k in ["quarter", "quarterfinal"]):
        return "8强"
    if any(k in s for k in ["semi", "semifinal"]):
        return "半决赛"
    if "final" in s:
        return "决赛"
    return stage


def _safe_pct(val) -> float:
    try:
        v = float(val)
        if v > 1:
            v = v / 100
        return max(0.0, min(v, 1.0)) * 100
    except Exception:
        return 0.0


def _get_team(m: Dict, *keys, default="待定"):
    for k in keys:
        v = m.get(k)
        if v:
            return v
    return default


def _get_score(m: Dict) -> str:
    for k in ["predicted_score", "score"]:
        v = m.get(k)
        if v is not None and v != "":
            return str(v)
    hs = m.get("predicted_home_score", m.get("home_score"))
    as_ = m.get("predicted_away_score", m.get("away_score"))
    if hs is not None and as_ is not None:
        return f"{hs} : {as_}"
    return "-"


def _is_finished(m: Dict) -> bool:
    """判断比赛是否已结束（FINISHED 状态）"""
    status = (m.get("status") or "").upper()
    source = m.get("source", m.get("match_source", ""))
    if status in ("FINISHED", "FINISHED_PEN", "PEN"):
        return True
    if source in ("real_result", "real_data", "football_data"):
        return True
    return False


# ==================== UI 渲染函数 ====================

def clean_explanation_text(text: str, champion_name: str) -> str:
    """清洗 AI 解释文本，移除重复标题和 markdown 标题符号"""
    import re
    lines = text.strip().split("\n")
    cleaned_lines = []
    skipped_title = False
    for line in lines:
        stripped = line.strip()
        # 跳过开头的重复标题行
        if not skipped_title and not cleaned_lines:
            # 匹配 "为什么预测 XXX 夺冠？" 或 markdown 标题形式
            if re.match(r'^#{1,3}\s*为什么预测.+夺冠', stripped):
                skipped_title = True
                continue
            if re.match(r'^为什么预测.+夺冠', stripped):
                skipped_title = True
                continue
        # 移除 markdown 标题符号
        cleaned = re.sub(r'^#{1,3}\s+', '', stripped)
        cleaned_lines.append(cleaned)
    result = "\n".join(cleaned_lines).strip()
    if not result:
        result = f"根据当前真实赛果和剩余对阵形势，{champion_name} 在后续路径中拥有较高的晋级稳定性。系统综合球队实力、近期表现和潜在对手后，认为其是当前最有希望夺冠的球队。"
    return result


def format_prob(p) -> str:
    """统一概率格式: 0.4741 → '47.4%'"""
    if p is None:
        return "—"
    v = float(p)
    if v > 1:
        v = v / 100
    return f"{v * 100:.1f}%"


def format_delta(d) -> str:
    """统一变化格式: 0.076 → '+7.6%'"""
    if d is None:
        return "—"
    v = float(d) * 100
    if v > 0:
        return f"+{v:.1f}%"
    return f"{v:.1f}%"


def display_champion_card(data: Dict):
    """冠军卡片 — 使用 official-card 样式"""
    champion = data.get("champion", "—")
    prob = data.get("champion_probability", 0)

    # 保护：如果 top5[0] 与 champion 不一致，以 top5[0] 为准（仅日志）
    top5 = data.get("top5", [])
    if top5:
        top1_team = top5[0].get("team", "")
        top1_prob = top5[0].get("probability", 0)
        if top1_team and top1_team != champion:
            import logging
            logging.getLogger(__name__).warning(
                "WARNING: champion mismatch fixed by top5[0]: %s → %s", champion, top1_team
            )
            champion = top1_team
            prob = top1_prob

    prob_display = format_probability(prob)

    # 实力标签
    top_contenders = data.get("top_contenders", [])
    strength_label = "夺冠热门"
    if top_contenders:
        champ_data = next((t for t in top_contenders if t.get("team") == champion), None)
        if champ_data:
            strength_idx = champ_data.get("team_strength_index", 0)
            if strength_idx > 0.75:
                strength_label = "夺冠热门"
            elif strength_idx > 0.6:
                strength_label = "强力竞争者"
            elif strength_idx > 0.45:
                strength_label = "有力争夺者"
            else:
                strength_label = "潜在黑马"

    st.markdown(f"""
<div class="section-card">
    <div class="section-title">🏆 正式冠军预测</div>
    <div style="color:#8fa6c8;font-size:.86rem;margin-bottom:.6rem;">基于当前真实赛果与剩余赛程推演</div>
    <div class="official-card">
        <div style="font-size:2.6rem;margin-bottom:.2rem;">🏆</div>
        <div class="champion-name">{champion}</div>
        <div class="champion-prob">{prob_display}</div>
        <div style="margin-top:.6rem;">
            <span class="sandbox-badge" style="background:rgba(255,215,0,.15);color:#ffd700;border-color:rgba(255,215,0,.35);">{strength_label}</span>
        </div>
    </div>
</div>""", unsafe_allow_html=True)


def render_explanation_html(text: str, champion_name: str) -> str:
    """将 AI 解释文本解析为带层次样式的 HTML"""
    import re
    lines = text.strip().split("\n")
    html_parts = []
    section_keywords = {"核心优势", "关键因素", "AI综合判断", "综合分析", "夺冠理由", "战术分析", "数据支撑"}
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                in_list = False
            continue

        # 检测是否是小节标题
        is_section = False
        for kw in section_keywords:
            if kw in stripped and len(stripped) < 30:
                is_section = True
                break

        if is_section:
            if in_list:
                in_list = False
            html_parts.append(f'<div class="expl-section-title">{stripped}</div>')
        elif stripped.startswith("•") or stripped.startswith("-") or stripped.startswith("*"):
            in_list = True
            item_text = re.sub(r'^[•\-*]\s*', '', stripped)
            item_text = re.sub(r'(\d+\.?\d*\s*%)', r'<span class="expl-highlight">\1</span>', item_text)
            item_text = re.sub(rf'({re.escape(champion_name)})', r'<strong>\1</strong>', item_text)
            html_parts.append(f'<div class="expl-list-item">{item_text}</div>')
        elif in_list:
            item_text = re.sub(r'(\d+\.?\d*\s*%)', r'<span class="expl-highlight">\1</span>', stripped)
            html_parts.append(f'<div class="expl-list-item">{item_text}</div>')
        else:
            in_list = False
            styled = re.sub(r'(\d+\.?\d*\s*%)', r'<span class="expl-highlight">\1</span>', stripped)
            styled = re.sub(rf'({re.escape(champion_name)})', r'<strong>\1</strong>', styled)
            if any(kw in stripped for kw in ("综合", "总结", "最终", "结论")) and len(stripped) > 40:
                html_parts.append(f'<div class="expl-final">{styled}</div>')
            else:
                html_parts.append(f'<div class="expl-body">{styled}</div>')

    return "\n".join(html_parts)


def display_explanation(data: Dict):
    """AI 冠军解读 — 使用 ai-card 样式，去重标题，增加文字层次"""
    explanation = data.get("explanation", {})
    if not explanation:
        return
    content = explanation.get("content", "")
    if not content:
        return

    # 确定正确的冠军名（与冠军卡片一致：优先 top5[0]）
    champion_name = data.get("champion", "—")
    top5 = data.get("top5", [])
    if top5:
        top1_team = top5[0].get("team", "")
        if top1_team:
            champion_name = top1_team

    # 清洗正文，移除重复标题
    cleaned_text = clean_explanation_text(content, champion_name)

    # 解析为带层次的 HTML
    expl_html = render_explanation_html(cleaned_text, champion_name)

    st.markdown(f"""
<div class="section-card">
    <div class="section-title">💡 AI 冠军解读</div>
    <div class="ai-card">
        <h3 style="color:#ffd866;margin:0 0 .6rem 0;font-size:1.1rem;font-weight:800;">为什么预测 {champion_name} 夺冠？</h3>
        {expl_html}
    </div>
</div>""", unsafe_allow_html=True)


def display_top5(data: Dict):
    """Top N 夺冠热门 — 使用 section-card + 金色概率条，统一标题 + 动态副标题"""
    top5 = data.get("top5", [])

    if not top5:
        return

    candidate_count = len(top5)

    # 统一标题
    stage_info = data.get("stage_info", {})
    stage = stage_info.get("stage", "") if stage_info else ""
    stage_label = stage_info.get("stage_label", "") if stage_info else ""

    if stage == "completed":
        label = "🏆 队伍夺冠概率"
        subtitle = "冠军已产生"
    elif stage:
        label = "🔥 队伍夺冠概率"
        subtitle = f"当前阶段：{stage_label} · {candidate_count} 支球队仍有夺冠可能"
    else:
        # 兜底：无 stage_info
        label = "🔥 队伍夺冠概率"
        subtitle = f"{candidate_count} 支球队仍有夺冠可能"

    max_pct = max(float(t.get("probability", 0)) * 100 if float(t.get("probability", 0)) <= 1
                  else float(t.get("probability", 0)) for t in top5) or 1
    rows = ""
    for i, t in enumerate(top5):
        raw_prob = float(t.get("probability", 0))
        pct = raw_prob * 100 if raw_prob <= 1 else raw_prob
        bar_w = max(pct / max_pct * 100, 8) if max_pct > 0 else 8
        prob_text = format_probability(raw_prob)
        rows += (
            f'<div class="prob-row">'
            f'<div style="font-weight:700;color:#e0e6ed;font-size:.92rem;">{t.get("team","")}</div>'
            f'<div class="prob-track"><div class="prob-fill-gold" style="width:{bar_w:.0f}%;"></div></div>'
            f'<div style="font-weight:800;color:#ffd700;font-size:.92rem;text-align:right;">{prob_text}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="section-card">'
        f'<div class="section-title">{label}</div>'
        f'<div class="section-subtitle">{subtitle}</div>'
        f'{rows}'
        f'</div>',
        unsafe_allow_html=True,
    )


def display_knockout_roadmap(data: Dict):
    """
    淘汰赛冠军之路（R32→R16→QF→SF→Final→Champion）
    颜色逻辑：FINISHED→绿色/真实比分，其他→黄色/预测比分
    数据来源：仅从 bracket_payload（fixtures 表）
    """
    bp = data.get("bracket_payload", {})
    if not bp:
        st.markdown(
            '<div class="section-card" style="text-align:center;color:#5a7090;padding:1rem 0;">'
            "暂无淘汰赛数据，请先运行预测。</div>",
            unsafe_allow_html=True,
        )
        return

    # 收集所有轮次的比赛
    rounds_data = {}
    for round_key in ["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "final"]:
        matches = bp.get(round_key, [])
        if matches:
            rnd_name = normalize_stage(round_key)
            rounds_data[rnd_name] = matches

    if not rounds_data:
        st.markdown(
            '<div class="section-card" style="text-align:center;color:#5a7090;padding:1rem 0;">'
            "暂无淘汰赛数据。</div>",
            unsafe_allow_html=True,
        )
        return

    # 构建标题 HTML（稍后与赛程图合并为一次渲染）
    header_html = """
<div class="section-card bracket-section">
<div class="section-title">🧭 淘汰赛晋级路线</div>
<div style="margin-bottom:.4rem;"><span style="color:#8a9bb5;font-size:.75rem;margin-left:.2rem;">
<span style="color:#28a745;">■</span> 已结束
<span style="color:#ffc107;margin-left:.5rem;">■</span> 预测</span></div>
"""

    # 构建各轮 HTML
    order = ["32强", "16强", "8强", "半决赛", "决赛"]
    sorted_rounds = [r for r in order if r in rounds_data]
    for r in rounds_data:
        if r not in sorted_rounds:
            sorted_rounds.append(r)

    cols_html = ""
    for rnd in sorted_rounds:
        matches_html = ""
        for m in rounds_data[rnd]:
            home = _get_team(m, "home_team", "home_team_name", "team1", "home")
            away = _get_team(m, "away_team", "away_team_name", "team2", "away")
            score = _get_score(m)
            winner = _get_team(m, "winner", "predicted_winner", "winner_team_name", default="")

            finished = _is_finished(m)

            # 颜色逻辑：FINISHED→绿色/真实比分，其他→黄色/预测比分
            if finished:
                border_cls = "road-match-green"
                score_cls = "road-score-real"
                tag_cls = "road-tag-done"
                tag_text = "已结束"
            else:
                border_cls = "road-match-yellow"
                score_cls = "road-score-predict"
                tag_cls = "road-tag-predict"
                tag_text = "预测"

            hc = "road-team-winner" if winner and home == winner else ""
            ac = "road-team-winner" if winner and away == winner else ""

            matches_html += f"""
<div class="road-match {border_cls}">
    <div class="road-match-teams">
        <span class="road-team {hc}">{home}</span>
        <span class="road-vs">vs</span>
        <span class="road-team {ac}">{away}</span>
    </div>
    <div class="road-score {score_cls}">{score}</div>
    <div style="text-align:center;"><span class="road-stage-tag {tag_cls}">{tag_text}</span></div>
</div>"""

        icon = {"32强": "🏟️", "16强": "🏟️", "8强": "🔥", "半决赛": "⚡", "决赛": "🏆"}.get(rnd, "🏟️")
        cols_html += f"""
<div class="road-round">
    <div class="road-round-title">{icon} {rnd}</div>
    <div class="road-matches">{matches_html}</div>
</div>"""

    # 冠军列
    champion = data.get("champion", "")
    if champion:
        cols_html += f"""
<div class="road-round" style="min-width:120px;max-width:140px;">
    <div class="road-round-title">🏆 冠军</div>
    <div class="road-matches" style="justify-content:center;">
        <div class="road-champion-box">
            <div style="font-size:2rem;">🏆</div>
            <div style="color:#b8860b;font-size:1.1rem;font-weight:800;margin-top:.2rem;">{champion}</div>
        </div>
    </div>
</div>"""

    st.markdown(f'{header_html}<div class="road-container">{cols_html}</div></div>', unsafe_allow_html=True)


def display_ai_analysis_process(data: Dict):
    """AI 分析过程 — 默认折叠"""
    steps = data.get("agent_steps_summary", [])
    if not steps:
        steps = [
            {"step": 1, "name": "数据获取", "description": "从 API 获取 2026 世界杯赛程与球队数据", "status": "completed"},
            {"step": 2, "name": "历史分析", "description": "加载 6000+ 场历史国际比赛数据", "status": "completed"},
            {"step": 3, "name": "模型融合", "description": "综合多种算法模型进行预测分析", "status": "completed"},
            {"step": 4, "name": "Monte Carlo 推演", "description": "10000 次模拟推演淘汰赛进程", "status": "completed"},
            {"step": 5, "name": "AI解释生成", "description": "生成冠军预测解释与关键因素分析", "status": "completed"},
        ]

    with st.expander("🔍 AI 分析过程（点击展开）", expanded=False):
        steps_html = '<div class="steps-container">'
        for s in steps:
            num = s.get("step", 0)
            name = s.get("name", "")
            desc = s.get("description", "")
            status = s.get("status", "completed")
            done_cls = "step-done" if status == "completed" else ""
            steps_html += f"""
<div class="step-item">
    <div class="step-num {done_cls}">{num}</div>
    <div>
        <div style="color:#ffd700;font-weight:700;font-size:.88rem;">{name}</div>
        <div style="color:#8a9bb5;font-size:.8rem;">{desc}</div>
    </div>
</div>"""
        steps_html += "</div>"
        st.markdown(steps_html, unsafe_allow_html=True)


def display_data_status_bar(data: Dict):
    """数据状态提示条 — 仅显示用户友好消息"""
    ds = data.get("data_status", {})
    user_message = ds.get("user_message", "")

    if not user_message:
        return

    source_level = ds.get("source_level", "unavailable")
    fixtures_count = ds.get("fixtures_count", 0)

    if source_level == "external_real" and fixtures_count > 0:
        icon, color = "✅", "#00c878"
    elif fixtures_count > 0:
        icon, color = "⚠️", "#3c8cff"
    else:
        icon, color = "❌", "#ff6b6b"

    st.markdown(f"""
<div style="background:linear-gradient(90deg,rgba(255,255,255,.04),rgba(255,255,255,.02));
    border:1px solid rgba(255,255,255,.10); border-radius:10px; padding:.55rem 1rem;
    color:{color}; font-weight:600; font-size:.85rem; margin-bottom:.4rem; text-align:center;">
    {icon} {user_message}
</div>""", unsafe_allow_html=True)


def _format_sandbox_explanation(text: str) -> str:
    """将沙盘 AI 解读的 markdown 文本转为带层次样式的 HTML（与 AI 冠军解读风格一致）"""
    import re
    lines = text.strip().split("\n")
    html_parts = []

    # 小节标题关键词（短行 + 冒号结尾 → 视为小节标题）
    section_keywords = {"新的夺冠格局", "影响分析", "沙盘假设", "推演结果", "概率变化", "关键变化", "可能决赛对阵"}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 先剥离 ** 加粗标记，得到干净文本用于检测
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
        # 再剥离列表标记（- / • / *），用于百分比行检测
        clean_for_match = re.sub(r'^[•\-*]\s*', '', clean)

        # 检测百分比行（如 "France：53.4%" 或 "France: 53.4%"）
        pct_match = re.match(r'^([A-Za-z\u4e00-\u9fff]+(?:\s*[·/]\s*[A-Za-z\u4e00-\u9fff]+)?)\s*[：:]\s*(\d+\.?\d*\s*%)', clean_for_match)
        if pct_match:
            team = pct_match.group(1)
            pct = pct_match.group(2)
            html_parts.append(
                f'<div class="expl-list-item">'
                f'{team}：<span class="expl-highlight">{pct}</span>'
                f'</div>'
            )
            continue

        # 检测小节标题（短行 + 以：结尾，或包含关键词）
        is_short_header = len(clean) < 25 and clean.endswith("：")
        is_keyword_header = any(kw in clean for kw in section_keywords) and len(clean) < 30 and "：" in clean
        if is_short_header or is_keyword_header:
            title_text = clean.rstrip("：").rstrip(":")
            html_parts.append(f'<div class="expl-section-title">{title_text}</div>')
            continue

        # 检测 "影响分析：长文本..." 这种行内标题+正文
        inline_header_match = re.match(r'^(影响分析|推演结论|综合判断|总结)\s*[：:]\s*(.+)', clean)
        if inline_header_match:
            header = inline_header_match.group(1)
            body = inline_header_match.group(2)
            body = re.sub(r'(\d+\.?\d*\s*%)', r'<span class="expl-highlight">\1</span>', body)
            html_parts.append(
                f'<div class="expl-body"><strong>{header}：</strong>{body}</div>'
            )
            continue

        # 免责声明行 — 直接跳过，不渲染
        if any(kw in clean for kw in ("仅用于", "不代表", "免责声明")):
            continue

        # 普通正文（应用 ** 加粗 + 百分比高亮）
        styled = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        styled = re.sub(r'(\d+\.?\d*\s*%)', r'<span class="expl-highlight">\1</span>', styled)
        html_parts.append(f'<div class="expl-body">{styled}</div>')

    return "\n".join(html_parts)


def display_scenario_sandbox(data: Dict):
    """冠军路径沙盘模块 — 交互式推演，仅按钮点击后展示结果"""

    # ── 交互式沙盘状态管理 ──
    if "scenario_result_visible" not in st.session_state:
        st.session_state["scenario_result_visible"] = False
    if "scenario_result" not in st.session_state:
        st.session_state["scenario_result"] = None
    if "scenario_last_run_key" not in st.session_state:
        st.session_state["scenario_last_run_key"] = None

    # ─ 获取阶段感知的比赛列表 ─
    pending_response = fetch_scenario_pending_matches()
    sandbox_enabled = pending_response.get("sandbox_enabled", False)
    sandbox_message = pending_response.get("sandbox_message", "")
    pending_matches = pending_response.get("matches", [])
    stage_label = pending_response.get("stage_label", "")

    # 仅从 session_state 读取（按钮点击后写入），不自动加载 API 缓存
    scenario = st.session_state.get("scenario_result")

    # ── 检查过期提示 ──
    stale_message = st.session_state.pop("scenario_stale_message", None)

    # ── 标题 HTML（根据阶段动态） ─
    if sandbox_enabled:
        subtitle = '选择一场未开始的半决赛，并假设其中一队晋级。点击"开始推演"后，系统会重新模拟剩余赛程，展示可能决赛对阵、沙盘夺冠概率和概率变化。'
        badge_text = "假设推演"
    else:
        subtitle = sandbox_message or "沙盘推演已结束。"
        badge_text = "已结束"

    title_html = f"""
<div class="section-title">🎮 冠军路径沙盘</div>
<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem;">
    <span class="sandbox-badge">{badge_text}</span>
    <span class="section-subtitle" style="margin:0;">{subtitle}</span>
</div>"""

    # ── CSS 样式 ──
    sandbox_css = """
<style>
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) {
    background: rgba(15, 38, 70, 0.82) !important;
    border: 1px solid rgba(120, 160, 220, 0.22) !important;
    border-radius: 20px !important;
    padding: 1.4rem 1.6rem !important;
    margin: 1.2rem 0 1.4rem 0 !important;
    box-shadow: 0 16px 36px rgba(0,0,0,.2) !important;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .section-title {
    font-size: 1.3rem !important;
    margin-bottom: 0.6rem;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .section-subtitle {
    font-size: 0.95rem !important;
    color: #b0c4de !important;
    margin-bottom: 0.5rem;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .sandbox-badge {
    font-size: 0.85rem !important;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .sandbox-result-title {
    color: #ffffff !important;
    font-size: 1.1rem !important;
    font-weight: 800;
    margin: 0.8rem 0 0.6rem;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .prob-row div,
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .scenario-compare-row div {
    font-size: 0.95rem !important;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .module-subcard > div:first-child {
    font-size: 1.05rem !important;
    color: #e8f2ff !important;
    font-weight: 700 !important;
    letter-spacing: 0.5px;
    margin-bottom: 0.6rem !important;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid rgba(255,255,255,.06);
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .ai-card > div:first-child:not([style*="font-size:1.08rem"]) {
    font-size: 0.82rem !important;
    color: #8fa6c8 !important;
    letter-spacing: 1.6px;
    margin-bottom: 0.3rem;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .ai-card > div:last-child {
    font-size: 1.02rem !important;
    color: #d6e8ff !important;
    line-height: 1.9;
    letter-spacing: 0.3px;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .ai-card {
    background: rgba(20, 52, 92, .68) !important;
    border: 1px solid rgba(88, 190, 255, .22) !important;
    border-left: 4px solid #36d1ff !important;
    border-radius: 14px !important;
    padding: 1.1rem 1.3rem !important;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) label,
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .stSelectbox label,
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .stRadio label {
    font-size: 0.95rem !important;
    color: #d6e8ff !important;
}
div[data-testid="stVerticalBlock"]:has(#sandbox-container-marker) .warning-note {
    font-size: 0.9rem !important;
    margin-top: 1rem;
}
</style>
"""

    st.markdown(sandbox_css, unsafe_allow_html=True)

    # ── 沙盘已关闭（决赛/已结束）──
    if not sandbox_enabled:
        with st.container():
            st.markdown('<div id="sandbox-container-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.markdown(title_html, unsafe_allow_html=True)
            st.markdown(f"""
<div style="text-align:center;color:#5a7090;padding:1rem 0;font-size:1rem;">
    {sandbox_message or "沙盘推演已结束。"}
</div>""", unsafe_allow_html=True)
            st.markdown("""
<div class="warning-note">
    ⚠️ 该模块不会修改真实赛果，也不会影响正式冠军预测。
</div>""", unsafe_allow_html=True)
        return

    # ── 没有可推演的比赛（sandbox 开启但比赛列表为空） ──
    if not pending_matches:
        with st.container():
            st.markdown('<div id="sandbox-container-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.markdown(title_html, unsafe_allow_html=True)
            st.markdown("""
<div style="text-align:center;color:#5a7090;padding:1rem 0;font-size:1rem;">
    暂时无法获取可推演比赛列表，请稍后重试。
</div>""", unsafe_allow_html=True)
            st.markdown("""
<div class="warning-note">
    ⚠️ 该模块不会修改真实赛果，也不会影响正式冠军预测。
</div>""", unsafe_allow_html=True)
        return

    # ── 构建选项 ──
    stage_cn = {"semi_finals": "半决赛", "quarter_finals": "8强", "round_of_16": "16强",
                "round_of_32": "32强", "final": "决赛"}
    match_options = []
    match_map = {}
    for m in pending_matches:
        label = f"{m['home_team']} vs {m['away_team']}"
        stage_lbl = stage_cn.get(m.get("stage", ""), m.get("stage", ""))
        display = f"{label}（{stage_lbl}）"
        match_options.append(display)
        match_map[display] = m

    with st.container():
        st.markdown('<div id="sandbox-container-marker" style="display:none;"></div>', unsafe_allow_html=True)

        # ── 标题 ──
        st.markdown(title_html, unsafe_allow_html=True)

        # ── 过期提示 ──
        if stale_message:
            st.markdown(f"""
<div style="background:linear-gradient(90deg,rgba(255,180,50,.12),rgba(255,180,50,.04));
    border:1px solid rgba(255,180,50,.30); border-radius:8px; padding:.5rem 1rem;
    color:#ffb432; font-weight:600; font-size:.85rem; margin-bottom:.6rem; text-align:center;">
    ⚠️ {stale_message}
</div>""", unsafe_allow_html=True)

        # ── 表单 ──
        col_a, col_b, col_c = st.columns([2, 1.2, 1])

        with col_a:
            selected_match_label = st.selectbox("选择比赛", match_options, key="scenario_match_select")

        selected_match = match_map.get(selected_match_label, {})
        home = selected_match.get("home_team", "")
        away = selected_match.get("away_team", "")
        match_id = selected_match.get("match_id", "")

        with col_b:
            forced_winner = st.radio(
                "假设晋级队",
                [home, away],
                key="scenario_winner_radio",
                horizontal=True,
            )

        with col_c:
            st.markdown('<div style="margin-top:1.55rem;"></div>', unsafe_allow_html=True)
            run_clicked = st.button("开始推演", use_container_width=True, key="scenario_run_btn")

        # ─ 选择变化检测：切换比赛或晋级队后隐藏旧结果 ──
        _current_key = f"{match_id}:{forced_winner}"
        if st.session_state.get("scenario_last_run_key") != _current_key:
            st.session_state["scenario_result_visible"] = False

        # 轻提示：条件已更改
        if st.session_state.get("scenario_result") and not st.session_state.get("scenario_result_visible"):
            st.info('已更改假设条件，请点击"开始推演"查看新结果。', icon="ℹ️")

        # ── 推演按钮逻辑 ──
        if run_clicked:
            if not match_id or not forced_winner:
                st.warning("请选择比赛和假设晋级队。")
            else:
                with st.spinner("正在进行沙盘推演（3000 次模拟）..."):
                    result = call_scenario_simulate(match_id, forced_winner)
                if result and result.get("success"):
                    st.session_state["scenario_result"] = result
                    st.session_state["scenario_result_visible"] = True
                    st.session_state["scenario_last_run_key"] = f"{match_id}:{forced_winner}"
                    st.rerun()
                elif result:
                    st.session_state["scenario_result_visible"] = False
                    if result.get("scenario_scope") == "disabled":
                        st.warning(result.get("message", "沙盘推演已关闭。"))
                    else:
                        st.error(f"推演失败: {result.get('error', '未知错误')}")
                else:
                    st.session_state["scenario_result_visible"] = False
                    st.error("沙盘推演请求失败，请稍后重试。")

        # ─ 结果内容（仅按钮推演成功后展示） ──
        if st.session_state.get("scenario_result_visible") and scenario:
            sc = scenario.get("scenario", {})
            forced_winner_name = sc.get("forced_winner", "")
            forced_loser_name = sc.get("forced_loser", "")

            content_html = f"""
<div class="sandbox-result-title">
    沙盘推演结果：假设 {forced_winner_name} 淘汰 {forced_loser_name}
</div>"""

            # ── 沙盘夺冠概率 ──
            champ_dist = scenario.get("champion_distribution", [])
            if champ_dist:
                max_pct = max(cd.get("probability", 0) * 100 for cd in champ_dist) or 1
                rows_html = ""
                for cd in champ_dist:
                    pct = cd.get("probability", 0) * 100
                    bar_w = max(pct / max_pct * 100, 8)
                    rows_html += (
                        f'<div class="prob-row">'
                        f'<div style="font-weight:700;color:#e8f2ff;">{cd.get("name","")}</div>'
                        f'<div class="prob-track"><div class="prob-fill-blue" style="width:{bar_w:.0f}%;"></div></div>'
                        f'<div style="font-weight:800;color:#aebcff;text-align:right;">{pct:.1f}%</div>'
                        f'</div>'
                    )
                content_html += f"""
<div class="module-subcard">
    <div>沙盘夺冠概率</div>
    {rows_html}
</div>"""

            # ── 可能决赛对阵（新结构） ──
            final_matchup_dist = scenario.get("final_matchup_distribution", [])
            if final_matchup_dist:
                matchup_html = ""
                for fm in final_matchup_dist[:5]:
                    pct = fm.get("probability", 0) * 100
                    matchup_html += (
                        f'<div class="prob-row">'
                        f'<div style="font-weight:600;color:#e8f2ff;font-size:.88rem;">{fm.get("matchup","")}</div>'
                        f'<div class="prob-track"><div class="prob-fill-blue" style="width:{max(pct * 2, 8):.0f}%;"></div></div>'
                        f'<div style="font-weight:700;color:#aebcff;text-align:right;font-size:.88rem;">{pct:.1f}%</div>'
                        f'</div>'
                    )
                content_html += f"""
<div class="module-subcard">
    <div>可能决赛对阵</div>
    {matchup_html}
</div>"""

            # ── 晋级决赛概率（新结构） ──
            finalist_dist = scenario.get("finalist_distribution", [])
            if finalist_dist:
                finalist_html = ""
                for fd in finalist_dist:
                    pct = fd.get("finalist_probability", 0) * 100
                    finalist_html += (
                        f'<div class="prob-row">'
                        f'<div style="font-weight:700;color:#e8f2ff;">{fd.get("name","")}</div>'
                        f'<div class="prob-track"><div class="prob-fill-blue" style="width:{max(pct * 2, 8):.0f}%;"></div></div>'
                        f'<div style="font-weight:800;color:#aebcff;text-align:right;">{pct:.1f}%</div>'
                        f'</div>'
                    )
                content_html += f"""
<div class="module-subcard">
    <div>晋级决赛概率</div>
    {finalist_html}
</div>"""

            # ── 正式 vs 沙盘对比 ──
            comparison = scenario.get("comparison", [])
            if comparison:
                header = ('<div style="display:grid;grid-template-columns:110px 1fr 1fr 90px;'
                          'gap:.8rem;padding:.4rem .6rem;'
                          'border-bottom:1px solid rgba(255,255,255,.12);font-size:.8rem;'
                          'color:#7a92ad;font-weight:600;letter-spacing:1px;">'
                          '<div>球队</div>'
                          '<div style="text-align:center;">正式预测</div>'
                          '<div style="text-align:center;">沙盘预测</div>'
                          '<div style="text-align:center;">变化</div></div>')

                rows = ""
                for c in comparison:
                    name = c.get("name", "")
                    official_p = format_prob(c.get("official_probability", 0))
                    scenario_p = format_prob(c.get("scenario_probability", 0))
                    delta = c.get("delta", 0)
                    trend = c.get("trend", "same")

                    if trend == "eliminated":
                        delta_text = "淘汰"
                        delta_cls = "delta-out"
                    elif trend == "up":
                        delta_text = f"↑ {format_delta(delta)}"
                        delta_cls = "delta-up"
                    elif trend == "down":
                        delta_text = f"↓ {format_delta(delta)}"
                        delta_cls = "delta-down"
                    else:
                        delta_text = format_delta(delta)
                        delta_cls = "delta-down" if float(delta) < 0 else "delta-up"

                    rows += (
                        f'<div class="scenario-compare-row" style="display:grid;'
                        f'grid-template-columns:110px 1fr 1fr 90px;gap:.8rem;">'
                        f'<div style="font-weight:600;color:#e8f2ff;">{name}</div>'
                        f'<div style="text-align:center;color:#8a9bb5;">{official_p}</div>'
                        f'<div style="text-align:center;color:#aebcff;">{scenario_p}</div>'
                        f'<div style="text-align:center;" class="{delta_cls}">{delta_text}</div>'
                        f'</div>'
                    )

                content_html += f"""
<div class="module-subcard">
    <div>正式 vs 沙盘对比</div>
    {header}{rows}
</div>"""

            # ── AI 沙盘解读 ──
            explanation = scenario.get("explanation", "")
            if explanation:
                expl_html = _format_sandbox_explanation(explanation)
                content_html += f"""
<div class="ai-card" style="margin-bottom:.5rem;">
    <div style="font-size:1.08rem;font-weight:800;color:#e8f2ff;margin-bottom:.7rem;padding-bottom:.35rem;border-bottom:1px solid rgba(255,255,255,.08);">AI 沙盘解读</div>
    <div style="color:#c8ddf5;line-height:1.9;font-size:1rem;">
        {expl_html}
    </div>
</div>"""

            st.markdown(content_html, unsafe_allow_html=True)

        # ── 警告 ──
        st.markdown("""
<div class="warning-note">
    ⚠️ 该模块不会修改真实赛果，也不会影响正式冠军预测。
</div>""", unsafe_allow_html=True)



# ==================== 主函数 ====================
def main():
    # ── 始终从 API 获取最新数据（不依赖旧 session_state 缓存） ──
    data = fetch_final_result()
    if data:
        st.session_state["final_result"] = data

    # ── 无结果：启动页 ──
    if not data:
        st.markdown("""
<div style="text-align:center;padding:2rem 0 .8rem;">
    <div style="font-size:2.4rem;margin-bottom:.2rem;">
        <span class="decor-bounce" style="animation-delay:0s;">⚽</span>
        <span class="decor-float" style="animation-delay:.3s;">🐱</span>
        <span class="decor-bounce" style="animation-delay:.6s;">🏆</span>
        <span class="decor-float" style="animation-delay:.9s;">🐶</span>
        <span class="decor-bounce" style="animation-delay:1.2s;">⚽</span>
    </div>
    <h1 class="hero-title" style="font-size:2rem;">2026 世界杯冠军预测</h1>
    <p class="hero-sub" style="margin-bottom:1rem;">基于历史比赛、球队实力与赛程推演的智能预测系统</p>
</div>""", unsafe_allow_html=True)

        # 检查数据状态
        ds = get_data_status() or {}
        fc = ds.get("fixtures_count", 0)
        sl = ds.get("source_level", "unavailable")
        um = ds.get("user_message", "当前比赛数据不足，请先刷新数据源。")

        if fc > 0 and sl in ("external_real", "verified_cache"):
            st.markdown(f"""
<div style="background:linear-gradient(90deg,rgba(0,200,120,.10),rgba(0,200,120,.04));
    border:1px solid rgba(0,200,120,.30); border-radius:10px; padding:.55rem 1rem;
    color:#00c878; font-weight:600; font-size:.85rem; margin-bottom:.4rem; text-align:center;">
    ✅ {um}
</div>""", unsafe_allow_html=True)
        elif fc > 0:
            st.markdown(f"""
<div style="background:linear-gradient(90deg,rgba(60,140,255,.10),rgba(60,140,255,.04));
    border:1px solid rgba(60,140,255,.30); border-radius:10px; padding:.55rem 1rem;
    color:#3c8cff; font-weight:600; font-size:.85rem; margin-bottom:.4rem; text-align:center;">
    ⚠️ {um}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
<div style="background:linear-gradient(90deg,rgba(255,100,100,.10),rgba(255,100,100,.04));
    border:1px solid rgba(255,100,100,.30); border-radius:10px; padding:.55rem 1rem;
    color:#ff6b6b; font-weight:600; font-size:.85rem; margin-bottom:.4rem; text-align:center;">
    ❌ {um}
</div>""", unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            allow_pred = fc > 0 and sl in ("external_real", "verified_cache")
            if st.button("🏆 开始预测", use_container_width=True, disabled=not allow_pred):
                with st.spinner("正在运行预测，请稍候..."):
                    res = call_agent_api(mode="llm_planner_safe", use_llm=True)
                if res:
                    # 清除旧缓存，重新加载
                    st.session_state.pop("final_result", None)
                    final = fetch_final_result()
                    if final:
                        st.session_state["final_result"] = final
                    st.success("预测完成")
                    st.rerun()
                else:
                    st.error("预测请求失败，请检查后端服务。")

            if st.button("📡 刷新比赛数据", use_container_width=True):
                with st.spinner("正在全量刷新（赛程→存活球队→模拟→结果）..."):
                    res = refresh_real_data()
                if res and res.get("success"):
                    surviving = res.get("steps", {}).get("identify_surviving", {}).get("surviving_teams", [])
                    stage = res.get("steps", {}).get("identify_surviving", {}).get("stage", "")
                    st.session_state.pop("scenario_result", None)
                    st.session_state["scenario_result_visible"] = False
                    st.session_state["scenario_last_run_key"] = None
                    st.success(f"全量刷新完成！阶段: {stage}，存活球队: {len(surviving)} 支")
                    st.rerun()
                else:
                    st.warning("全量刷新部分失败，已使用当前可用数据。")
        return

    # ── 有结果：渲染展示页 ──
    # 1. 标题区
    st.markdown("""
<div style="text-align:center;padding:.6rem 0 .3rem;">
    <div style="font-size:2.4rem;margin-bottom:.1rem;">
        <span class="decor-bounce" style="animation-delay:0s;">⚽</span>
        <span class="decor-float" style="animation-delay:.3s;">🐱</span>
        <span class="decor-bounce" style="animation-delay:.6s;">🏆</span>
        <span class="decor-float" style="animation-delay:.9s;">🐶</span>
        <span class="decor-bounce" style="animation-delay:1.2s;">⚽</span>
    </div>
    <h1 class="hero-title">2026 世界杯冠军预测</h1>
    <p class="hero-sub">基于历史比赛、球队实力与赛程推演的智能分析</p>
</div>""", unsafe_allow_html=True)

    # 2. 操作按钮区
    bc1, bc2, bc3 = st.columns([1, 2, 1])
    with bc2:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🔄 重新预测", use_container_width=True):
                with st.spinner("正在运行预测，请稍候..."):
                    res = call_agent_api(mode="llm_planner_safe", use_llm=True)
                if res:
                    st.session_state.pop("final_result", None)
                    st.session_state.pop("scenario_result", None)
                    st.session_state["scenario_result_visible"] = False
                    st.session_state["scenario_last_run_key"] = None
                    st.cache_data.clear()
                    final = fetch_final_result()
                    if final:
                        st.session_state["final_result"] = final
                    st.success("预测完成")
                    st.rerun()
                else:
                    st.error("预测请求失败。")
        with c2:
            if st.button("📡 刷新数据", use_container_width=True):
                with st.spinner("正在全量刷新（赛程→存活球队→模拟→结果）..."):
                    res = refresh_real_data()
                if res and res.get("success"):
                    surviving = res.get("steps", {}).get("identify_surviving", {}).get("surviving_teams", [])
                    stage = res.get("steps", {}).get("identify_surviving", {}).get("stage", "")
                    st.session_state.pop("scenario_result", None)
                    st.session_state["scenario_result_visible"] = False
                    st.session_state["scenario_last_run_key"] = None
                    st.success(f"全量刷新完成！阶段: {stage}，存活球队: {len(surviving)} 支")
                    st.rerun()
                else:
                    st.warning("暂时无法刷新。")
        with c3:
            if st.button("🧹 清除缓存", use_container_width=True):
                st.session_state.clear()
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()

    # 3. 数据状态提示
    display_data_status_bar(data)

    # 4. 正式冠军预测
    display_champion_card(data)

    # 5. AI 冠军解读
    display_explanation(data)

    # 6. 淘汰赛晋级路线
    display_knockout_roadmap(data)

    # 7. 队伍夺冠概率（统一标题 + 动态副标题）
    display_top5(data)

    # 8. 冠军路径沙盘
    display_scenario_sandbox(data)

    # 9. AI 分析过程（默认折叠）
    display_ai_analysis_process(data)

    # 10. 页脚装饰
    st.markdown("""
<div style="text-align:center;padding:1.5rem 0 1rem;opacity:.55;">
    <span class="decor-bounce" style="font-size:1.2rem;animation-delay:0s;">⚽</span>
    <span class="decor-float" style="font-size:1.2rem;animation-delay:.4s;">🐱</span>
    <span class="decor-bounce" style="font-size:1.2rem;animation-delay:.8s;">🏆</span>
    <span class="decor-float" style="font-size:1.2rem;animation-delay:1.2s;">🐶</span>
    <span class="decor-bounce" style="font-size:1.2rem;animation-delay:1.6s;">⚽</span>
    <div style="color:#5a7090;font-size:.78rem;margin-top:.4rem;">2026 FIFA World Cup · AI Prediction System</div>
</div>""", unsafe_allow_html=True)



if __name__ == "__main__":
    main()
