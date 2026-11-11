# GitHub Actions 自动部署（与 market-desk 同构）

push `main`（或手动 Run workflow）后，GitHub Actions 用 SSH 登录服务器，执行：

1. `git fetch` + `reset --hard origin/main`
2. `rsync` 到运行目录（默认 `/opt/toolkit`，**保留** `.venv` 与 `data/`）
3. `pip install -r requirements.txt`
4. `systemctl restart toolkit`
5. 访问 `/api/health` 做健康检查

---

## A. 一次性准备（VPS）

SSH 登录服务器后执行（root / sudo）：

```bash
curl -fsSL https://raw.githubusercontent.com/lurenXYN/toolkit/main/deploy/bootstrap-vps.sh -o /tmp/bootstrap-toolkit.sh
# 若 raw 尚未拉取到最新，也可：
# git clone https://github.com/lurenXYN/toolkit.git ~/github/toolkit && cd ~/github/toolkit

bash /tmp/bootstrap-toolkit.sh
# 等价手工步骤：
#   apt install -y git rsync curl python3-venv ffmpeg
#   git clone https://github.com/lurenXYN/toolkit.git ~/github/toolkit
#   cd ~/github/toolkit && ./deploy/bootstrap-vps.sh
```

默认：

| 项 | 值 |
|----|----|
| 克隆目录 | `~/github/toolkit` |
| 运行目录 | `/opt/toolkit` |
| 端口 | `8780` |
| systemd | `toolkit.service` |

验证：

```bash
systemctl is-active toolkit
curl -sS http://127.0.0.1:8780/api/health
curl -sS http://127.0.0.1:8780/api/tools
journalctl -u toolkit -n 30 --no-pager
```

手动再部署一次（不经过 Actions）：

```bash
cd ~/github/toolkit
git pull origin main
SKIP_PULL=1 REPO_DIR="$PWD" INSTALL_DIR=/opt/toolkit ./deploy/remote-update.sh
```

---

## B. 一次性准备（GitHub Secrets）

仓库 Secrets：https://github.com/lurenXYN/toolkit/settings/secrets/actions

与 market-desk **同一台 VPS** 时可复用同一把部署密钥（本机若已有 `C:\Users\BSI\market-desk-deploy`）：

```powershell
# 把 YOUR_VPS_IP 换成和 market-desk 相同的主机
gh secret set DEPLOY_HOST -R lurenXYN/toolkit --body "YOUR_VPS_IP"
gh secret set DEPLOY_USER -R lurenXYN/toolkit --body "root"
gh secret set DEPLOY_SSH_KEY -R lurenXYN/toolkit < "C:\Users\BSI\market-desk-deploy"
```

| Name | 必填 | 说明 |
|------|------|------|
| `DEPLOY_HOST` | 是 | VPS IP / 域名 |
| `DEPLOY_USER` | 是 | 通常 `root` |
| `DEPLOY_SSH_KEY` | 是 | 部署私钥全文 |
| `DEPLOY_PORT` | 否 | 默认 `22` |

可选 Variables：

| Name | 默认 |
|------|------|
| `DEPLOY_REPO_DIR` | `$HOME/github/toolkit` |
| `DEPLOY_INSTALL_DIR` | `/opt/toolkit` |

若服务器上还没有这把公钥，把 `market-desk-deploy.pub` 追加进 `~/.ssh/authorized_keys`。

本机测 SSH：

```powershell
ssh -i C:\Users\BSI\market-desk-deploy root@YOUR_VPS_IP "systemctl is-active toolkit || echo not-installed-yet"
```

Secrets 配好后，在 Actions 页对 **Deploy** 点 **Re-run**，或随便推一个空提交触发。

---

## C. 注意

- 服务器需有 **ffmpeg**；Ubuntu 22.04 自带 4.4 **不能解码动图 WebP**，应用会自动回退到 Pillow/libwebp
- 若仍想用新版 ffmpeg，可另装静态包（可选，非必须）
- `data/` 不会被 rsync 覆盖（输出缓存保留）
- 公网建议 Nginx + HTTPS，勿长期裸奔 `0.0.0.0:8780`
- 私钥只放 GitHub Secrets，不要提交进仓库
