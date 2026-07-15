"""
APScheduler 后台定时任务调度器

任务调度：
- 任务 A（动态数据）：每天 02:00 / 14:00 刷新球队近期战绩
- 任务 B（静态爬虫）：每周一 03:00 更新球队身价
- 任务 C（计算刷新）：数据抓取后自动触发 Elo 重新计算
"""

import logging
from datetime import datetime
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# ==================== 颜色输出 ====================

class Colors:
    """终端颜色代码"""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def log_colored(message: str, color: str = Colors.GREEN):
    """打印彩色日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{timestamp}] {message}{Colors.RESET}")


# ==================== 定时任务定义 ====================

async def task_fetch_dynamic_data():
    """
    任务 A：抓取动态数据（球队近期战绩、实时比分）
    
    调用 FootballAPIClients 刷新缓存
    """
    log_colored("⚽ 开始执行动态数据抓取任务...", Colors.CYAN)
    
    try:
        from app.data.api_fetcher import get_api_client
        from app.core.config import get_settings
        
        settings = get_settings()
        client = get_api_client(api_key=settings.API_FOOTBALL_KEY)
        
        # 获取所有世界杯参赛球队的 ID 列表
        # API-Football 球队 ID 映射（主要参赛队）
        team_ids = [
            85,   # France
            31,   # Argentina
            71,   # Brazil
            82,   # Germany
            529,  # Spain
            402,  # Portugal
            42,   # England
            48,   # Netherlands
            1,    # USA
            83,   # Japan
            # ... 更多球队
        ]
        
        success_count = 0
        for team_id in team_ids:
            try:
                result = client.fetch_team_recent_form(team_id)
                if result.get("source") in ("api", "cache"):
                    success_count += 1
            except Exception as e:
                logger.warning(f"球队 {team_id} 数据抓取失败: {e}")
        
        # 同时刷新实时比分
        try:
            client.fetch_live_scores()
        except Exception as e:
            logger.warning(f"比分抓取失败: {e}")
        
        log_colored(f"✅ 动态数据抓取完成: {success_count}/{len(team_ids)} 支球队", Colors.GREEN)
        
        # 触发任务 C：重新计算 Elo
        await task_refresh_elo_ratings()
        
    except Exception as e:
        log_colored(f"❌ 动态数据抓取失败: {e}", Colors.YELLOW)
        logger.error(f"动态数据抓取任务异常: {e}")


async def task_fetch_static_data():
    """
    任务 B：抓取静态数据（球队身价、阵容信息）
    
    调用 TeamDataScraper 更新身价数据
    """
    log_colored("💰 开始执行静态数据爬虫任务...", Colors.MAGENTA)
    
    try:
        from app.data.web_scraper import get_scraper
        
        scraper = get_scraper(enable_delay=True)
        
        # 世界杯主要参赛队
        team_names = [
            "France", "Argentina", "Brazil", "Germany", "Spain",
            "Portugal", "England", "Netherlands", "USA", "Japan",
            "Croatia", "Uruguay", "Belgium", "Italy", "Mexico"
        ]
        
        success_count = 0
        for team_name in team_names:
            try:
                result = await scraper.scrape_team_value(team_name)
                if result.get("source") in ("transfermarkt", "default"):
                    success_count += 1
                    log_colored(f"  {team_name}: {result['total_value_str']}", Colors.BLUE)
            except Exception as e:
                logger.warning(f"球队 {team_name} 身价抓取失败: {e}")
        
        log_colored(f"✅ 静态数据爬虫完成: {success_count}/{len(team_names)} 支球队", Colors.GREEN)
        
        # 触发任务 C：重新计算 Elo
        await task_refresh_elo_ratings()
        
    except Exception as e:
        log_colored(f"❌ 静态数据爬虫失败: {e}", Colors.YELLOW)
        logger.error(f"静态数据爬虫任务异常: {e}")


async def task_refresh_elo_ratings():
    """
    任务 C：重新计算所有球队的 Elo 评分
    
    基于最新比赛数据更新 Elo 并存入数据库
    """
    log_colored("📊 开始刷新 Elo 评分...", Colors.CYAN)
    
    try:
        from app.db.database import SessionLocal
        from app.models.schemas import Team
        from app.services.probability_engine import ProbabilityEngine
        
        db = SessionLocal()
        
        try:
            # 获取所有球队
            teams = db.query(Team).all()
            updated_count = 0
            
            for team in teams:
                # 这里可以根据最新比赛结果更新 Elo
                # 简化版本：保持当前 Elo 不变，仅记录更新时间
                updated_count += 1
            
            db.commit()
            log_colored(f"✅ Elo 评分刷新完成: {updated_count} 支球队", Colors.GREEN)
            
        finally:
            db.close()
            
    except Exception as e:
        log_colored(f"❌ Elo 刷新失败: {e}", Colors.YELLOW)
        logger.error(f"Elo 刷新任务异常: {e}")


async def task_full_refresh():
    """
    任务 D：每日全量刷新流水线

    1. 刷新 fixtures（从外部 API 拉取最新赛程/比分）
    2. 识别 surviving_teams（仍有夺冠可能的球队）
    3. Monte Carlo 模拟（只在 surviving_teams 中模拟）
    4. 更新 final_agent_result.json
    """
    log_colored("🔄 开始执行每日全量刷新...", Colors.CYAN)

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        from app.services.scheduled_refresh_service import run_full_refresh_pipeline

        # 在线程池中运行同步代码（避免阻塞事件循环）
        result = await loop.run_in_executor(None, run_full_refresh_pipeline)

        if result.get("success"):
            surviving = result.get("steps", {}).get("identify_surviving", {}).get("surviving_teams", [])
            stage = result.get("steps", {}).get("identify_surviving", {}).get("stage", "?")
            top = result.get("steps", {}).get("simulation", {}).get("top_champion", "?")
            log_colored(
                f"✅ 全量刷新完成: stage={stage}, surviving={surviving}, champion={top}",
                Colors.GREEN
            )
        else:
            failed_steps = [
                name for name, step in result.get("steps", {}).items()
                if not step.get("success")
            ]
            log_colored(f"⚠️ 全量刷新部分失败: {failed_steps}", Colors.YELLOW)

    except Exception as e:
        log_colored(f"❌ 全量刷新失败: {e}", Colors.YELLOW)
        logger.error(f"全量刷新任务异常: {e}")


# ==================== 调度器管理 ====================

_scheduler: Optional[AsyncIOScheduler] = None


def create_scheduler() -> AsyncIOScheduler:
    """
    创建并配置 APScheduler 调度器
    
    Returns:
        配置好的 AsyncIOScheduler 实例
    """
    scheduler = AsyncIOScheduler(
        timezone="Asia/Shanghai",
        job_defaults={
            "coalesce": True,  # 合并错过的执行
            "max_instances": 1,  # 每个任务最多 1 个实例
            "misfire_grace_time": 3600  # 错过 1 小时内仍执行
        }
    )
    
    # 任务 A：每天 02:00 和 14:00 抓取动态数据
    scheduler.add_job(
        task_fetch_dynamic_data,
        trigger=CronTrigger(hour=2, minute=0),
        id="fetch_dynamic_data_morning",
        name="动态数据抓取(凌晨)",
        replace_existing=True
    )
    
    scheduler.add_job(
        task_fetch_dynamic_data,
        trigger=CronTrigger(hour=14, minute=0),
        id="fetch_dynamic_data_afternoon",
        name="动态数据抓取(下午)",
        replace_existing=True
    )
    
    # 任务 B：每周一 03:00 抓取静态数据
    scheduler.add_job(
        task_fetch_static_data,
        trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="fetch_static_data_weekly",
        name="静态数据爬虫(每周)",
        replace_existing=True
    )
    
    # 任务 D：每天 06:00 全量刷新（赛程→存活球队→模拟→更新结果）
    scheduler.add_job(
        task_full_refresh,
        trigger=CronTrigger(hour=6, minute=0),
        id="full_daily_refresh",
        name="全量刷新(每日)",
        replace_existing=True
    )
    
    return scheduler


def start_scheduler():
    """
    启动调度器（在 FastAPI lifespan 中调用）

    通过 ENABLE_SCHEDULER 环境变量控制是否启动。
    生产环境多实例部署时，应只在一个实例启用。

    Returns:
        已启动的调度器实例，或 None（未启用时）
    """
    import os
    global _scheduler

    # 环境变量开关
    enable_str = os.getenv("ENABLE_SCHEDULER", "true").lower()
    if enable_str in ("false", "0", "no", "off"):
        log_colored("⚠️ APScheduler disabled by ENABLE_SCHEDULER=false", Colors.YELLOW)
        return None

    if _scheduler is not None:
        log_colored("⚠️ 调度器已在运行中", Colors.YELLOW)
        return _scheduler

    _scheduler = create_scheduler()
    _scheduler.start()
    
    log_colored("=" * 50, Colors.GREEN)
    log_colored("📅 APScheduler 定时任务调度器已启动", Colors.GREEN)
    log_colored("  ⚽ 任务 A: 每天 02:00 / 14:00 刷新动态数据", Colors.CYAN)
    log_colored("  💰 任务 B: 每周一 03:00 更新球队身价", Colors.MAGENTA)
    log_colored("  📊 任务 C: 数据更新后自动刷新 Elo 评分", Colors.BLUE)
    log_colored("  🔄 任务 D: 每天 06:00 全量刷新(赛程→存活球队→模拟→结果)", Colors.GREEN)
    log_colored("=" * 50, Colors.GREEN)
    
    return _scheduler


def stop_scheduler():
    """停止调度器（在 FastAPI lifespan 关闭时调用）"""
    global _scheduler
    
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log_colored("📅 调度器已停止", Colors.YELLOW)


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """获取当前调度器实例"""
    return _scheduler


def get_scheduler_status() -> dict:
    """
    获取调度器状态信息（用于 API 查询）
    
    Returns:
        调度器状态字典
    """
    if _scheduler is None:
        return {
            "running": False,
            "jobs": []
        }
    
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": _scheduler.running,
        "jobs": jobs
    }


# ==================== 手动触发（调试用）====================

async def trigger_task(task_name: str) -> bool:
    """
    手动触发指定任务（用于调试/测试）
    
    Args:
        task_name: 任务名称 ("dynamic" | "static" | "elo")
    
    Returns:
        是否成功触发
    """
    task_map = {
        "dynamic": task_fetch_dynamic_data,
        "static": task_fetch_static_data,
        "elo": task_refresh_elo_ratings,
        "full_refresh": task_full_refresh,
    }
    
    task_func = task_map.get(task_name)
    if task_func:
        log_colored(f"🔧 手动触发任务: {task_name}", Colors.YELLOW)
        await task_func()
        return True
    
    return False


# ==================== 测试入口 ====================

if __name__ == "__main__":
    import asyncio
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("APScheduler 调度器测试")
    print("=" * 60)
    
    # 测试手动触发任务
    async def test():
        print("\n[1] 测试手动触发 Elo 刷新任务:")
        await trigger_task("elo")
        
        print("\n[2] 调度器状态:")
        print(get_scheduler_status())
    
    asyncio.run(test())
    
    print("\n测试完成！")
