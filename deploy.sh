#!/bin/bash
# deploy.sh - Auto Update & Restart DiBot CV

echo "🚀 Memulai Deployment Antigravity..."

# 1. Pull perubahan terbaru
git pull origin main

# 2. Update dependencies (optional)
# source .venv/bin/activate
# pip install -r requirements.txt

# 3. Cari PID bot yang lama lalu matikan
PID=$(pgrep -f "python3 main.py")
if [ -z "$PID" ]; then
    echo "ℹ️ Bot tidak sedang berjalan."
else
    echo "Stopping bot (PID: $PID)..."
    kill $PID
    sleep 2
fi

# 4. Jalankan bot di background (pake nohup atau screen/tmux)
echo "Starting bot..."
nohup python3 main.py > logs/nohup.log 2>&1 &

echo "✅ Deployment Berhasil Bang! Bot sudah jalan di background."
