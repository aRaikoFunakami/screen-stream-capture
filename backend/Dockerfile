# ---- builder: Python パッケージインストール ----
FROM python:3.13-alpine AS builder

RUN pip install uv

COPY packages/android-screen-stream /app/packages/android-screen-stream
WORKDIR /app/packages/android-screen-stream
RUN uv pip install --system .

COPY backend /app/backend
WORKDIR /app/backend
RUN uv pip install --system .

# ---- runtime ----
FROM python:3.13-alpine

RUN apk add --no-cache ffmpeg android-tools curl

# Python パッケージをビルダーからコピー（uv は含まない）
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /app /app

# scrcpy-server.jar をイメージに含める（存在する場合のみ）
# 開発環境では volume マウントで提供するため不要だが、リリースイメージでは必要
COPY vendor/scrcpy-server.jar* /app/vendor/

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
