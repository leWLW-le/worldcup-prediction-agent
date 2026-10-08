# V2 API 索引

完整参数以运行中的 /docs 与 app/api/v2.py 为准。写接口使用 X-API-Key，值等于 ADMIN_API_KEY；dashboard 通过服务端 BACKEND_API_KEY 提供。

| 方法与路径 | 用途 |
| --- | --- |
| GET /api/v2/tournament-state | 查询赛事快照 |
| GET /api/v2/data/status | 查询数据源状态与真实赛程 |
| POST /api/v2/snapshots | 导入校验后的快照 |
| POST /api/v2/snapshots/{id}/refresh | 刷新数据并形成新快照 |
| POST /api/v2/predictions | 提交预测任务 |
| POST /api/v2/scenarios | 提交晋级假设，与同种子基线对比 |
| GET /api/v2/jobs/{id} | 查询任务 |
| DELETE /api/v2/jobs/{id} | 请求取消任务 |
| GET /api/v2/results | 查询保存结果，可按 snapshot_id 筛选 |
| GET /api/v2/results/{id} | 完整结果 |
| GET /api/v2/results/{id}/explanation | 无外部调用的确定性摘要 |
| POST /api/v2/results/{id}/explanation | 鉴权后生成或读取缓存 LLM 解读；失败返回明确降级 |
| POST /api/v2/compare | 对比历史记录 |
| POST /api/v2/coordinator | LLM 五工具工作流 |

预测请求示例：
```json
{"snapshot_id":"替换为实际快照ID","simulation_count":2000,"seed":42}
```
预测提交为异步任务接口；协调器当前仍同步等待工具。不要在收到忙或超时后不断重复提交。公开读取接口只适合公开赛事信息。

解读的 source=llm 表示生成结果来自 LLM（可能命中缓存），不是每次访问都实时调用；source=template 表示摘要，fallback_reason 说明降级。概率字段始终来自原结果。
