"""
WSGI 入口 - 生产环境使用 Gunicorn 启动
用法: gunicorn wsgi:app -b 0.0.0.0:5000 -w 4
"""
from app import app, init_db, db

# 生产环境初始化数据库
init_db()
