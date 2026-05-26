# Azure for Students VM 部署

> 最后核对：2026-05-25。Azure 免费服务和地区 SKU 可用性会变，创建资源前以 Azure Portal 的 Free services、Cost Management 和 Pricing Calculator 为准。

KGTS 已支持单端口部署：前端构建产物、教学 API、维护 API、图谱浏览页和后台页都由根目录 `render_app.py` 托管。VM 上只需要运行一个 Python Web 服务，再由防火墙或 Nginx 暴露到公网。

## 免费规格选择

Azure for Students 当前包含 12 个月内的免费 VM 小规格和 100 美元额度。免费 VM 候选优先级：

| 规格 | 架构 | 资源 | 判断 |
| --- | --- | --- | --- |
| `Standard_B2ats_v2` | AMD x86-64 | 2 vCPU / 1 GB RAM | 首选。CPU 比 `B1s` 更宽裕，保持 x86 兼容。 |
| `Standard_B2pts_v2` | Arm64 | 2 vCPU / 1 GB RAM | 备选。部分 Python/Node 依赖在 Arm 上更容易遇到 wheel 或构建问题。 |
| `Standard_B1s` | x86-64 | 1 vCPU / 1 GB RAM | 最稳妥兼容兜底，但构建和冷启动更慢。 |

KGTS 的完整本地能力，包括神经向量检索和 Genie-TTS，不适合 1 GB 免费 VM。免费 VM 线上部署应使用轻量配置：

```text
KGTS_RETRIEVAL_MODE=sparse_hybrid
KGTS_TTS_ENABLED=0
KGTS_TTS_PROVIDER=disabled
APP_RUN_STARTUP_MAINTENANCE=0
RENDER_AUTO_SYNC_STRUCTURED=0
APP_BOOTSTRAP_SEED_DATA=1
DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0
```

如果要实验本地 TTS，必须把它作为独立服务运行，并让主站使用 `genie_server` 代理。不要在主 `kgts.service` 里直接使用 `KGTS_TTS_PROVIDER=genie`。

## 成本边界

避免意外扣费时重点看这些资源：

- 只创建一个免费 VM 规格，不要同时运行多个免费 VM，否则 750 小时/月会被多台机器累计消耗。
- 使用 64 GB P6 托管磁盘以内；不要额外挂载大磁盘。
- 公网 IPv4 地址可能有单独计费，Basic SKU 已在 2025-09-30 退役。创建前在 Portal 费用预估里确认 Public IP、带宽和磁盘是否仍在免费额度或学生额度内。
- 不要创建 NAT Gateway、Load Balancer、Application Gateway、Azure Firewall 等额外网络资源。
- 部署后在 Cost Management 设置预算告警，建议阈值 1 美元和 5 美元。

如果需要“完全避免 VM 公网 IP 成本”，继续使用 Azure App Service F1 是更合适的公开 Web 部署方式；VM 更适合需要 SSH、后台任务和更可控运行环境的场景。

## Azure CLI 创建流程

下面的命令假设已经安装并登录 Azure CLI，且当前订阅是 Azure for Students。地区优先用 `eastasia` 或 `southeastasia`，如果目标地区没有 `Standard_B2ats_v2` 配额，就切换地区或退回 `Standard_B1s`。

```bash
az login
az account list --output table
az account set --subscription "<Azure for Students subscription id or name>"
```

检查 SKU：

```bash
az vm list-skus \
  --location eastasia \
  --size Standard_B2ats_v2 \
  --all \
  --output table
```

创建资源组和 VM：

```bash
az group create \
  --name kgts-student-rg \
  --location eastasia

az vm create \
  --resource-group kgts-student-rg \
  --name kgts-free-vm \
  --image Ubuntu2204 \
  --size Standard_B2ats_v2 \
  --admin-username azureuser \
  --os-disk-size-gb 64 \
  --storage-sku Premium_LRS \
  --generate-ssh-keys
```

只开放 SSH 和 Web：

```bash
az vm open-port --resource-group kgts-student-rg --name kgts-free-vm --port 22
az vm open-port --resource-group kgts-student-rg --name kgts-free-vm --port 80
```

## VM 内部署 KGTS

SSH 进入 VM 后执行：

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip nodejs npm nginx
```

1 GB 内存构建前端时建议加 swap：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

拉代码并构建：

```bash
git clone https://github.com/mysteriousFourier/Knowledge-Graph-Teaching-System.git kgts
cd kgts
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd frontend
npm ci
NODE_OPTIONS=--max-old-space-size=1536 npm run build
cd ..
```

前端生产构建默认不生成 sourcemap，以降低 1 GB 免费 VM 的构建内存和磁盘压力。如需调试线上 bundle，可临时执行 `VITE_BUILD_SOURCEMAP=1 npm run build`。

创建生产环境配置：

```bash
cat > .env <<'EOF'
APP_BIND_HOST=127.0.0.1
APP_BOOTSTRAP_SEED_DATA=1
APP_RUN_STARTUP_MAINTENANCE=0
RENDER_AUTO_SYNC_STRUCTURED=0
KGTS_RETRIEVAL_MODE=sparse_hybrid
KGTS_TTS_ENABLED=0
KGTS_TTS_PROVIDER=disabled
DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0
DEEPSEEK_API_KEY=
EOF
```

把 `DEEPSEEK_API_KEY` 改成实际值；不要提交 `.env`。

## systemd 服务

```bash
sudo tee /etc/systemd/system/kgts.service >/dev/null <<'EOF'
[Unit]
Description=KGTS single-port web app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/kgts
EnvironmentFile=/home/azureuser/kgts/.env
ExecStart=/home/azureuser/kgts/.venv/bin/python -m uvicorn render_app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kgts
sudo systemctl status kgts --no-pager
```

## Nginx 反向代理

```bash
sudo tee /etc/nginx/sites-available/kgts >/dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 32m;

    location /assets/ {
        root /var/www/kgts;
        try_files $uri =404;
        access_log off;
        expires 1h;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/kgts /etc/nginx/sites-enabled/kgts
sudo nginx -t
sudo systemctl reload nginx
```

验证：

```bash
curl -I http://127.0.0.1:8000/
curl -I http://127.0.0.1/
```

如果由 Nginx 直接服务前端静态资源，把构建产物复制到 Web 可读目录，避免 Nginx 无法遍历 `/home/azureuser`：

```bash
sudo rm -rf /var/www/kgts
sudo mkdir -p /var/www/kgts
sudo cp -a /home/azureuser/kgts/frontend/dist/. /var/www/kgts/
sudo chown -R www-data:www-data /var/www/kgts
```

## 更新部署

以后更新 main 分支：

```bash
cd ~/kgts
git pull --ff-only origin main
. .venv/bin/activate
python -m pip install -r requirements.txt
cd frontend
npm ci
NODE_OPTIONS=--max-old-space-size=1536 npm run build
cd ..
sudo rm -rf /var/www/kgts
sudo mkdir -p /var/www/kgts
sudo cp -a frontend/dist/. /var/www/kgts/
sudo chown -R www-data:www-data /var/www/kgts
sudo systemctl restart kgts
sudo journalctl -u kgts -n 80 --no-pager
```

## 可选：本机 Genie-TTS 代理实验

这不是推荐生产配置，只用于验证 1 GB 免费 VM 是否能承载本地 `shu` TTS。先安装最小中文 Genie 依赖并确认 `models/tts/`、`third_party/Genie-TTS/` 已在 VM 本地存在；这些资产已被 `.gitignore` 排除，不要提交。

主站 `.env` 使用代理模式：

```text
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie_server
KGTS_TTS_SERVER_URL=http://127.0.0.1:9880
KGTS_TTS_GENIE_DATA_DIR=models/tts/GenieData
KGTS_TTS_MODEL_DIR=models/tts/shu
KGTS_TTS_CHARACTER_NAME=shu
KGTS_TTS_LANGUAGE=zh
KGTS_TTS_REFERENCE_AUDIO=models/tts/shu/reference/shu.wav
KGTS_TTS_REFERENCE_LANGUAGE=zh
KGTS_TTS_REFERENCE_TEXT=我是谁？答案只在于我所见所遇的一切。
KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1
KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1
```

创建独立 TTS 服务：

```bash
sudo tee /etc/systemd/system/kgts-tts.service >/dev/null <<'EOF'
[Unit]
Description=KGTS Genie-TTS proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/kgts
EnvironmentFile=/home/azureuser/kgts/.env
Environment=PYTHONPATH=/home/azureuser/kgts:/home/azureuser/kgts/third_party/Genie-TTS/src
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
Environment=NUMEXPR_NUM_THREADS=1
Environment=TOKENIZERS_PARALLELISM=false
Environment=KGTS_TTS_GENIE_LOW_MEMORY=1
Environment=KGTS_TTS_ONNX_CACHE_DIR=/home/azureuser/kgts/.runtime/tts/onnx-fp32-cache
Environment=KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1
Environment=KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1
ExecStart=/home/azureuser/kgts/.venv/bin/python scripts/genie_tts_proxy_server.py
Restart=on-failure
RestartSec=10
OOMPolicy=stop

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kgts-tts
sudo systemctl restart kgts
```

验证：

```bash
curl -s http://127.0.0.1:9880/status
curl -s http://127.0.0.1:8000/api/tts/status
free -h
journalctl -u kgts-tts -n 100 --no-pager
```

`KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1` 会在每次合成后卸载 Genie 角色模型、HuBERT 和引用音频缓存。ONNX Runtime 在 1 GB VM 上不一定把全部内存还给系统，因此更稳的配置是同时开启 `KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1`，让代理在响应发出后退出并由 systemd 拉起一个空闲新进程。代价是每次合成都接近冷启动。

如果合成时出现 OOM，`kgts-tts.service` 会失败或重启，但 `kgts.service` 应继续可用。这说明当前免费 VM 不能稳定承载本地 TTS；可以保留 `genie_server` 配置指向更高内存 VM，或恢复 `KGTS_TTS_ENABLED=0`。

## 官方参考

- Azure for Students: https://azure.microsoft.com/free/students/
- Azure free services: https://azure.microsoft.com/pricing/free-services/
- Create free services: https://learn.microsoft.com/azure/cost-management-billing/manage/create-free-services
- Bv1 sizes: https://learn.microsoft.com/azure/virtual-machines/sizes/general-purpose/bv1-series
- Basv2 sizes: https://learn.microsoft.com/azure/virtual-machines/sizes/general-purpose/basv2-series
- Public IP pricing: https://azure.microsoft.com/pricing/details/ip-addresses/
