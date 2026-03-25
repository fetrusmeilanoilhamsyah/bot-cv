# DiBot CV (VCF Telegram Bot)

A high-performance Telegram bot built with Python for converting, managing, and merging VCF (vCard) and TXT contacts. Designed with concurrency and disk-backed caching to accommodate high-traffic loads and large file processing without memory exhaustion.

## Features

* **Contact Management**: Convert TXT to VCF, VCF to TXT, and split or merge large VCF files.
* **Bulk Processing**: Rapidly counts and processes millions of contacts using background workers (`ThreadPoolExecutor`).
* **Session Safety**: Disk-based temporary sessions prevent Out-Of-Memory (OOM) crashes.
* **Smart Concurrency**: connection pooling and `concurrent_updates` tuned for 50-100 simultaneous users.
* **VIP & Membership**: Integrated membership system with SQLite WAL mode.
* **Automated Maintenance**: Auto-cleans expired cache and stale sessions via APScheduler.

## Prerequisites

* Python 3.10 or higher
* Telegram Bot Token (from BotFather)
* VPS (Minimum 1 vCPU, 1GB RAM) or Local PC for testing

## Installation & Localhost Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/fetrusmeilanoilhamsyah/bot-cv.git
   cd bot-cv
   ```

2. **Set up Virtual Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Copy the example config and edit it with your credentials:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in `BOT_TOKEN`, `ADMIN_IDS`, `ADMIN_CONTACT`, etc.

5. **Run the Bot:**
   ```bash
   python main.py
   ```

## VPS Deployment Guide (Linux)

To keep the bot running 24/7 on a VPS, use `systemd` or `pm2`. Below is a standard `systemd` configuration:

1. Copy the project to your VPS (e.g., `/var/www/bot-cv`).
2. Create a service file: `sudo nano /etc/systemd/system/botcv.service`
3. Add the following configuration:
   ```ini
   [Unit]
   Description=DiBot CV Telegram Bot
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/var/www/bot-cv
   ExecStart=/var/www/bot-cv/.venv/bin/python main.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
4. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start botcv
   sudo systemctl enable botcv
   ```

## Dummy Data Cleanup

Before deploying to production, ensure you wipe all local testing sessions and temporary SQLite databases. Run:
```bash
python clean_dummy_data.py
```

## License

Copyright (c) 2026 Fetrus Meilano Ilhamsyah

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.