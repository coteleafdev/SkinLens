"""
auto_recovery_engine.py — 장애 자동 복구 엔진

기능:
- 장애 감지
- 복구 플레이북 실행
- 복구 상태 추적
- 롤백 관리
- 알림 전송
"""
import logging
import asyncio
import time
from typing import Dict, Any, Optional, Callable
from enum import Enum

from src.db.skin_analysis_db import SkinAnalysisDB
from src.notification import AlertSystem

log = logging.getLogger(__name__)


class IncidentType(Enum):
    """장애 유형"""
    SERVER_DOWN = "server_down"
    DATABASE_DOWN = "database_down"
    NETWORK_FAILURE = "network_failure"
    CPU_OVERLOAD = "cpu_overload"
    MEMORY_OVERLOAD = "memory_overload"
    DISK_FULL = "disk_full"


class Severity(Enum):
    """심각도"""
    P0 = "P0"  # Critical
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low


class RecoveryActionType(Enum):
    """복구 작업 유형"""
    RESTART = "restart"
    FAILOVER = "failover"
    SCALE_OUT = "scale_out"
    ROLLBACK = "rollback"
    DATA_RESTORE = "data_restore"


class RecoveryEngine:
    """자동 복구 엔진"""
    
    def __init__(self, db: SkinAnalysisDB, alert_system: Optional[AlertSystem] = None):
        self.db = db
        self.alert_system = alert_system or AlertSystem()
        self.recovery_playbooks: Dict[str, Callable] = {}
        self._register_playbooks()
    
    def _register_playbooks(self):
        """복구 플레이북 등록"""
        self.recovery_playbooks = {
            IncidentType.SERVER_DOWN.value: self._playbook_server_restart,
            IncidentType.DATABASE_DOWN.value: self._playbook_database_recovery,
            IncidentType.CPU_OVERLOAD.value: self._playbook_cpu_scale_out,
            IncidentType.MEMORY_OVERLOAD.value: self._playbook_memory_scale_out,
            IncidentType.DISK_FULL.value: self._playbook_disk_cleanup,
        }
    
    async def detect_and_recover(
        self,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str] = None,
    ) -> str:
        """
        장애 감지 및 자동 복구
        
        Returns:
            str: 장애 ID
        """
        # 장애 이벤트 생성
        incident_id = self.db.create_incident(
            incident_type=incident_type,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
        )
        
        log.info(f"[Recovery] 장애 감지: ID={incident_id}, Type={incident_type}, Severity={severity}")
        
        # 알림 전송
        await self.alert_system.send_incident_alert(
            incident_id=incident_id,
            incident_type=incident_type,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
        )
        
        # 복구 플레이북 실행
        if incident_type in self.recovery_playbooks:
            try:
                await self._execute_playbook(incident_id, incident_type)
            except Exception as e:
                log.error(f"[Recovery] 복구 플레이북 실행 실패: {e}")
                self.db.update_incident_status(incident_id, "failed")
        else:
            log.warning(f"[Recovery] 복구 플레이북 없음: {incident_type}")
            self.db.update_incident_status(incident_id, "failed")
        
        return incident_id
    
    async def _execute_playbook(self, incident_id: str, incident_type: str):
        """복구 플레이북 실행"""
        playbook = self.recovery_playbooks[incident_type]
        
        # 복구 작업 생성
        action_id = self.db.create_recovery_action(
            incident_id=incident_id,
            action_type=RecoveryActionType.RESTART.value,
        )
        
        # 상태 업데이트
        self.db.update_recovery_action_status(action_id, "in_progress")
        self.db.update_incident_status(incident_id, "recovering")
        
        # 로그 추가
        self.db.add_recovery_log(action_id, "info", f"Starting recovery playbook: {incident_type}")
        
        try:
            # 플레이북 실행
            success = await playbook(incident_id, action_id)
            
            if success:
                self.db.update_recovery_action_status(action_id, "completed")
                self.db.update_incident_status(incident_id, "resolved")
                self.db.add_recovery_log(action_id, "info", "Recovery completed successfully")
                
                # 복구 완료 알림
                await self.alert_system.send_recovery_alert(
                    incident_id=incident_id,
                    action_type=RecoveryActionType.RESTART.value,
                    status="completed",
                )
                
                log.info(f"[Recovery] 복구 성공: IncidentID={incident_id}")
            else:
                self.db.update_recovery_action_status(action_id, "failed", error_message="Playbook returned False")
                self.db.update_incident_status(incident_id, "failed")
                self.db.add_recovery_log(action_id, "error", "Recovery playbook failed")
                log.error(f"[Recovery] 복구 실패: IncidentID={incident_id}")
        except Exception as e:
            self.db.update_recovery_action_status(action_id, "failed", error_message=str(e))
            self.db.update_incident_status(incident_id, "failed")
            self.db.add_recovery_log(action_id, "error", f"Recovery playbook error: {str(e)}")
            log.error(f"[Recovery] 복구 플레이북 예외: {e}")
    
    async def _playbook_server_restart(self, incident_id: str, action_id: str) -> bool:
        """서버 재시작 플레이북"""
        self.db.add_recovery_log(action_id, "info", "Attempting server restart")
        
        # 실제 서비스 재시작 로직 (예시)
        # 실제 구현에서는 systemctl, docker restart 등 사용
        await asyncio.sleep(2)  # 시뮬레이션
        
        self.db.add_recovery_log(action_id, "info", "Server restart completed")
        return True
    
    async def _playbook_database_recovery(self, incident_id: str, action_id: str) -> bool:
        """데이터베이스 복구 플레이북"""
        self.db.add_recovery_log(action_id, "info", "Attempting database recovery")
        
        # 데이터베이스 연결 시도
        try:
            # 연결 테스트
            self.db.add_recovery_log(action_id, "info", "Testing database connection")
            await asyncio.sleep(1)  # 시뮬레이션
            
            self.db.add_recovery_log(action_id, "info", "Database connection restored")
            return True
        except Exception as e:
            self.db.add_recovery_log(action_id, "error", f"Database recovery failed: {str(e)}")
            return False
    
    async def _playbook_cpu_scale_out(self, incident_id: str, action_id: str) -> bool:
        """CPU 스케일 아웃 플레이북"""
        self.db.add_recovery_log(action_id, "info", "Attempting CPU scale out")
        
        # 실제 스케일 아웃 로직 (예시)
        # Kubernetes HPA, Auto Scaling Group 등
        await asyncio.sleep(3)  # 시뮬레이션
        
        self.db.add_recovery_log(action_id, "info", "CPU scale out completed")
        return True
    
    async def _playbook_memory_scale_out(self, incident_id: str, action_id: str) -> bool:
        """메모리 스케일 아웃 플레이북"""
        self.db.add_recovery_log(action_id, "info", "Attempting memory scale out")
        
        # 실제 스케일 아웃 로직
        await asyncio.sleep(3)  # 시뮬레이션
        
        self.db.add_recovery_log(action_id, "info", "Memory scale out completed")
        return True
    
    async def _playbook_disk_cleanup(self, incident_id: str, action_id: str) -> bool:
        """디스크 정리 플레이북"""
        self.db.add_recovery_log(action_id, "info", "Attempting disk cleanup")
        
        # 실제 디스크 정리 로직
        await asyncio.sleep(5)  # 시뮬레이션
        
        self.db.add_recovery_log(action_id, "info", "Disk cleanup completed")
        return True
    
    async def rollback_recovery(self, action_id: str) -> bool:
        """복구 롤백"""
        self.db.add_recovery_log(action_id, "info", "Starting rollback")
        
        # 롤백 로직
        await asyncio.sleep(2)  # 시뮬레이션
        
        self.db.update_recovery_action_status(action_id, "rolled_back")
        self.db.add_recovery_log(action_id, "info", "Rollback completed")
        
        return True


class HealthMonitor:
    """헬스 모니터 - 주기적 헬스 체크 및 장애 감지"""
    
    def __init__(self, recovery_engine: RecoveryEngine):
        self.recovery_engine = recovery_engine
        self.monitoring_enabled = True
        self.check_interval = 30  # 30초
    
    async def start_monitoring(self):
        """모니터링 시작"""
        log.info("[HealthMonitor] 헬스 모니터링 시작")
        
        while self.monitoring_enabled:
            try:
                await self._check_system_health()
            except Exception as e:
                log.error(f"[HealthMonitor] 헬스 체크 실패: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def _check_system_health(self):
        """시스템 헬스 체크"""
        import psutil
        
        # CPU 체크
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 90:
            await self.recovery_engine.detect_and_recover(
                incident_type=IncidentType.CPU_OVERLOAD.value,
                severity=Severity.P1.value,
                resource_type="cpu",
                resource_id="system",
                description=f"CPU usage: {cpu_percent}%",
            )
        
        # 메모리 체크
        memory = psutil.virtual_memory()
        if memory.percent > 95:
            await self.recovery_engine.detect_and_recover(
                incident_type=IncidentType.MEMORY_OVERLOAD.value,
                severity=Severity.P1.value,
                resource_type="memory",
                resource_id="system",
                description=f"Memory usage: {memory.percent}%",
            )
        
        # 디스크 체크
        disk = psutil.disk_usage('/')
        if disk.percent > 90:
            await self.recovery_engine.detect_and_recover(
                incident_type=IncidentType.DISK_FULL.value,
                severity=Severity.P2.value,
                resource_type="disk",
                resource_id="/",
                description=f"Disk usage: {disk.percent}%",
            )
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring_enabled = False
        log.info("[HealthMonitor] 헬스 모니터링 중지")
