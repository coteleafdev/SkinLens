# 성능 최적화 가이드 (Performance Optimization Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 개요

SkinLens 성능 최적화 방법입니다.

---

## 1. GPU 최적화

### 1.1 GPU 메모리 관리

**문제:**
- GPU 메모리 부족으로 OOM 발생

**해결:**
```python
import torch

# 배치 크기 감소
batch_size = 1  # 기본값 4 → 1

# 그라디언트 체크포인트 사용
from torch.utils.checkpoint import checkpoint

# 메모리 정리
torch.cuda.empty_cache()

# 혼합 정밀도 사용
from torch.cuda.amp import autocast
with autocast():
    output = model(input)
```

### 1.2 GPU 활용률 향상

```python
# 병렬 처리
from concurrent.futures import ThreadPoolExecutor

def process_images_parallel(images):
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process_image, img) for img in images]
        results = [f.result() for f in futures]
    return results
```

### 1.3 모델 최적화

```python
# 모델 양자화
import torch.quantization

model_quantized = torch.quantization.quantize_dynamic(
    model,
    {torch.nn.Linear},
    dtype=torch.qint8
)

# 모델 프루닝
import torch.nn.utils.prune as prune

prune.l1_unstructured(model.conv1, name='weight', amount=0.2)
```

---

## 2. 메모리 관리

### 2.1 이미지 메모리 최적화

```python
from PIL import Image
import numpy as np

# 이미지 리사이징
def resize_image(image_path, max_size=1024):
    img = Image.open(image_path)
    img.thumbnail((max_size, max_size))
    return img

# 메모리 매핑 사용
import memmap

# Lazy loading
def load_image_lazy(image_path):
    with Image.open(image_path) as img:
        return img.copy()
```

### 2.2 캐싱

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_analysis(image_hash):
    return analyze_image(image_hash)

# Redis 캐싱
import redis

r = redis.Redis(host='localhost', port=6379, db=0)

def get_cached_result(key):
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    return None
```

---

## 3. I/O 최적화

### 3.1 비동기 I/O

```python
import asyncio
import aiofiles

async def read_image_async(path):
    async with aiofiles.open(path, 'rb') as f:
        return await f.read()

async def process_images_async(paths):
    tasks = [read_image_async(p) for p in paths]
    return await asyncio.gather(*tasks)
```

### 3.2 파일 시스템 최적화

```python
# SSD 사용
# config/config.json
{
  "storage": {
    "use_ssd": true,
    "cache_dir": "/mnt/ssd/cache"
  }
}

# TMPFS 사용 (Linux)
sudo mount -t tmpfs -o size=4G tmpfs /tmp/skinlens
```

---

## 4. 데이터베이스 최적화

### 4.1 SQLite 최적화

```python
import sqlite3

# WAL 모드 활성화
conn = sqlite3.connect('skin_analysis.db')
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')
conn.execute('PRAGMA cache_size=10000')

# 인덱스 생성
conn.execute('CREATE INDEX IF NOT EXISTS idx_customer_id ON analyses(customer_id)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON analyses(created_at)')
```

### 4.2 쿼리 최적화

```python
# 배치 삽입
def batch_insert(records):
    cursor.executemany(
        "INSERT INTO analyses VALUES (?, ?, ?)",
        records
    )

# 쿼리 계획 확인
cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM analyses WHERE customer_id = ?")
```

---

## 5. 네트워크 최적화

### 5.1 HTTP 최적화

```python
# Keep-Alive
import httpx

client = httpx.Client(http2=True, timeout=30.0)

# 압축
import gzip

def compress_data(data):
    return gzip.compress(json.dumps(data).encode())
```

### 5.2 CDN 사용

```nginx
# nginx.conf
location /static/ {
    proxy_pass https://cdn.skinlens.com/static/;
    proxy_cache_valid 200 30d;
}
```

---

## 6. 병렬 처리

### 6.1 멀티프로세싱

```python
from multiprocessing import Pool

def process_image_mp(image_path):
    return analyze_image(image_path)

if __name__ == '__main__':
    with Pool(processes=4) as pool:
        results = pool.map(process_image_mp, image_paths)
```

### 6.2 멀티스레딩

```python
from threading import Thread

def process_image_thread(image_path, results):
    results.append(analyze_image(image_path))

threads = []
results = []

for img in image_paths:
    t = Thread(target=process_image_thread, args=(img, results))
    t.start()
    threads.append(t)

for t in threads:
    t.join()
```

---

## 7. 캐싱 전략

### 7.1 LLM 캐싱

```python
from functools import lru_cache

@lru_cache(maxsize=50)
def get_llm_response(prompt_hash):
    return llm.generate(prompt)
```

### 7.2 분석 결과 캐싱

```python
# 이미지 해시 기반 캐싱
import hashlib

def get_image_hash(image_path):
    with open(image_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def get_cached_analysis(image_path):
    img_hash = get_image_hash(image_path)
    return cache.get(img_hash)
```

---

## 8. 프로파일링

### 8.1 CPU 프로파일링

```python
import cProfile
import pstats

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # 함수 실행
    process_image("test.jpg")
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
```

### 8.2 메모리 프로파일링

```python
import memory_profiler

@memory_profiler.profile
def process_image_memory(image_path):
    img = load_image(image_path)
    result = analyze_image(img)
    return result
```

### 8.3 GPU 프로파일링

```bash
# NVIDIA Nsight
nsys profile --stats=true python main.py

# PyTorch Profiler
with torch.profiler.profile(
    activities=[
        torch.profiler.ProfilerActivity.CPU,
        torch.profiler.ProfilerActivity.CUDA
    ]
) as prof:
    model(input)
```

---

## 9. 모니터링

### 9.1 성능 메트릭

```python
import time

def measure_time(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"{func.__name__}: {elapsed:.2f}s")
        return result
    return wrapper

@measure_time
def process_image(image_path):
    return analyze_image(image_path)
```

### 9.2 Prometheus 메트릭

```python
from prometheus_client import Counter, Histogram

request_count = Counter('requests_total', 'Total requests')
request_duration = Histogram('request_duration_seconds', 'Request duration')

@request_duration.time()
def process_request():
    request_count.inc()
    # 처리 로직
```

---

## 10. 최적화 체크리스트

### 10.1 배포 전 확인

- [ ] GPU 메모리 사용량 확인
- [ ] CPU 사용량 확인
- [ ] 메모리 누수 확인
- [ ] I/O 병목 확인
- [ ] 네트워크 지연 확인
- [ ] DB 쿼리 최적화
- [ ] 캐싱 전략 적용
- [ ] 병렬 처리 활용

### 10.2 성능 목표

| 항목 | 목표 |
|------|------|
| 이미지 복원 | < 30초 |
| 이미지 분석 | < 20초 |
| LLM 소견 | < 60초 |
| 전체 파이프라인 | < 2분 |
| API 응답 | < 100ms (헬스체크) |

---

## 참고 문서

- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드
- `TROUBLESHOOTING_GUIDE.md` - 트러블슈팅 가이드
- `MONITORING_GUIDE.md` - 모니터링 가이드

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
| 0.6.0 | 2026-05-30 | 성능 최적화 가이드 초기 작성 | Cascade |
