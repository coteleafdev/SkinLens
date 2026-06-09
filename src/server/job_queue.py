"""
job_queue.py — 배치 작업 큐 관리

기능:
- 이미지 처리 대기열
- 작업 우선순위
- 작업 재시도 메커니즘
- 작업 상태 추적
"""
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any
from datetime import datetime
import heapq

log = logging.getLogger(__name__)


class JobStatus(Enum):
    """작업 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class JobPriority(Enum):
    """작업 우선순위"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass(order=True)
class Job:
    """작업 항목"""
    priority: int = field(compare=True)
    created_at: datetime = field(compare=True)
    job_id: str = field(compare=False)
    task_func: Callable = field(compare=False)
    task_args: tuple = field(compare=False)
    task_kwargs: dict = field(compare=False)
    max_retries: int = field(compare=False, default=3)
    retry_count: int = field(compare=False, default=0)
    status: JobStatus = field(compare=False, default=JobStatus.PENDING)
    error: Optional[str] = field(compare=False, default=None)


class JobQueue:
    """작업 큐 관리자"""

    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: 최대 동시 작업 수
        """
        self.queue: list[Job] = []
        self.max_workers = max_workers
        self.workers: list[asyncio.Task] = []
        self.running_jobs: dict[str, Job] = {}
        self.job_history: dict[str, Job] = {}
        self._queue_lock = asyncio.Lock()
        self._running = False

    async def add_job(
        self,
        job_id: str,
        task_func: Callable,
        task_args: tuple = (),
        task_kwargs: dict = None,
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: int = 3,
    ) -> None:
        """작업 추가.

        Args:
            job_id: 작업 ID
            task_func: 실행할 함수
            task_args: 함수 인자
            task_kwargs: 함수 키워드 인자
            priority: 우선순위
            max_retries: 최대 재시도 횟수
        """
        if task_kwargs is None:
            task_kwargs = {}

        job = Job(
            priority=priority.value,
            created_at=datetime.now(),
            job_id=job_id,
            task_func=task_func,
            task_args=task_args,
            task_kwargs=task_kwargs,
            max_retries=max_retries,
        )

        async with self._queue_lock:
            heapq.heappush(self.queue, job)
            self.job_history[job_id] = job

        log.info("작업 추가: job_id=%s, priority=%s, 큐 크기=%d", job_id, priority.name, len(self.queue))

    async def start(self) -> None:
        """작업 큐 시작"""
        if self._running:
            return

        self._running = True
        log.info("작업 큐 시작 (최대 작업자: %d)", self.max_workers)

        # 작업자 생성
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)

    async def stop(self) -> None:
        """작업 큐 중지"""
        self._running = False

        # 작업자 중지
        for worker in self.workers:
            worker.cancel()

        # 작업자 완료 대기
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

        log.info("작업 큐 중지")

    async def _worker(self, worker_name: str) -> None:
        """작업자 루프"""
        while self._running:
            try:
                # 작업 획득
                async with self._queue_lock:
                    if not self.queue:
                        await asyncio.sleep(0.1)
                        continue

                    job = heapq.heappop(self.queue)

                # 작업 실행
                self.running_jobs[job.job_id] = job
                job.status = JobStatus.RUNNING
                log.info("작업 시작: job_id=%s, worker=%s", job.job_id, worker_name)

                try:
                    result = await job.task_func(*job.task_args, **job.task_kwargs)
                    job.status = JobStatus.COMPLETED
                    log.info("작업 완료: job_id=%s, worker=%s", job.job_id, worker_name)
                except (RuntimeError, ValueError, OSError, IOError) as e:  # [FIX P2] 구체적 예외
                    job.error = str(e)
                    job.retry_count += 1

                    if job.retry_count < job.max_retries:
                        job.status = JobStatus.RETRYING
                        log.warning("작업 재시도: job_id=%s, 시도=%d/%d, error=%s",
                                   job.job_id, job.retry_count, job.max_retries, e)
                        # 재시도를 위해 큐에 다시 추가 (우선순위 유지, 재시도 횟수 전달)
                        async with self._queue_lock:
                            retry_job = Job(
                                priority=job.priority,
                                created_at=datetime.now(),
                                job_id=job.job_id,
                                task_func=job.task_func,
                                task_args=job.task_args,
                                task_kwargs=job.task_kwargs,
                                max_retries=job.max_retries,
                                retry_count=job.retry_count,  # 재시도 횟수 전달
                            )
                            heapq.heappush(self.queue, retry_job)
                            self.job_history[job.job_id] = retry_job
                    else:
                        job.status = JobStatus.FAILED
                        log.error("작업 실패: job_id=%s, 최대 재시도 초과, error=%s", job.job_id, e)

                finally:
                    del self.running_jobs[job.job_id]

            except asyncio.CancelledError:
                break
            except (RuntimeError, ValueError) as e:  # [FIX P2] 구체적 예외
                log.error("작업자 오류: worker=%s, error=%s", worker_name, e)
                await asyncio.sleep(1)

    def get_queue_stats(self) -> dict:
        """큐 통계 반환"""
        return {
            "queue_size": len(self.queue),
            "running_jobs": len(self.running_jobs),
            "max_workers": self.max_workers,
            "job_history_size": len(self.job_history),
            "running": self._running,
        }

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """작업 상태 조회"""
        job = self.job_history.get(job_id)
        if not job:
            return None

        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "priority": job.priority,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
        }


# 전역 작업 큐
_global_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """전역 작업 큐 반환"""
    global _global_queue
    if _global_queue is None:
        from src.utils.config import load_config
        config = load_config()
        server_config = config.get("server", {})
        job_queue_config = server_config.get("job_queue", {})
        max_workers = job_queue_config.get("max_workers", 4)

        _global_queue = JobQueue(max_workers=max_workers)
    return _global_queue
