FROM python:3.13-slim

WORKDIR /app

# システム依存関係
RUN apt-get update && apt-get install -y \
    android-tools-adb \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv をインストール
RUN pip install uv

# Python ライブラリをインストール（editable install）
COPY packages/android-screen-stream /app/packages/android-screen-stream
WORKDIR /app/packages/android-screen-stream
RUN uv pip install --system -e .

# 公式バックエンドをインストール
COPY backend /app/backend
WORKDIR /app/backend
RUN uv pip install --system -e .

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
