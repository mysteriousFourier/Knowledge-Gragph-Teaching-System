#!/usr/bin/env bash
set -euo pipefail

KGTS_DIR="${KGTS_DIR:-/home/azureuser/kgts}"
KGTS_USER="${KGTS_USER:-azureuser}"
SERVICE_PATH="/etc/systemd/system/kgts-tts.service"

if [ ! -d "$KGTS_DIR" ]; then
  echo "KGTS_DIR does not exist: $KGTS_DIR" >&2
  exit 1
fi

cd "$KGTS_DIR"

if [ ! -f ".env" ]; then
  echo ".env is missing in $KGTS_DIR" >&2
  exit 1
fi

set_env_var() {
  local name="$1"
  local value="$2"
  if grep -qE "^${name}=" .env; then
    sed -i "s#^${name}=.*#${name}=${value}#" .env
  else
    printf '\n%s=%s\n' "$name" "$value" >> .env
  fi
}

set_env_var "KGTS_TTS_ENABLED" "1"
set_env_var "KGTS_TTS_PROVIDER" "genie_server"
set_env_var "KGTS_TTS_SERVER_URL" "http://127.0.0.1:9880"
set_env_var "KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH" "1"
set_env_var "KGTS_TTS_PROXY_EXIT_AFTER_SYNTH" "1"

missing=0
for path in \
  ".venv/bin/python" \
  "scripts/genie_tts_proxy_server.py" \
  "third_party/Genie-TTS/src/genie_tts" \
  "models/tts/GenieData" \
  "models/tts/shu" \
  "models/tts/shu/reference/shu.wav"
do
  if [ ! -e "$path" ]; then
    echo "Missing required TTS path: $KGTS_DIR/$path" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "TTS proxy service was not modified because required local TTS assets are incomplete." >&2
  exit 2
fi

sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=KGTS Genie-TTS proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$KGTS_USER
WorkingDirectory=$KGTS_DIR
EnvironmentFile=$KGTS_DIR/.env
Environment=PYTHONPATH=$KGTS_DIR:$KGTS_DIR/third_party/Genie-TTS/src
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
Environment=NUMEXPR_NUM_THREADS=1
Environment=TOKENIZERS_PARALLELISM=false
Environment=KGTS_TTS_GENIE_LOW_MEMORY=1
Environment=KGTS_TTS_ONNX_CACHE_DIR=$KGTS_DIR/.runtime/tts/onnx-fp32-cache
Environment=KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1
Environment=KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1
ExecStart=$KGTS_DIR/.venv/bin/python scripts/genie_tts_proxy_server.py
Restart=always
RestartSec=2
OOMPolicy=stop

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable kgts-tts
sudo systemctl restart kgts-tts
sleep 3

if ! curl -fsS --max-time 10 http://127.0.0.1:9880/status; then
  echo
  echo "kgts-tts did not become reachable. Recent service status and logs follow:" >&2
  sudo systemctl status kgts-tts --no-pager || true
  sudo journalctl -u kgts-tts -n 80 --no-pager || true
  exit 3
fi

sudo systemctl restart kgts
sleep 2

echo
echo "Main app TTS status:"
curl -fsS --max-time 10 http://127.0.0.1:8000/api/tts/status
echo
