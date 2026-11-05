# Deployment (Oracle Cloud Always Free + Docker + Caddy)

```
Internet ──HTTPS──▶ Caddy (:443, auto Let's Encrypt) ──▶ app (FastAPI + UI, :8000, private)
                                                         └── volume: SQLite + MP3s
```

## 1. Create the server (Oracle Cloud)
1. Sign up at cloud.oracle.com and pick a **home region** close to Israel (e.g. Frankfurt or Amsterdam).
   Home region can't be changed later.
2. **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 24.04** (aarch64)
   - Shape: **Ampere → VM.Standard.A1.Flex**, 1 OCPU / 6 GB (well within Always Free)
   - Networking: keep "Assign a public IPv4 address"
   - SSH keys: **Generate a key pair for me** → download the private key
   - If you get *Out of capacity*: try another availability domain or retry later.
3. Open the web ports: **Instance → Subnet → Default Security List → Add Ingress Rules**
   - Source `0.0.0.0/0`, TCP, destination port `80`
   - Source `0.0.0.0/0`, TCP, destination port `443`
4. Recommended: upgrade the account to **Pay As You Go**. Always Free resources stay free,
   and idle Always Free instances are no longer at risk of being reclaimed.
   Set a budget alert at $1 (Billing → Budgets).

## 2. Free domain (DuckDNS)
1. Log in at duckdns.org, create a subdomain (e.g. `oshri-reader`).
2. Set its IP to the instance's **public IP**.

## 3. Prepare the server
```bash
ssh -i path/to/private.key ubuntu@<PUBLIC_IP>

# Ubuntu images on Oracle block ports in iptables too, not only in the security list
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # log out and back in so the group change applies
```

## 4. Deploy
```bash
ssh -i path/to/private.key ubuntu@<PUBLIC_IP>
git clone https://github.com/<you>/hebrew-reader.git
cd hebrew-reader
cp .env.example .env
nano .env          # fill in Azure key, APP_TOKEN, FEED_TOKEN, DOMAIN, PUBLIC_URL
chmod 600 .env     # only your user can read the secrets
docker compose up -d --build
docker compose logs -f   # Ctrl+C to stop watching
```
Open `https://<DOMAIN>`. The first load can take ~30s while Caddy gets the certificate.

## 5. Updating
```bash
cd hebrew-reader && git pull && docker compose up -d --build
```

## 6. Backup
```bash
docker run --rm -v hebrew-reader_appdata:/data -v "$PWD":/backup alpine \
  tar czf /backup/backup-$(date +%F).tgz -C /data .
```

## Podcast feed (optional, best for driving)
Subscribe once to `https://<DOMAIN>/feed/<FEED_TOKEN>/podcast.xml`:
- **iPhone:** Apple Podcasts → Library → ⋯ → *Follow a Show by URL*
- **Android:** AntennaPod or Pocket Casts → add podcast by URL

New articles appear as episodes automatically. CarPlay / Android Auto work out of the box.
Spotify does not support private feeds.
