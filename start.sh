#!/bin/bash
# 阿里系供应链直签服务商精英培训会 - 一键启动脚本 (Linux/macOS)

set -e

echo "=========================================="
echo "  阿里系供应链直签服务商精英培训会 - 启动中..."
echo "=========================================="

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📦 安装依赖..."
pip install -r requirements.txt -q

# 创建上传目录
mkdir -p uploads/videos uploads/pdfs uploads/covers

# 启动应用
echo ""
echo "🚀 启动应用服务器..."
echo ""
python app.py
