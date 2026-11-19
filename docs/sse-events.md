# 聊天流式事件契约

`POST /api/chat/stream` 返回 `text/event-stream`。每帧采用 `data: <JSON>\n\n`；事件按发送顺序处理。同一请求以 `done` 或 `error` 结束，客户端收到终态后停止等待。请求体与 `/api/chat` 相同。

| `type` | 字段 | 含义 |
| --- | --- | --- |
| `node` | `id`, `name`, `status` | 图节点状态；同一任务的开始和结束共用 `id`，`status` 为 `running`、`success` 或 `error`。 |
| `tool` | `id`, `name`, `status` | 工具调用状态；字段同上。不会发送工具参数或密钥。 |
| `sources` | `sources` | 本轮法规引用列表；无结果时为空数组。 |
| `delta` | `content` | 模型正在生成的正文片段，只含文本，不含推理内容或工具参数；此时完整答案尚未校验。 |
| `done` | `session_id`, `answer`, `sources` | 成功终态；`answer` 是完整的权威回答。 |
| `error` | `message` | 失败终态；只返回面向用户的固定错误文本。 |

`node` 和 `tool` 来自 LangGraph 的 `tasks` 流，先发送 `running`，完成后发送 `success` 或 `error`。首次 `delta` 前发送来源列表（尚未检索时为空数组），后续检索可以更新来源。正文通过 v3 `messages` 内容增量实时发送，过滤意图识别、推理和工具参数；无模型增量的固定回答在结束时补发。`done.answer` 是校验后的权威回答，可能替换生成中的草稿，前端必须采用终帧全文。客户端断开时关闭图迭代器。HTTP 状态码仅表示是否建立了流，流内失败由 `error` 表示。

后端在 `app/modules/chat/service.py` 调用 `astream_events(version="v3")`，使用转换器按原始顺序收集父图及子图的任务、引用和状态事件。router 使用 FastAPI 原生 `EventSourceResponse` 自动编码 JSON、发送心跳并处理断连。v3 目前为实验 API，依赖版本已固定。

前端按任务 `id` 配对开始与结束事件，按到达顺序展示实际步骤。耗时是浏览器接收两次事件的时间差，包含网络延迟；终态或用户停止不把未完成节点标为成功。暂停、继续和跳过仅控制页面文字动画，停止会取消 HTTP 流。
