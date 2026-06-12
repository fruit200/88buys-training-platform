FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建上传目录
RUN mkdir -p uploads/videos uploads/pdfs uploads/covers

EXPOSE 5000

ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV SECRET_KEY=change-me-in-production

# 生产环境使用 Gunicorn (4 workers, 120s 超时适配大文件上传)
CMD ["gunicorn", "wsgi:app", "-b", "0.0.0.0:5000", "-w", "4", "--timeout", "120"]
