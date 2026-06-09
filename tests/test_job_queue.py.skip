"""
test_job_queue.py — 작업 큐 테스트
"""
import pytest
import asyncio
from src.server.job_queue import JobQueue, JobPriority, JobStatus


class TestJobQueue:
    """작업 큐 테스트"""

    @pytest.mark.asyncio
    async def test_job_queue_initialization(self):
        """작업 큐 초기화 테스트"""
        queue = JobQueue(max_workers=2)
        assert queue.max_workers == 2
        assert len(queue.queue) == 0
        assert not queue._running

    @pytest.mark.asyncio
    async def test_add_job(self):
        """작업 추가 테스트"""
        queue = JobQueue(max_workers=2)

        async def dummy_task():
            await asyncio.sleep(0.1)
            return "done"

        await queue.add_job(
            job_id="test_job_1",
            task_func=dummy_task,
            priority=JobPriority.NORMAL,
        )

        assert len(queue.queue) == 1
        assert queue.queue[0].job_id == "test_job_1"

    @pytest.mark.asyncio
    async def test_job_priority_ordering(self):
        """작업 우선순위 정렬 테스트"""
        queue = JobQueue(max_workers=2)

        async def dummy_task():
            return "done"

        # 다른 우선순위로 작업 추가
        await queue.add_job("job_low", dummy_task, priority=JobPriority.LOW)
        await queue.add_job("job_high", dummy_task, priority=JobPriority.HIGH)
        await queue.add_job("job_normal", dummy_task, priority=JobPriority.NORMAL)

        # 우선순위 순서 확인 (HIGH > NORMAL > LOW)
        # 힙은 최소 힙이므로 가장 낮은 우선순위 값이 먼저 나옴
        # JobPriority: URGENT=0, HIGH=1, NORMAL=2, LOW=3
        # 첫 번째는 가장 높은 우선순위 (HIGH)
        assert queue.queue[0].job_id == "job_high"  # priority=1
        assert queue.queue[0].priority == 1

        # 나머지 작업들이 존재하는지 확인
        job_ids = [job.job_id for job in queue.queue]
        assert "job_normal" in job_ids
        assert "job_low" in job_ids

    @pytest.mark.asyncio
    async def test_job_execution(self):
        """작업 실행 테스트"""
        queue = JobQueue(max_workers=1)

        execution_log = []

        async def test_task(value):
            execution_log.append(value)
            return value

        await queue.add_job("job_1", test_task, task_args=("task1",))
        await queue.add_job("job_2", test_task, task_args=("task2",))

        # 큐 시작
        await queue.start()

        # 작업 완료 대기
        await asyncio.sleep(0.5)

        # 작업 실행 확인
        assert "task1" in execution_log
        assert "task2" in execution_log

        # 큐 중지
        await queue.stop()

    @pytest.mark.asyncio
    async def test_job_retry_mechanism(self):
        """작업 재시도 메커니즘 테스트"""
        queue = JobQueue(max_workers=1)

        attempt_count = 0

        async def failing_task():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Simulated failure")
            return "success"

        await queue.add_job("retry_job", failing_task, max_retries=3)

        await queue.start()
        await asyncio.sleep(1.0)  # 재시도 대기

        # 작업이 성공적으로 완료되었는지 확인
        assert attempt_count >= 3  # 최소 3번 시도 (초기 + 2회 재시도)

        # 작업 상태 확인 (COMPLETED 상태여야 함)
        job_status = queue.get_job_status("retry_job")
        assert job_status is not None
        assert job_status["status"] == "completed"

        await queue.stop()

    def test_queue_stats(self):
        """큐 통계 테스트"""
        queue = JobQueue(max_workers=4)
        stats = queue.get_queue_stats()

        assert "queue_size" in stats
        assert "running_jobs" in stats
        assert "max_workers" in stats
        assert "job_history_size" in stats
        assert "running" in stats
        assert stats["max_workers"] == 4

    def test_job_status_not_found(self):
        """존재하지 않는 작업 상태 조회 테스트"""
        queue = JobQueue()
        status = queue.get_job_status("nonexistent_job")
        assert status is None

    def test_job_queue_config_from_json(self):
        """config.json에서 작업 큐 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        job_queue_config = server_config.get("job_queue", {})

        assert "max_workers" in job_queue_config
        assert job_queue_config["max_workers"] > 0
