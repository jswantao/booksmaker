#!/usr/bin/env python
# run.py — 项目启动入口 (从根目录运行后端 API 服务)
# 用法: python run.py  或  cd backend && python app.py

import sys
from pathlib import Path

# 将 backend/ 加入 Python 搜索路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app import main

if __name__ == "__main__":
    main()
