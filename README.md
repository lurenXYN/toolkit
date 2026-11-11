# toolkit

小工具聚合台。第一个工具：**动图 WebP → GIF**（也支持 PNG/JPG、体积上限）。

发布方式与 **market-desk / news-radar** 同构：本仓 `apps/toolkit` 开发 → 同步独立仓 → push GitHub `main` → Actions SSH 部署 VPS。

## 本地启动

依赖：Python 3.10+、ffmpeg

```powershell
cd apps/toolkit
.\start.bat
# 或
.\.venv\Scripts\python.exe -m toolkit serve
```

打开：http://127.0.0.1:8780

- 首页：工具卡片
- 转换器：http://127.0.0.1:8780/tools/media-convert/

## 目录

```
apps/toolkit/
├── toolkit/                 # 平台壳（首页、配置、CLI）
├── tools/media_convert/     # 第一个工具
├── static/                  # 门户 + 工具页
├── deploy/                  # systemd + remote-update + Actions 说明
├── .github/workflows/deploy.yml
├── start.bat / start.sh
└── requirements.txt
```

## 发布流程（独立仓）

1. 开发与验证：`go-learning/apps/toolkit`
2. 同步到：`D:\Source\Repos\toolkit`（排除 `.venv` `__pycache__` `data` `.git`）
3. 在独立仓 commit + `git push origin main`
4. Actions 部署到 VPS：`/opt/toolkit`，健康检查 `:8780/api/health`

详见 [deploy/GITHUB_ACTIONS_DEPLOY.md](deploy/GITHUB_ACTIONS_DEPLOY.md)。

## 输出清理

`data/outputs/media-convert/`：

1. 超过 24 小时删除  
2. 仍超 **100MB** 或 **50 个文件** 时删最旧
