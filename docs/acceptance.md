# Linux 运行验证记录

2026-11-19，用户在 Linux 虚拟机使用本仓库 Compose 完成部署，并反馈问答与文档上传可用，录制了仓库中的演示视频。

## 已验证链路

- PostgreSQL 16、etcd、MinIO、Milvus 2.6.26、FastAPI 与 Nginx 启动，API 与 Milvus 健康检查通过。
- MinerU 解析文档、下载结果，调用智谱 Embedding，将子块写入 Milvus、父块写入 PostgreSQL。
- 初始化脚本成功导入《中华人民共和国建筑法》PDF，并按内容哈希跳过重复文档。
- 法规问答经工具检索、Milvus 内置 SiliconFlow 模型重排、父块展开后返回正文及引用。
- 修复结构化消息被字符串化的问题；模型正文通过 LangGraph v3 SSE 增量返回，终帧携带校验后的完整答案。
- 用户反馈完成直连环境下的提问和上传试用，并提供演示录像。

详细自动化验证范围和命令见 [README](../README.md)。本记录区分用户实机反馈与本地自动化测试，不包含性能基准数字。
