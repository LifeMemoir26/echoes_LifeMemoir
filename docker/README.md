# Docker 部署

适用于单机 `docker compose + Caddy` 的生产部署：

- `https://<你的域名>` -> `frontend`
- `https://<你的域名>/api/v1/*` -> `backend`
- Caddy 自动申请并续期 HTTPS 证书

## 前置条件

- 域名 `A/AAAA` 记录已指向服务器公网 IP
- 服务器已放行 `80` 和 `443`
- 已安装 Docker Engine 与 Docker Compose Plugin

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

仓库根 `.env` 填写：

```dotenv
APP_DOMAIN=echoes.example.com
LETSENCRYPT_EMAIL=ops@example.com
```

`CORS_ORIGINS`、`TRUSTED_HOSTS`、`SESSION_COOKIE_SECURE` 会由 `docker-compose.yml` 按域名自动注入。

## 启动

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f caddy
```

## 验证

```bash
curl -I https://echoes.example.com/healthz
```

返回 `HTTP/2 200` 即表示 HTTPS、反代和后端健康检查都已打通。

## 约束

后端当前依赖内存态 session 和 SSE registry，生产环境必须保持单实例，不要对 `backend` 使用 `--scale`。
