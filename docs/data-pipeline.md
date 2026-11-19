# 文档数据清理与初始化

这些命令从项目根目录运行，并读取当前 `.env` 配置。

## 从空知识库开始

确认当前配置指向本项目后，运行：

```bash
python -m scripts.reset_knowledge_base --confirm
```

命令只会删除配置的 Milvus database 下的目标 collection、PostgreSQL 的 `rag_documents` / `rag_parent_chunks` 两张项目表中的记录，以及 `DATA_DIR/uploads` 中按文档 ID 命名的上传副本。它不会删除 PostgreSQL database、其它表、Milvus database、原始本地文档或 Docker volumes。

`--confirm` 是必需参数；不带该参数时命令只显示清理范围并退出。

## 导入本地文档

```bash
python -m scripts.init_documents /path/to/regulations
```

脚本递归扫描目录中的 PDF 和 DOCX，逐份调用与上传 API 相同的 MinerU → Markdown 切分 → PostgreSQL/Milvus pipeline。相同 SHA-256 的已入库文档会跳过；单份文档失败不会阻断其余文件。原始文件留在指定目录，不会被移动或删除。

运行需要 `MINERU_TOKEN`、`ZHIPU_API_KEY`、`POSTGRES_PASSWORD` 和正确的 PostgreSQL/Milvus 连接配置。命令结束时会报告新增、跳过和失败数量；有失败文件时返回非零退出码。
