# GitHub Actions 自动部署（与 market-desk 同构）

push `main`（或手动 Run workflow）后，GitHub Actions 用 SSH 登录服务器，执行：

1. `git fetch` + `reset --hard origin/main`
2. `rsync` 到运行目录（默认 `/opt/toolkit`，**保留** `.venv` 与 `data/`）
3. `pip install -r requirements.txt`
4. `systemctl restart toolkit`
5. 访问 `/api/health` 做健康检查

## 一次性准备（服务器）

```bash
apt install -y git rsync curl python3-venv ffmpeg

mkdir -p ~/github
git clone https://github.com/lurenXYN/toolkit.git ~/github/toolkit
cd ~/github/toolkit
chmod +x deploy/install-systemd.sh deploy/remote-update.sh
./deploy/install-systemd.sh
# 默认: INSTALL_DIR=/opt/toolkit  PORT=8780
```

手动演练更新：

```bash
cd ~/github/toolkit
SKIP_PULL=1 REPO_DIR="$PWD" INSTALL_DIR=/opt/toolkit ./deploy/remote-update.sh
```

## 一次性准备（SSH 部署密钥）

```bash
ssh-keygen -t ed25519 -C "github-actions-toolkit" -f ./toolkit-deploy -N ""
```

把公钥写入服务器 `~/.ssh/authorized_keys`，私钥放到 GitHub Secrets。

## 配置 GitHub Secrets

仓库：https://github.com/lurenXYN/toolkit/settings/secrets/actions

| Name | 必填 | 说明 |
|------|------|------|
| `DEPLOY_HOST` | 是 | VPS IP / 域名 |
| `DEPLOY_USER` | 是 | 如 `root` |
| `DEPLOY_SSH_KEY` | 是 | 部署私钥全文 |
| `DEPLOY_PORT` | 否 | 默认 22 |

可选 Variables：

| Name | 默认 |
|------|------|
| `DEPLOY_REPO_DIR` | `$HOME/github/toolkit` |
| `DEPLOY_INSTALL_DIR` | `/opt/toolkit` |

## 验证

```bash
systemctl is-active toolkit
curl -sS http://127.0.0.1:8780/api/health
journalctl -u toolkit -n 30 --no-pager
```

公网建议 Nginx + HTTPS，勿长期裸奔 `0.0.0.0:8780`。
