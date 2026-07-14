"""
FastAPI 应用入口文件
使用 lifespan 特性管理应用生命周期，集成 PyTorch、ChromaDB 和 LLM Agent
"""
from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.database import init_db, engine
from app.api.routes import api_router

# 导入 Agent 数据库模型，确保 Base.metadata 包含这些表
import app.models.agent_models  # noqa: F401

# 配置对象
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理器
    
    在应用启动时执行初始化操作：
    - SQLite 数据库引擎
    - PyTorch 权重文件
    - ChromaDB 索引
    - LLM Agent
    
    在应用关闭时执行清理操作
    """
    # === 启动阶段 ===
    print("🚀 Starting World Cup Prediction API...")
    
    # 1. 初始化 SQLite 数据库
    print("📦 Initializing SQLite database...")
    init_db()
    print("✅ SQLite database initialized")
    
    # 2. 加载 PyTorch 模型权重
    print("🤖 Loading PyTorch model weights...")
    try:
        import torch
        from app.services.feature_network import FeatureAttentionMixer
        
        # 检查权重文件是否存在
        weights_path = Path("models/feature_mixer.pth")
        if weights_path.exists():
            feature_model = FeatureAttentionMixer()
            feature_model.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
            feature_model.eval()
            # 存储到 app state 供全局访问
            app.state.feature_model = feature_model
            print(f"✅ PyTorch model loaded from {weights_path}")
        else:
            # 使用未训练的模型
            feature_model = FeatureAttentionMixer()
            feature_model.eval()
            app.state.feature_model = feature_model
            print("⚠️  Using untrained PyTorch model (no weights file found)")
    except Exception as e:
        print(f"⚠️  PyTorch model loading skipped: {e}")
        app.state.feature_model = None
    
    # 3. 初始化 ChromaDB 和战术知识库
    print("🔍 Initializing ChromaDB and tactical knowledge base...")
    try:
        from app.services.llm_explainer import TacticalKnowledgeBase
        
        kb = TacticalKnowledgeBase()
        app.state.tactical_kb = kb
        print("✅ Tactical knowledge base initialized")
    except Exception as e:
        print(f"⚠️  Knowledge base initialization skipped: {e}")
        app.state.tactical_kb = None
    
    # 4. 初始化 LLM Explainer Agent
    print("🧠 Initializing LLM Explainer Agent...")
    try:
        from app.services.llm_explainer import MatchExplainerAgent
        
        if settings.USE_LOCAL_MODEL:
            print(f"📡 Using local model: {settings.LOCAL_MODEL_NAME}")
            agent = MatchExplainerAgent(
                model_name=settings.LOCAL_MODEL_NAME,
                api_key=None,
                use_local_model=True
            )
        else:
            api_key = settings.OPENAI_API_KEY or "sk-placeholder-key"
            print(f"☁️  Using ZhipuAI native SDK: model={settings.OPENAI_MODEL}")
            agent = MatchExplainerAgent(
                model_name=settings.OPENAI_MODEL,
                api_key=api_key,
                use_local_model=False
            )
        
        app.state.explainer_agent = agent
        print("✅ LLM Explainer Agent initialized")
    except Exception as e:
        print(f"⚠️  LLM Agent initialization skipped: {e}")
        app.state.explainer_agent = None
    
    # 5. 启动 APScheduler 定时任务调度器
    print("📅 Starting APScheduler...")
    try:
        from app.core.scheduler import start_scheduler
        start_scheduler()
        print("✅ APScheduler started")
    except Exception as e:
        print(f"⚠️  APScheduler startup skipped: {e}")
    
    # 6. 检查外部 API Key 配置状态（仅记录是否已配置，不记录真实值）
    _football_data_ok = bool(os.getenv("FOOTBALL_DATA_API", "").strip())
    _api_football_ok = bool(os.getenv("API_FOOTBALL", "").strip())
    print(
        f"🔑 External API config: "
        f"FOOTBALL_DATA_API={'configured' if _football_data_ok else 'missing'}  "
        f"API_FOOTBALL={'configured' if _api_football_ok else 'missing'}"
    )
    if not _football_data_ok and not _api_football_ok:
        print("⚠️  No external football API key configured — data refresh will use DB cache only")
    
    print("✨ Application startup complete!")
    
    yield  # 应用运行期间
    
    # === 关闭阶段 ===
    print("🛑 Shutting down application...")
    
    # 0. 停止 APScheduler 调度器
    try:
        from app.core.scheduler import stop_scheduler
        stop_scheduler()
        print("✅ APScheduler stopped")
    except Exception as e:
        print(f"⚠️  APScheduler stop skipped: {e}")
    
    # 1. 保存 PyTorch 模型状态（如果需要）
    if hasattr(app.state, 'feature_model') and app.state.feature_model:
        try:
            import torch
            models_dir = Path("models")
            models_dir.mkdir(exist_ok=True)
            torch.save(app.state.feature_model.state_dict(), models_dir / "feature_mixer_latest.pth")
            print("✅ PyTorch model state saved")
        except Exception as e:
            print(f"⚠️  Failed to save model: {e}")
    
    # 2. 关闭数据库连接
    engine.dispose()
    print("✅ Database connection closed")
    
    print("✅ Application shutdown complete")


# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="世界杯冠军预测系统 API - 基于 ELO 评分和机器学习的智能预测",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置 CORS（跨域资源共享）
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router, prefix="/api/v1")


# 根路径健康检查
@app.get("/", tags=["health"])
def root():
    """根路径 - 健康检查"""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


# 健康检查端点
@app.get("/health", tags=["health"])
def health_check():
    """健康检查端点"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
