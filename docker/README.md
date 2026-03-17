# Docker 部署

适用于单机生产环境，支持两种接入方式：

- 宿主机已有反向代理：`https://<你的域名>/<子路径>` -> `frontend`，`https://<你的域名>/<子路径>/api/v1/*` -> `backend`
- 容器内置 Caddy：`https://<你的域名>` -> `frontend`，`https://<你的域名>/api/v1/*` -> `backend`

## 前置条件

- 域名 `A/AAAA` 记录已指向服务器公网 IP
- 已安装 Docker Engine 与 Docker Compose Plugin
- 如使用容器内置 Caddy，服务器需放行 `80` 和 `443`

如果系统只有旧命令，可将下文的 `docker compose` 替换为 `docker-compose`。

## 配置

```bash
cp backend/.env.example backend/.env
cp docker/compose.env.example .env
```

`backend/.env` 至少填写：

- `JWT_SECRET_KEY`
- `LLM_API_KEYS`
- `LLM_BASE_URL`
- `GEMINI_API_KEYS`
- `ASR_APPID`
- `ASR_API_KEY`

仓库根 `.env` 示例：

```dotenv
APP_DOMAIN=echoes.example.com
APP_BASE_PATH=/echoes
FRONTEND_HOST_PORT=13000
BACKEND_HOST_PORT=18000
PYTHON_BASE_IMAGE=python:3.12-slim
NODE_BASE_IMAGE=node:20-slim
UV_IMAGE=ghcr.io/astral-sh/uv:latest
LETSENCRYPT_EMAIL=ops@example.com
```

`CORS_ORIGINS`、`TRUSTED_HOSTS`、`SESSION_COOKIE_SECURE` 会由 `docker-compose.yml` 按域名自动注入。

`PYTHON_BASE_IMAGE`、`NODE_BASE_IMAGE`、`UV_IMAGE` 是可选项。
默认走官方镜像；如果 Docker Hub / GHCR 在你的网络环境里拉取过慢，可以覆盖为你自己的镜像源。

## 启动

### 1. 宿主机已有 Caddy / Nginx，部署到子路径

如果机器上的 `80/443` 已被现有代理占用，直接启动应用容器：

```bash
mkdir -p data
docker compose up -d --build backend frontend
```

然后把宿主机代理加到现有站点配置里，并把这几条规则放在原有兜底反代之前：

```caddyfile
echoes.example.com {
	encode zstd gzip

	handle_path /echoes/api/v1/* {
		reverse_proxy 127.0.0.1:18000
	}

	handle /echoes/healthz {
		rewrite * /healthz
		reverse_proxy 127.0.0.1:18000
	}

	redir /echoes /echoes/ 308

	handle /echoes/* {
		reverse_proxy 127.0.0.1:13000
	}

	# 其余现有站点规则...
}
```

### 2. 机器没有现成反向代理，直接用容器内置 Caddy

只有在 `80/443` 空闲时，才使用内置 Caddy：

```bash
mkdir -p data
docker compose --profile edge up -d --build
docker compose logs -f caddy
```

## 验证

```bash
curl -I https://echoes.example.com/echoes
curl -I https://echoes.example.com/echoes/healthz
```

返回 `HTTP/2 200` 即表示 HTTPS、反代和后端健康检查都已打通。

## 常用运维命令

```bash
docker compose ps
docker compose logs -f backend frontend
docker compose up -d --build backend frontend
```

## 常见问题

### 1. `docker compose build` 卡在拉基础镜像

如果 `python:3.12-slim`、`node:20-slim` 或 `ghcr.io/astral-sh/uv` 拉取超时，优先给 Docker daemon 配代理：

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf >/dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

如果你更希望直接切换镜像源，也可以在根 `.env` 里覆盖基础镜像，例如：

```dotenv
PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:20-slim
UV_IMAGE=ghcr.io/astral-sh/uv:latest
```

### 2. 前端或后端一直卡在 `health: starting`

- 后端探活依赖 `TRUSTED_HOSTS` 同时放行域名和容器内本地探活地址，当前 compose 已内置这组值。
- 前端容器需要监听 `0.0.0.0:3000`，当前 `frontend/Dockerfile` 已内置 `HOSTNAME=0.0.0.0`。

## 约束

后端当前依赖内存态 session 和 SSE registry，生产环境必须保持单实例，不要对 `backend` 使用 `--scale`。
