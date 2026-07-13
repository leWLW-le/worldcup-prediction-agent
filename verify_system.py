"""
系统验证脚本

检查所有依赖、模块导入和配置是否正确。
"""

import sys
from pathlib import Path


def check_dependencies():
    """检查依赖包是否安装"""
    print("=" * 80)
    print("📦 检查依赖包")
    print("=" * 80)
    
    required_packages = {
        "fastapi": "FastAPI Web 框架",
        "uvicorn": "ASGI 服务器",
        "sqlalchemy": "数据库 ORM",
        "pydantic": "数据校验",
        "pydantic_settings": "配置管理",
        "torch": "PyTorch 深度学习",
        "langchain_core": "LangChain 核心",
        "langchain_community": "LangChain 社区",
        "chromadb": "向量数据库",
        "openai": "OpenAI API",
        "numpy": "数值计算",
        "scipy": "科学计算",
        "pandas": "数据处理"
    }
    
    missing = []
    for package, description in required_packages.items():
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package:25s} - {description}")
        except ImportError:
            print(f"❌ {package:25s} - {description} (未安装)")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  缺少以下依赖: {', '.join(missing)}")
        print("请运行: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ 所有依赖包已安装")
        return True


def check_project_structure():
    """检查项目结构"""
    print("\n" + "=" * 80)
    print("📁 检查项目结构")
    print("=" * 80)
    
    project_root = Path(__file__).parent
    
    required_files = [
        "main.py",
        "requirements.txt",
        ".env",
        "app/__init__.py",
        "app/main.py",
        "app/core/config.py",
        "app/db/database.py",
        "app/api/routes.py",
        "app/api/simulation.py",
        "app/services/probability_engine.py",
        "app/services/feature_network.py",
        "app/services/llm_explainer.py",
        "app/services/tournament_sim.py",
    ]
    
    missing = []
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✅ {file_path:40s} ({size:,} bytes)")
        else:
            print(f"❌ {file_path:40s} (不存在)")
            missing.append(file_path)
    
    if missing:
        print(f"\n⚠️  缺少以下文件: {', '.join(missing)}")
        return False
    else:
        print("\n✅ 项目结构完整")
        return True


def check_module_imports():
    """检查模块导入"""
    print("\n" + "=" * 80)
    print("🔧 检查模块导入")
    print("=" * 80)
    
    modules_to_check = [
        ("app.core.config", "配置模块"),
        ("app.db.database", "数据库模块"),
        ("app.api.routes", "路由模块"),
        ("app.api.simulation", "模拟接口"),
        ("app.services.probability_engine", "概率引擎"),
        ("app.services.feature_network", "特征网络"),
        ("app.services.llm_explainer", "LLM 解释器"),
        ("app.services.tournament_sim", "锦标赛模拟"),
    ]
    
    failed = []
    for module_name, description in modules_to_check:
        try:
            __import__(module_name)
            print(f"✅ {module_name:40s} - {description}")
        except Exception as e:
            print(f"❌ {module_name:40s} - {description} (导入失败: {e})")
            failed.append(module_name)
    
    if failed:
        print(f"\n⚠️  以下模块导入失败: {', '.join(failed)}")
        return False
    else:
        print("\n✅ 所有模块可正常导入")
        return True


def check_configuration():
    """检查配置"""
    print("\n" + "=" * 80)
    print("⚙️  检查配置")
    print("=" * 80)
    
    try:
        from app.core.config import get_settings
        settings = get_settings()
        
        config_items = {
            "APP_NAME": settings.APP_NAME,
            "APP_VERSION": settings.APP_VERSION,
            "HOST": settings.HOST,
            "PORT": settings.PORT,
            "DATABASE_URL": settings.DATABASE_URL,
            "OPENAI_API_KEY": "已配置" if settings.OPENAI_API_KEY else "未配置（可选）",
        }
        
        for key, value in config_items.items():
            print(f"✅ {key:20s} = {value}")
        
        print("\n✅ 配置加载成功")
        return True
        
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
        return False


def check_database():
    """检查数据库"""
    print("\n" + "=" * 80)
    print("🗄️  检查数据库")
    print("=" * 80)
    
    try:
        from app.db.database import init_db, engine
        
        # 初始化数据库
        init_db()
        
        # 检查数据库文件是否存在
        db_path = Path("worldcup.db")
        if db_path.exists():
            size = db_path.stat().st_size
            print(f"✅ 数据库文件存在 ({size:,} bytes)")
        else:
            print("⚠️  数据库文件尚未创建（将在首次使用时创建）")
        
        print("✅ 数据库连接正常")
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库检查失败: {e}")
        return False


def check_pytorch_model():
    """检查 PyTorch 模型"""
    print("\n" + "=" * 80)
    print("🤖 检查 PyTorch 模型")
    print("=" * 80)
    
    try:
        import torch
        from app.services.feature_network import FeatureAttentionMixer
        
        print(f"✅ PyTorch 版本: {torch.__version__}")
        
        # 创建模型实例
        model = FeatureAttentionMixer()
        param_count = sum(p.numel() for p in model.parameters())
        print(f"✅ 模型参数量: {param_count:,}")
        
        # 检查权重文件
        weights_path = Path("models/feature_mixer.pth")
        if weights_path.exists():
            size = weights_path.stat().st_size
            print(f"✅ 权重文件存在 ({size:,} bytes)")
            
            # 尝试加载
            model.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
            print("✅ 权重加载成功")
        else:
            print("⚠️  权重文件不存在（将使用未训练模型）")
            print("   如需训练模型，请参考 FEATURE_NETWORK_GUIDE.md")
        
        print("✅ PyTorch 模型可用")
        return True
        
    except Exception as e:
        print(f"\n❌ PyTorch 模型检查失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("World Cup Prediction System - 系统验证")
    print("=" * 80)
    print()
    
    # 执行所有检查
    checks = [
        ("依赖包", check_dependencies),
        ("项目结构", check_project_structure),
        ("模块导入", check_module_imports),
        ("配置", check_configuration),
        ("数据库", check_database),
        ("PyTorch 模型", check_pytorch_model),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            success = check_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} 检查异常: {e}")
            results.append((name, False))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 验证结果汇总")
    print("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status:8s} - {name}")
    
    print()
    print(f"总计: {passed}/{total} 项检查通过")
    
    if passed == total:
        print("\n🎉 所有检查通过！系统已准备就绪。")
        print("\n下一步:")
        print("  1. 启动服务器: uvicorn main:app --reload")
        print("  2. 访问 API 文档: http://localhost:8000/docs")
        print("  3. 运行测试: python test_api.py")
        return 0
    else:
        print("\n⚠️  部分检查未通过，请先解决上述问题。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
