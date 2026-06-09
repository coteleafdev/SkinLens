#!/usr/bin/env python3
"""
Engine Server 실행 스크립트

엔진 서버를 독립적으로 실행합니다.
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from src.engine.engine_server import app
    import uvicorn
    
    config = {
        "host": "0.0.0.0",
        "port": 8001,
        "log_level": "info"
    }
    
    print("Starting Engine Server...")
    print(f"Host: {config['host']}")
    print(f"Port: {config['port']}")
    
    uvicorn.run(app, **config)
