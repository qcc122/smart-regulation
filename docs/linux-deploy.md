# Linux 全栈部署

仓库根目录的 `docker-compose.yml` 同时定义 PostgreSQL 16、etcd、MinIO、Milvus 2.6.26、FastAPI、前端构建任务和 Nginx。数据库、对象存储、Milvus、上传文件和前端产物各有独立的 Compose 命名卷。后端使用 Python 3.14 基础镜像，在容器启动时安装 `requirements.txt`，不使用旧 Dockerfile。

## 首次启动

1. 将仓库复制到 Linux 虚拟机，进入仓库根目录。
2. 将已填好的本地 `.env` 一并复制到项目根目录；只有缺少 `.env` 时才执行 `cp .env.example .env` 并填写配置。当前数据库为 `smart_regulation`，用户为 `regulation_app`；密码从 `.env` 注入。不要用模板覆盖已填写的 API Key。
   智谱网页搜索 MCP 复用 `ZHIPU_API_KEY`。
   SiliconFlow 重排由 Milvus 服务执行，Compose 将 `SILICONFLOW_API_KEY` 注入 Milvus 的 `MILVUS_SILICONFLOW_API_KEY`；Function 不传原始 Key 作为 `credential`（该参数是服务端凭据名称）。更换该 Key 后需重新创建 Milvus 容器，使环境变量生效。
   如 pip/npm 在虚拟机内需走 Windows 代理，在 `.env` 中填写 `HTTP_PROXY`、`HTTPS_PROXY`，地址使用虚拟机可访问的宿主机地址。
3. 旧的 `~/deploy` Compose 若仍占用 5432、9000、9001、19530 或 9091 端口，先在旧目录执行 `docker compose down`。不要加 `-v`；新项目使用不同的命名卷，从空业务数据启动。
4. 在本仓库目录执行 `docker compose config --quiet`，然后执行 `docker compose up -d`。
5. 执行 `docker compose ps`，确认 `postgres`、`etcd`、`minio`、`milvus`、`api` 和 `nginx` 已就绪，`web-build` 成功退出。浏览器访问 `http://<虚拟机 IP>:8080`。

`api` 容器首次启动要安装 Python 依赖，`web-build` 会执行 `npm ci` 和前端构建，首次启动需要能访问对应包仓库。Milvus 镜像已在虚拟机下载；其余镜像仍可能需要下载。

## 查看状态

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 milvus
```

上传副本保存在 `app_data`，PostgreSQL 表和 LangGraph checkpoint 保存在 `postgres_data`，Milvus 元数据、对象和本地数据分别保存在 `etcd_data`、`minio_data` 和 `milvus_data`。停止服务使用 `docker compose down`，下次 `docker compose up -d` 会继续使用这些卷。

PostgreSQL 的初始化账户和数据库只在空卷首次启动时创建，修改 `.env` 不会修改已有卷内的账户密码。首次重部署请确认使用本项目的独立新卷。

## 联调与重启验收

启动后按 [验收清单](acceptance.md) 检查真实文档、流式问答、引用和会话恢复。SSE 已采用 LangGraph v3，正文随模型生成逐段发送，最后以校验后的完整答案校正。前端上传请求和 Nginx 等待后端响应的时间均为 10 分钟；文件大小限制仍是 20 MiB。
