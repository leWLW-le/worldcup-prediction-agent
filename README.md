# World Cup Prediction API

基于 FastAPI 的世界杯冠军预测系统后端服务。

## 📁 项目结构

```
worldcup/
├── app/
│   ├── api/              # API 路由层
│   │   ├── teams.py      # 球队管理接口
│   │   ├── predictions.py # 预测相关接口
│   │   └── routes.py     # 路由注册
│   ├── core/             # 核心配置
│   │   └── config.py     # 应用配置
│   ├── models/           # 数据模型
│   │   ├── schemas.py    # SQLAlchemy ORM 模型
│   │   └── pydantic_models.py # Pydantic 验证模型
│   ├── services/         # 业务逻辑层
│   │   └── prediction_service.py # 预测服务
│   ├── db/               # 数据库层
│   │   └── database.py   # 数据库连接
│   └── data/             # 数据文件目录
├── main.py               # 应用入口
├── init_data.py          # 数据初始化脚本
├── requirements.txt      # 依赖包
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库和示例数据

```bash
python init_data.py
```

### 3. 启动服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🎯 核心功能

### API 端点

#### 球队管理
- `GET /api/v1/teams/` - 获取所有球队
- `GET /api/v1/teams/{team_id}` - 获取单个球队
- `POST /api/v1/teams/` - 创建新球队
- `DELETE /api/v1/teams/{team_id}` - 删除球队

#### 预测功能
- `POST /api/v1/predictions/tournament` - 预测整个锦标赛
- `POST /api/v1/predictions/match/{match_id}` - 预测单场比赛
- `GET /api/v1/predictions/match/{match_id}` - 获取比赛预测结果
- `DELETE /api/v1/predictions/{prediction_id}` - 删除预测结果

### 预测模型

当前实现了基于 **ELO 评分系统**的预测算法：

- 考虑球队实力差异（ELO 评分）
- 包含主场优势加成（+100 分）
- 使用泊松分布生成比分
- 计算预测置信度
- 提供可解释的推理依据

## 🛠️ 技术栈

- **FastAPI** - 高性能 Web 框架
- **SQLAlchemy** - ORM 数据库工具
- **Pydantic** - 数据验证
- **Pandas** - 数据处理
- **SciPy** - 科学计算
- **Uvicorn** - ASGI 服务器

## 📝 开发规范

- 严格使用 Python 3.10+ 类型注解
- 遵循 PEP 8 代码规范
- 使用异步编程模式（lifespan）
- 依赖注入模式（FastAPI Depends）

## 🔧 配置说明

通过环境变量或 `.env` 文件配置：

```env
APP_NAME=World Cup Prediction API
APP_VERSION=1.0.0
DEBUG=False
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:///./worldcup.db
DATA_DIR=app/data
PREDICTION_MODEL_PATH=app/data/models
```

## 📈 后续扩展方向

1. **数据采集模块** - 接入 FIFA API 或网页抓取
2. **机器学习模型** - 集成更复杂的预测算法
3. **可视化前端** - 赛程树和对阵图展示
4. **历史数据分析** - 往届世界杯数据挖掘
5. **实时预测更新** - 根据比赛进程动态调整

## 📄 许可证

MIT License
