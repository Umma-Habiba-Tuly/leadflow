# Deploying LeadFlow to a VPS

Target: one Ubuntu VPS that already runs a Caddy reverse proxy (80/443), one domain (`app.atsync.tech`), data in Postgres.
LeadFlow does not run its own Caddy: it publishes web (3100) and api (8100) on the Docker bridge address only,
and the existing Caddy proxies to them (see `Caddyfile.snippet`). A server with nothing on 80/443 needs a Caddy added first.

> **Status: written but not yet run.** Docker is not installed on the development machine, so none of this
> has been built or started. Expect to fix small things on the first deploy. Backend tests ran on SQLite;
> the migrations have not yet run on Postgres.

## 1. DNS (in Hostinger hPanel → Domains → atsync.tech → DNS)
Add an **A record**: name `app`, value = the VPS IP. Wait until `dig +short app.atsync.tech` shows that IP.
Caddy cannot get a certificate before this works.

## 2. Server prep (only the parts a shared server needs)
Do NOT re-run firewall or SSH hardening on a server that already hosts other services.
```bash
# Swap, so `next build` does not get OOM-killed on a 4 GB machine (safe, additive)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
# Let the existing Caddy (on the Docker bridge range) reach LeadFlow's two local ports. Nothing else opens.
ufw allow from 172.16.0.0/12 to any port 3100 proto tcp
ufw allow from 172.16.0.0/12 to any port 8100 proto tcp
```

## 3. Get the code on the server
```bash
git clone https://github.com/Umma-Habiba-Tuly/leadflow.git /opt/leadflow && cd /opt/leadflow
```

## 4. Secrets
```bash
cd /opt/leadflow && cp deploy/.env.production.example deploy/.env.production && chmod 600 deploy/.env.production
nano deploy/.env.production      # fill every empty value (the file explains how to generate each)
```
Save `ENCRYPTION_KEY` in a password manager as well. It is not in the backups.

## 5. Start
```bash
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml logs -f api   # migrations should say "Running upgrade"
```
Then add the block from `Caddyfile.snippet` to the existing Caddyfile (back it up first), validate, and reload:
```bash
cp /home/tuly/n8n/Caddyfile /home/tuly/n8n/Caddyfile.bak-$(date +%F)
cat deploy/Caddyfile.snippet >> /home/tuly/n8n/Caddyfile      # append in place: the file is bind-mounted
docker exec caddy caddy validate --config /etc/caddy/Caddyfile && docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```
Open `https://app.atsync.tech`, register, and the first workspace exists.

## 6. Backups
```bash
crontab -e
15 3 * * * cd /opt/leadflow && ./deploy/backup.sh >> /root/backup.log 2>&1
```
Copy the backup folder off the server now and then. A backup on the same disk dies with the disk.
Restore: `gunzip -c file.sql.gz | docker compose ... exec -T db psql -U leadflow leadflow`.

## 7. Updating
`git pull`, then the `up -d --build` command. Migrations run automatically on api start.

## Before real clients
- Send cold email from a **separate domain**, never from `atsync.tech` (a spam flag would hit your main mail).
- The free Gemini tier may use prompts to improve Google's products. Use a paid key before client data goes in.
- Set up SPF/DKIM/DMARC on the sending domain.
