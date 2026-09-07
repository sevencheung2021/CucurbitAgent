# CuAgent 每日文献自动抓取 — systemd timer 部署指南

## 架构

```
每天 03:00 (服务器本地时区)
   ↓ systemd timer 触发
cuagent-daily-fetch.service (oneshot)
   ↓ ExecStart=fetch_and_reload.sh
   ├── ① fetch_yesterday.sh
   │     └── fetch_pubmed_range.py --yesterday
   │         ├── PubMed EUtils API
   │         ├── 物种校验 (17 种葫芦科)
   │         ├── 关键词打 subject 标签 (5 大类)
   │         └── 双写 SQLite + ChromaDB
   └── ② POST /api/literature/reload (热重载, 3 次重试)
   ↓
日志 → journalctl -u cuagent-daily-fetch.service
```

## 部署步骤 (阿里云服务器)

### 1. 配置 `.env`

```bash
# /opt/cuagent/.env
CUAGENT_DATA_ROOT=/data/cuagent
CUAGENT_HOME=/opt/cuagent
CUAGENT_LITERATURE_DB=/data/cuagent/SNP/Cucurbit_Papers_v4.db
CUAGENT_CHROMA_DB=/data/cuagent/SNP/chroma_cucurbit_db_v4
ENTREZ_EMAIL=your_real_email@your-lab.com   # ← NCBI 要求填真实邮箱
ZHIPU_API_KEY=...
```

### 2. 拷贝 systemd 文件

```bash
sudo cp /opt/cuagent/infrastructure/systemd/cuagent-daily-fetch.service /etc/systemd/system/
sudo cp /opt/cuagent/infrastructure/systemd/cuagent-daily-fetch.timer /etc/systemd/system/
```

### 3. 改 service 里的路径 (如果不用 /opt/cuagent)

编辑 `/etc/systemd/system/cuagent-daily-fetch.service`, 改这两行:

```ini
User=www-data                          # ← 改成跑服务的用户
WorkingDirectory=/opt/cuagent          # ← 改成你的项目路径
ExecStart=/opt/cuagent/scripts/fetch_and_reload.sh
```

### 4. 启用 timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cuagent-daily-fetch.timer
```

### 5. 验证

```bash
# 看 timer 状态 (下次触发时间)
systemctl status cuagent-daily-fetch.timer
systemctl list-timers cuagent-daily-fetch.timer

# 立刻手动跑一次 (不等凌晨 3 点)
sudo systemctl start cuagent-daily-fetch.service

# 看抓取日志
journalctl -u cuagent-daily-fetch.service -f
```

## 一次性运维: 把 1760 篇 `other` 论文用 LLM 重新分类

现有的 `subject` 列有 1760 篇是 `other` (关键词分类不够准)。
跑一次 LLM 重分类把它们分到 agri/biomed/food/chem:

```bash
cd /opt/cuagent
source .env
python3 scripts/reclassify_subjects_llm.py
# 支持 --sample N (先跑 N 篇试水) / --dry-run
# 断点续跑: logs/reclassify_progress.jsonl
```

成本估算: 1760 篇 × glm-4.5-air 一次调用 ≈ ¥5-8, 耗时 ~30 分钟。

## 调试 / 常见问题

### Q: 没抓到任何论文?

检查 PubMed API 是否可达, 以及 `ENTREZ_EMAIL` 是否配了真实邮箱:

```bash
journalctl -u cuagent-daily-fetch.service --since today | grep -iE "error|zero|0 papers"
```

### Q: 热重载失败 (Reload attempt failed)?

说明 API 没在跑, 或端口不对。新论文不会立刻显示, 但下次 API 重启后会自动加载。

### Q: 想改成每小时跑一次?

编辑 timer 文件:
```ini
OnCalendar=hourly
# 或每 6 小时
OnCalendar=*-*-* 00/6:00:00
```

### Q: 想临时停掉?

```bash
sudo systemctl stop cuagent-daily-fetch.timer    # 停定时
sudo systemctl disable cuagent-daily-fetch.timer # 开机不自启
```
