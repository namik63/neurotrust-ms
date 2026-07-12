# NeuroTrust-MS Ubuntu deployment

This guide describes a generic Ubuntu/Nginx deployment for NeuroTrust-MS.

Runtime layout:

- app path: `/opt/neurotrust-ms`
- backend: FastAPI/Uvicorn on `127.0.0.1:8000`
- frontend: static Vite build served by Nginx
- runtime data: `/var/lib/neurotrust-ms`
- prepared demo data: `/var/lib/neurotrust-ms/demo_data/test_1`
- access/history database: `/var/lib/neurotrust-ms/access_log.sqlite3`

Hosted defaults:

- maximum 5 validation cases per run;
- one validation job at a time;
- 2048 MB upload limit;
- temporary job cleanup after 4 hours;
- server-level basic auth disabled by default;
- app-level email/password login enabled.

## 1. Upload the project

Run this from your local machine, replacing the placeholders:

```bash
rsync -avz --progress \
  -e "ssh -i <PATH_TO_KEY.pem> -o IdentitiesOnly=yes" \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".git" \
  --exclude "data" \
  --exclude "backend/data" \
  --exclude "frontend/dist" \
  "<LOCAL_NEUROTRUST_MS_FOLDER>/" \
  ubuntu@<SERVER_PUBLIC_IP>:/home/ubuntu/neurotrust-ms/
```

## 2. Move the project into `/opt`

SSH into the server:

```bash
ssh -i <PATH_TO_KEY.pem> ubuntu@<SERVER_PUBLIC_IP>
```

Then run:

```bash
sudo rm -rf /opt/neurotrust-ms
sudo mkdir -p /opt
sudo mv /home/ubuntu/neurotrust-ms /opt/neurotrust-ms
sudo chown -R ubuntu:ubuntu /opt/neurotrust-ms
cd /opt/neurotrust-ms
chmod +x deploy/aws/*.sh
```

## 3. First setup

Set the public origin for the server, then run setup:

```bash
cd /opt/neurotrust-ms
PUBLIC_ORIGIN="http://<SERVER_PUBLIC_IP>" ./deploy/aws/setup_ec2.sh
```

Test locally on the server:

```bash
curl -i http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1/
```

Open in a browser:

```text
http://<SERVER_PUBLIC_IP>/
```

If the browser cannot open the site, confirm that inbound HTTP port `80` is allowed by the server firewall or cloud security group.

## 4. Upload the prepared 5-case demo bundle

The prepared demo bundle should be placed at:

```text
/var/lib/neurotrust-ms/demo_data/test_1
```

Expected bundle layout:

```text
test_1/
  raw_mris/
  gts/
  predictions/
  expert_2_masks_test_only/
  probability_maps_test_only/
  uncertainty_maps_test_only/
  freesurfer_subject_files/
  anatomy_labelmaps_optional/
  metadata/
```

Upload from your local machine:

```bash
rsync -avz --progress \
  -e "ssh -i <PATH_TO_KEY.pem> -o IdentitiesOnly=yes" \
  "<LOCAL_TEST_1_FOLDER>/" \
  ubuntu@<SERVER_PUBLIC_IP>:/home/ubuntu/neurotrust-test-1/
```

Install it on the server:

```bash
sudo mkdir -p /var/lib/neurotrust-ms/demo_data/test_1
sudo rsync -a --delete /home/ubuntu/neurotrust-test-1/ /var/lib/neurotrust-ms/demo_data/test_1/
sudo chown -R ubuntu:ubuntu /var/lib/neurotrust-ms/demo_data/test_1
sudo sed -i '/^NEUROTRUST_DEMO_BATCH_ROOT=/d' /etc/neurotrust-ms.env
echo 'NEUROTRUST_DEMO_BATCH_ROOT=/var/lib/neurotrust-ms/demo_data/test_1' | sudo tee -a /etc/neurotrust-ms.env
sudo systemctl restart neurotrust-ms
```

Field mapping used by the app:

- `raw_mris/` -> Raw MRIs
- `gts/` -> Expert GT masks
- `predictions/` -> Prediction masks
- `expert_2_masks_test_only/` -> Second expert masks
- `probability_maps_test_only/` -> Probability maps
- `uncertainty_maps_test_only/` -> Uncertainty maps
- `freesurfer_subject_files/` -> FreeSurfer subject files
- `anatomy_labelmaps_optional/` -> Optional fallback anatomy labelmaps
- `metadata/` -> bundle metadata

The Research Appendix reports this mapping after the demo runs.

## 5. Optional server-level password

By default, the deployment does not add a browser-level password prompt. The app uses its own email/password gate.

To add an additional Nginx basic-auth prompt:

```bash
sudo /opt/neurotrust-ms/deploy/aws/create_basic_auth.sh
```

## 6. Updating after code changes

Upload the project again:

```bash
rsync -avz --progress \
  -e "ssh -i <PATH_TO_KEY.pem> -o IdentitiesOnly=yes" \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".git" \
  --exclude "data" \
  --exclude "backend/data" \
  --exclude "frontend/dist" \
  "<LOCAL_NEUROTRUST_MS_FOLDER>/" \
  ubuntu@<SERVER_PUBLIC_IP>:/home/ubuntu/neurotrust-ms/
```

Then run on the server:

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

### SSH timeout

The server is not reachable on port `22`. Check the firewall or cloud security-group rule.

### Identity file not accessible

The private key path is wrong or the upload command is being run from the wrong machine.

### 502 Bad Gateway

Nginx is running but the FastAPI service is not healthy:

```bash
sudo journalctl -u neurotrust-ms -n 120 --no-pager
```

### Browser cannot open the site

Check inbound HTTP port `80`.

### Upload rejected

Hosted limits are intentional:

- maximum 5 cases per run;
- one job at a time;
- allowed file types: `.nii`, `.nii.gz`, `.mgz`, `.json`, `.csv`, `.txt`;
- max file size: 2048 MB.
