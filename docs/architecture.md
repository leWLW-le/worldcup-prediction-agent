# V2 架构与代码边界

## 运行入口
`main.py` 仅提供 `main:app` 兼容入口；应用定义、启动释放资源、周期数据刷新与健康检查在 `app/server.py`。只注册 `app/api/v2.py` 路由。旧 `/api/v1/*` 返回 410。

`debug_dashboard.py` 保留原有视觉与交互实现；`dashboard/app.py` 是其兼容启动器。配置读取、HTTP 通信、同进程后端和数据适配分别位于 dashboard 下对应模块。此次整理不搬动 UI 函数或 CSS。

## 职责与调用方向
- API 层验证请求与鉴权，把业务请求交给 pipeline/jobs/coordinator。
- coordinator 只选择五个白名单工具；模型计算与比赛规则不能由 LLM 改写。
- pipeline 调用共用特征、模型 registry 和 tournament；不会从 UI 读取业务状态。
- store 保存不可变输入与结果；jobs 管理计算占用、幂等、取消与完成。
- explanation/service.py 提供无需网络的摘要；explanation/llm.py 调用外部聊天接口、消耗预算并缓存成功结果。
- dashboard 通过 API 获取结果，不自己重新计算冠军概率。

## 三种不同时间语义
1. 训练数据截止：见模型 manifest 和模型卡。
2. 赛前预测快照截止：主页固定为 2026-06-01 的回放输入。
3. 真实赛程抓取时间：数据源最后成功更新的时间。

这三者不能互相替代。赛后抓取到结果，不意味着赛前预测使用了该结果。真实淘汰赛路线来自 provider fixtures，不能回退为代表模拟路径。

## 兼容代码
app 下仍有 V1 agents/services/tools 与旧 API 模块，tests 下仍有历史回归测试。它们不能仅凭目录名判断为生产代码，也不能全部删除。生产入口和上面的调用链是判断依据。

新功能优先添加到 V2 模块；不要把旧 service 的返回 JSON 直接塞进 V2 结果。历史文档入口见 docs/README.md。
