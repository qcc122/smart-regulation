FROM python:3.11-slim

WORKDIR /app

# 先复制依赖清单并安装，利用 Docker 层缓存加速后续构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
