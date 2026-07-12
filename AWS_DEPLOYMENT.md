# NeuroTrust-MS AWS EC2 deployment

This deploys the current NeuroTrust-MS prototype on the EC2 instance:

- Public IP: `3.109.202.213`
- SSH user: `ubuntu`
- App path on EC2: `/opt/neurotrust-ms`
- Backend: FastAPI/Uvicorn on `127.0.0.1:8000`
- Frontend: static Vite build served by Nginx
- Public URL: `http://3.109.202.213/`

The hosted demo is configured for:

- maximum 5 validation cases per run
- one validation job at a time
- upload limit 2048 MB per file
- temporary runtime storage under `/var/lib/neurotrust-ms/jobs`
- automatic cleanup after 4 hours
- Nginx basic-auth disabled by default
- in-app email/password gate with per-email password hashes
- login/session/history database stored privately at `/var/lib/neurotrust-ms/access_log.sqlite3`
- server-side session expiry, hashed session tokens, and protected saved validation history
- optional dual-header database audit verification for operators

## 1. Mac Terminal: upload project to EC2

Run this on your Mac, not inside the EC2 terminal:

```bash
rsync -avz --progress \
  -e "ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem" \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".git" \
  --exclude "data" \
  --exclude "backend/data" \
  --exclude "frontend/dist" \
  "/Users/namikhassan/Documents/New project/neurotrust-ms/" \
  ubuntu@3.109.202.213:/home/ubuntu/neurotrust-ms/
```

If this times out, check the EC2 security group allows inbound SSH port `22` from your current IP.

## 2. EC2 Terminal: move project into `/opt`

SSH into EC2:

```bash
ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem ubuntu@3.109.202.213
```

Then run this on EC2:

```bash
sudo rm -rf /opt/neurotrust-ms
sudo mkdir -p /opt
sudo mv /home/ubuntu/neurotrust-ms /opt/neurotrust-ms
sudo chown -R ubuntu:ubuntu /opt/neurotrust-ms
cd /opt/neurotrust-ms
chmod +x deploy/aws/*.sh
```

## 3. EC2 Terminal: first setup

Run:

```bash
cd /opt/neurotrust-ms
./deploy/aws/setup_ec2.sh
```

When it finishes, test:

```bash
curl -i http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1/
```

From your browser, open:

```text
http://3.109.202.213/
```

If the browser cannot open it, check the EC2 security group allows inbound HTTP port `80`.

## 4. Mac + EC2: upload the prepared 5-case demo bundle

The 5-case demo uses the same fields as a real batch upload. Locally, the app reads:

```text
/Users/namikhassan/Downloads/test 1
```

On EC2, place that same bundle here:

```text
/var/lib/neurotrust-ms/demo_data/test_1
```

From Mac Terminal:

```bash
rsync -avz --progress \
  -e "ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem -o IdentitiesOnly=yes" \
  "/Users/namikhassan/Downloads/test 1/" \
  ubuntu@3.109.202.213:/home/ubuntu/neurotrust-test-1/
```

Then on EC2:

```bash
sudo mkdir -p /var/lib/neurotrust-ms/demo_data/test_1
sudo rsync -a --delete /home/ubuntu/neurotrust-test-1/ /var/lib/neurotrust-ms/demo_data/test_1/
sudo chown -R ubuntu:ubuntu /var/lib/neurotrust-ms/demo_data/test_1
sudo sed -i '/^NEUROTRUST_DEMO_BATCH_ROOT=/d' /etc/neurotrust-ms.env
echo 'NEUROTRUST_DEMO_BATCH_ROOT=/var/lib/neurotrust-ms/demo_data/test_1' | sudo tee -a /etc/neurotrust-ms.env
sudo systemctl restart neurotrust-ms
```

Expected field mapping:

- `raw_mris/` → Raw MRIs
- `gts/` → Expert GT masks
- `predictions/` → AI prediction masks
- `expert_2_masks_test_only/` → Second expert masks
- `probability_maps_test_only/` → Probability maps
- `uncertainty_maps_test_only/` → Uncertainty maps
- `freesurfer_subject_files/` → FreeSurfer subject files
- `anatomy_labelmaps_optional/` → Optional fallback anatomy labelmaps
- `metadata/` plus root README/checksum/manifest files → bundle transparency documents

The Research Appendix in the app reports this mapping and each case's actual file pairing after the demo runs.

## 5. EC2 Terminal: optional server-level password

By default, the deployment disables the browser pop-up password prompt. The only normal login is the app email/password screen.

Only run this if you intentionally want an extra Nginx basic-auth prompt before the app loads:

```bash
sudo /opt/neurotrust-ms/deploy/aws/create_basic_auth.sh
```

Use:

- username: `neurotrust`
- password: the password you type when prompted

The app itself also has an email/password access gate. First login with an email creates that email's password record; repeat logins with the same email must use the same password.

## 6. Updating after local code changes

From Mac Terminal:

```bash
rsync -avz --progress \
  -e "ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem" \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".git" \
  --exclude "data" \
  --exclude "backend/data" \
  --exclude "frontend/dist" \
  "/Users/namikhassan/Documents/New project/neurotrust-ms/" \
  ubuntu@3.109.202.213:/home/ubuntu/neurotrust-ms/
```

Then on EC2:

```bash
sudo systemctl stop neurotrust-ms || true
sudo rm -rf /opt/neurotrust-ms
sudo mv /home/ubuntu/neurotrust-ms /opt/neurotrust-ms
sudo chown -R ubuntu:ubuntu /opt/neurotrust-ms
cd /opt/neurotrust-ms
chmod +x deploy/aws/*.sh
./deploy/aws/update_ec2.sh
```

## 7. Monitor and debug

Backend status:

```bash
sudo systemctl status neurotrust-ms --no-pager
```

Backend logs:

```bash
sudo journalctl -u neurotrust-ms -n 120 --no-pager
```

Nginx config test:

```bash
sudo nginx -t
```

Nginx logs:

```bash
sudo tail -n 120 /var/log/nginx/error.log
sudo tail -n 120 /var/log/nginx/access.log
```

Restart:

```bash
sudo systemctl restart neurotrust-ms
sudo systemctl reload nginx
```

Clean expired uploads/results:

```bash
sudo /opt/neurotrust-ms/deploy/aws/cleanup_jobs.sh
```

## 8. Common failures

### `ssh: connect to host 3.109.202.213 port 22: Connection timed out`

You ran the right command, but AWS is blocking SSH. Fix the EC2 security group inbound rule for port `22`.

### `Identity file ... not accessible`

You ran the Mac upload command from inside EC2. The key path `/Users/namikhassan/...` only exists on your Mac.

### `502 Bad Gateway`

Nginx is up but FastAPI is not. Run:

```bash
sudo journalctl -u neurotrust-ms -n 120 --no-pager
```

### Browser cannot open `http://3.109.202.213/`

Usually port `80` is blocked. Add EC2 security group inbound rule:

- Type: HTTP
- Port: 80
- Source: your IP for private demo, or `0.0.0.0/0` if judges need public access

### Upload rejected

Hosted limits are intentional:

- maximum 5 cases per run
- one job at a time
- allowed file types: `.nii`, `.nii.gz`, `.mgz`, `.json`, `.csv`, `.txt`
- max file size: 2048 MB
