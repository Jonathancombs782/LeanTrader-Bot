
# LeanTrader — Production Stack (Docker)

This stack runs **API + Agents + Redis + Postgres + Nginx TLS**.

## Launch
```bash
cd deploy
docker compose -f docker-compose.full.yml up --build -d
```
- Put TLS certs in `deploy/nginx/certs/fullchain.pem` and `privkey.pem`.
- API will be served through Nginx on ports **80/443**.

## ENV
Edit `../.env` (copy from `.env.example`) for tokens, broker mode, and database.

## Optional: Let’s Encrypt (future)
Add a companion like `nginxproxy/acme-companion` or Caddy for automated certs.
