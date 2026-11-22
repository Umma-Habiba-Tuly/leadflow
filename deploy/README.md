# Deploying LeadFlow to a VPS

Target: one Ubuntu VPS, one domain (`app.atsync.tech`), HTTPS by Caddy, data in Postgres.

> **Status: written but not yet run.** Docker is not installed on the development machine, so none of this
> has been built or started. Expect to fix small things on the first deploy. Backend tests ran on SQLite;
> the migrations have not yet run on Postgres.

## 1. DNS (in Hostinger hPanel → Domains → atsync.tech → DNS)
Add an **A record**: name `app`, value = the VPS IP. Wait until `dig +short app.atsync.tech` shows that IP.
Caddy cannot get a certificate before this works.

## 2. Server basics (once, as root)
```bash
adduser deploy && usermod -aG sudo deploy          # work as a normal user, not root
# copy your SSH public key to /home/deploy/.ssh/authorized_keys, then test login as deploy
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```
Then disable password login in `/etc/ssh/sshd_config` (`PasswordAuthentication no`) and `systemctl restart ssh`.
Do this only after the key login works, or you lock yourself out.

## 3. Put the code on the server
```bash
# from your laptop (excludes secrets, venv, node_modules, dev database)
rsync -az --exclude .venv --exclude node_modules --exclude .next --exclude .next-e2e \
  --exclude '*.db' --exclude .env ./ deploy@SERVER_IP:~/leadflow/
```

## 4. Secrets
```bash
cd ~/leadflow && cp deploy/.env.production.example deploy/.env.production && chmod 600 deploy/.env.production
nano deploy/.env.production      # fill every empty value (the file explains how to generate each)
```
Save `ENCRYPTION_KEY` in a password manager as well. It is not in the backups.

## 5. Start
```bash
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml logs -f api   # migrations should say "Running upgrade"
```
Open `https://app.atsync.tech`, register, and the first workspace exists.

## 6. Backups
```bash
crontab -e
15 3 * * * cd /home/deploy/leadflow && ./deploy/backup.sh >> /home/deploy/backup.log 2>&1
```
Copy the backup folder off the server now and then. A backup on the same disk dies with the disk.
Restore: `gunzip -c file.sql.gz | docker compose ... exec -T db psql -U leadflow leadflow`.

## 7. Updating
Re-run the rsync, then the `up -d --build` command. Migrations run automatically on api start.

## Before real clients
- Send cold email from a **separate domain**, never from `atsync.tech` (a spam flag would hit your main mail).
- The free Gemini tier may use prompts to improve Google's products. Use a paid key before client data goes in.
- Set up SPF/DKIM/DMARC on the sending domain.
