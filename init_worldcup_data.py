"""
2026 世界杯数据初始化脚本

功能：
1. 清理战场：清空 worldcup.db 中的旧数据并重建表
2. 生成架构：按 2026 赛制将 48 支参赛队分配到 12 个小组
3. 唤醒特种兵：驱动 Playwright 爬虫抓取球队身价
4. 唤醒通信兵：驱动 API 客户端拉取最近 5 场真实赛果
"""
import asyncio
from app.db.database import SessionLocal, Base, engine, init_db
from app.models.schemas import Team, Match, Prediction, SimulationRecord
from app.data.web_scraper import TeamDataScraper
from app.data.api_fetcher import FootballAPIClients
from app.core.config import get_settings

# 2026 世界杯模拟参赛的 48 支强队 (带有 API-Sports 对应的官方 Team ID)
# 为节省测试时间，先初始化这 8 支超一线强队，跑通后再加全 48 支
WORLD_CUP_TEAMS = [
    {"name": "Argentina",   "group": "Group A", "id": 26,    "confederation": "CONMEBOL", "elo": 2100.0},
    {"name": "France",      "group": "Group A", "id": 2,     "confederation": "UEFA",     "elo": 2080.0},
    {"name": "Brazil",      "group": "Group A", "id": 6,     "confederation": "CONMEBOL", "elo": 2060.0},
    {"name": "England",     "group": "Group A", "id": 10,    "confederation": "UEFA",     "elo": 2040.0},
    {"name": "Spain",       "group": "Group B", "id": 9,     "confederation": "UEFA",     "elo": 2020.0},
    {"name": "Germany",     "group": "Group B", "id": 25,    "confederation": "UEFA",     "elo": 2000.0},
    {"name": "Portugal",    "group": "Group B", "id": 27,    "confederation": "UEFA",     "elo": 1980.0},
    {"name": "Netherlands", "group": "Group B", "id": 1118,  "confederation": "UEFA",     "elo": 1960.0},
]


async def initialize_data():
    print("=" * 60)
    print("🚀 正在启动系统数据大灌溉...")
    print("=" * 60)

    # ── 1. 准备工具 ──
    settings = get_settings()
    api_client = FootballAPIClients(api_key=settings.API_FOOTBALL_KEY)
    scraper = TeamDataScraper()

    # ── 1.5 确保数据库表结构最新（添加新列） ──
    init_db()  # 创建所有表
    import sqlite3
    db_path = engine.url.database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 检查并添加新列
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(teams)").fetchall()}
    if "group_name" not in existing_cols:
        cursor.execute("ALTER TABLE teams ADD COLUMN group_name VARCHAR(50)")
    if "total_value_eur" not in existing_cols:
        cursor.execute("ALTER TABLE teams ADD COLUMN total_value_eur FLOAT")
    if "recent_form" not in existing_cols:
        cursor.execute("ALTER TABLE teams ADD COLUMN recent_form VARCHAR(20)")
    conn.commit()
    conn.close()
    print("   ✅ 数据库表结构已更新")

    db = SessionLocal()

    # ── 2. 清理旧数据 ──
    print("\n🧹 清理旧数据表...")
    db.query(SimulationRecord).delete()
    db.query(Prediction).delete()
    db.query(Match).delete()
    db.query(Team).delete()
    db.commit()
    print("   ✅ 旧数据已清空")

    # ── 3. 逐队处理：爬虫 + API + 入库 ──
    for t_info in WORLD_CUP_TEAMS:
        print(f"\n{'=' * 50}")
        print(f"⚽ 正在处理球队: {t_info['name']}")

        # [步骤 A] 爬虫行动：抓取身价
        print(f"   🕷️ [爬虫] 启动 Playwright 抓取身价...")
        value_data = await scraper.scrape_team_value(t_info['name'])
        total_value = value_data.get("total_value", 500_000_000)
        print(f"   ✅ 身价: €{total_value:,.0f} (来源: {value_data.get('source', 'default')})")

        # [步骤 B] API 行动：获取战绩
        print(f"   📡 [API] 呼叫官方接口获取近期战绩...")
        form_data = api_client.fetch_team_recent_form(t_info['id'], season=2024)
        form_str = form_data.get("form", "-----")
        source = form_data.get("source", "none")
        print(f"   ✅ 战绩: {form_str} (来源: {source})")

        # [步骤 C] 数据入库
        new_team = Team(
            name=t_info['name'],
            confederation=t_info['confederation'],
            current_elo=t_info['elo'],
            group_name=t_info['group'],
            total_value_eur=total_value,
            recent_form=form_str,
        )
        db.add(new_team)
        db.commit()
        db.refresh(new_team)

        print(f"   💾 {t_info['name']} 已入库！(ID={new_team.id}, 身价: €{total_value:,.0f}, 战绩: {form_str})")

    # ── 4. 收尾 ──
    await scraper.close()
    db.close()

    print(f"\n{'=' * 60}")
    print("🎉 数据初始化彻底完成！所有数据已灌入 worldcup.db！")
    print(f"{'=' * 60}")

    # 打印汇总
    db2 = SessionLocal()
    teams = db2.query(Team).all()
    print(f"\n📊 共入库 {len(teams)} 支球队：")
    for t in teams:
        print(f"   [{t.group_name}] {t.name:15s} | Elo: {t.current_elo:.0f} | 身价: €{t.total_value_eur or 0:,.0f} | 战绩: {t.recent_form or '-----'}")
    db2.close()


if __name__ == "__main__":
    asyncio.run(initialize_data())
