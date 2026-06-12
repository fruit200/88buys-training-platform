## 阿里系供应链直签服务商精英培训会 — 部署上线指南

本文档帮助你将项目从本地部署到公网，让所有服务商都能通过浏览器访问，你通过管理后台管理内容。

---

### 一、快速部署（推荐新手）

#### 方案 A：Railway（免费额度，5分钟上线）

1. 将项目代码推送到 GitHub 仓库
2. 打开 [railway.app](https://railway.app)，用 GitHub 登录
3. 点击 "New Project" → "Deploy from GitHub repo" → 选择你的仓库
4. 添加环境变量：`SECRET_KEY` = 一段随机字符串
5. Railway 会自动构建并给你一个公网地址，如 `https://xxx.up.railway.app`
6. 把这个地址发给服务商即可使用

#### 方案 B：Render（免费额度）

1. 推送代码到 GitHub
2. 打开 [render.com](https://render.com)，创建 "Web Service"
3. 关联 GitHub 仓库
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn wsgi:app -b 0.0.0.0:$PORT -w 2 --timeout 120`
6. 添加环境变量 `SECRET_KEY`
7. 部署完成后获得公网地址

---

### 二、云服务器部署（推荐正式使用）

适合需要稳定运行、绑定域名的场景。

#### 第 1 步：购买服务器

- 阿里云 ECS / 腾讯云轻量应用服务器 / 华为云 ECS
- 推荐配置：2核4G 内存，Ubuntu 22.04 系统
- 购买后记下公网 IP

#### 第 2 步：连接服务器并安装环境

```bash
# SSH 连接服务器（替换为你的 IP）
ssh root@你的服务器IP

# 更新系统
apt update && apt upgrade -y

# 安装 Python 和 Nginx
apt install -y python3 python3-pip python3-venv nginx git
```

#### 第 3 步：上传代码

```bash
# 方式一：Git 克隆（推荐，方便后续更新）
cd /opt
git clone https://github.com/你的用户名/training-platform.git
cd training-platform

# 方式二：直接上传文件
# 使用 scp 或 SFTP 工具将项目文件传到 /opt/training-platform/
```

#### 第 4 步：安装依赖并启动

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 设置密钥（重要！替换为随机字符串）
export SECRET_KEY="换成一段随机字符串"

# 测试启动（看到正常输出后 Ctrl+C 停止）
python app.py

# 正式后台运行（使用 Gunicorn）
nohup gunicorn wsgi:app -b 0.0.0.0:5000 -w 4 --timeout 120 > app.log 2>&1 &
```

此时通过 `http://你的服务器IP:5000` 应该可以访问。

#### 第 5 步：配置 Nginx 反向代理（用 80 端口访问）

```bash
# 编辑 Nginx 配置
nano /etc/nginx/sites-available/training

# 粘贴以下内容（替换 server_name）：
```

```nginx
server {
    listen 80;
    server_name 你的域名或IP;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
    }
}
```

```bash
# 启用配置并重启 Nginx
ln -s /etc/nginx/sites-available/training /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx
```

现在通过 `http://你的服务器IP` 或 `http://你的域名` 即可访问。

#### 第 6 步：配置 HTTPS（推荐）

```bash
# 安装 Certbot（需要先将域名解析到服务器 IP）
apt install -y certbot python3-certbot-nginx

# 自动获取证书并配置 Nginx
certbot --nginx -d 你的域名
```

---

### 三、Docker 部署

```bash
# 在服务器上安装 Docker
curl -fsSL https://get.docker.com | sh

# 克隆项目
git clone https://github.com/你的用户名/training-platform.git
cd training-platform

# 修改 docker-compose.yml 中的 SECRET_KEY

# 一键启动
docker compose up -d

# 查看日志
docker compose logs -f
```

---

### 四、上线后的管理流程

**你的角色（管理员）：**
- 访问 `https://你的域名/admin`
- 用 `admin / admin123` 登录（建议上线后修改密码）
- 在后台创建培训期数、上传视频和 PDF 资料、管理用户

**服务商的角色：**
- 访问 `https://你的域名`
- 用手机号 + 验证码 `123456` 登录
- 首次登录需填写姓名、公司、职位
- 浏览培训资料、观看视频、查看 PDF

**日常运维：**
- 定期检查服务器日志：`cat app.log` 或 `docker compose logs`
- 备份数据库：`cp training.db training_backup_日期.db`
- 更新代码后重启服务：`kill -HUP $(pgrep gunicorn)` 或 `docker compose restart`

---

### 五、安全建议

1. **修改管理员密码**：上线后建议修改默认的 admin123 密码
2. **设置强 SECRET_KEY**：用于 session 加密，建议用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成
3. **配置防火墙**：只开放 80、443 端口，关闭 5000 端口的外部访问
4. **定期备份**：数据库和上传文件都要定期备份
5. **HTTPS**：正式环境务必配置 SSL 证书，避免数据明文传输
