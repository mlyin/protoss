# Arena: API + sandbox + built leaderboard UI in one container.
#   docker build -t arena . && docker run -p 8000:8000 -e ARENA_MODE=sim -e ADMIN_TOKEN=change-me arena
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install --silent
COPY web/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
COPY sdk sdk
RUN pip install -e ./backend -e ./sdk
COPY --from=web /web/dist web/dist
COPY agents agents
COPY scripts scripts
COPY fleet.yaml .
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
