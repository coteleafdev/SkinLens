"""피부 분석 결과 SQLite DB — 도메인 Mixin 합성 파사드.

[구조변경] 기존 5,199 LOC / 165 메서드의 God 클래스 `SkinAnalysisDB` 를
도메인별 Mixin(src/db/skin_db/*.py)으로 분리하고, 본 모듈은 이를 합성하는
얇은 파사드만 유지한다. 공개 클래스명·임포트 경로(`src.db.skin_analysis_db.SkinAnalysisDB`)
와 모든 메서드 시그니처는 불변 → 외부 호출부(server 라우터·deps·cli) 무수정.

분해 원칙:
  - 메서드 본문은 한 줄도 변경하지 않고 도메인 Mixin으로 이동(동작 보존).
  - 공유 자원(커넥션·Lock·WAL·스키마·암복호화/Supabase 동기화 헬퍼)은
    `_BaseRepository` 에 집중. 모든 Mixin 은 self._conn/self._lock 을 공유.
  - 중복 정의(get/update_notification_settings)는 동일 Mixin 내 원본 순서로 보존
    → 기존과 동일하게 '뒤 정의'가 유효(별도 정리 권장 항목).
"""
from src.db.skin_db._base import _BaseRepository
from src.db.skin_db.analysis import AnalysisMixin
from src.db.skin_db.recovery import RecoveryMixin
from src.db.skin_db.apikeys import ApiKeysMixin
from src.db.skin_db.user_prefs import UserPrefsMixin
from src.db.skin_db.notifications import NotificationsMixin
from src.db.skin_db.recommendations import RecommendationsMixin
from src.db.skin_db.customers import CustomersMixin
from src.db.skin_db.products import ProductsMixin
from src.db.skin_db.sessions import SessionsMixin
from src.db.skin_db.security import SecurityMixin
from src.db.skin_db.stats import StatsMixin
from src.db.skin_db.feedback import FeedbackMixin
from src.db.skin_db.orders import OrdersMixin
from src.db.skin_db.gamification import GamificationMixin
from src.db.skin_db.webhooks import WebhooksMixin
from src.db.skin_db.images import ImagesMixin
from src.db.skin_db.abtest import AbTestMixin
from src.db.skin_db.sync import SyncMixin
from src.db.skin_db.auth import AuthMixin
from src.db.skin_db.surveys import SurveysMixin
from src.db.skin_db.pcr import PcrMixin


class SkinAnalysisDB(
    AnalysisMixin,
    RecoveryMixin,
    ApiKeysMixin,
    UserPrefsMixin,
    NotificationsMixin,
    RecommendationsMixin,
    CustomersMixin,
    ProductsMixin,
    SessionsMixin,
    SecurityMixin,
    StatsMixin,
    FeedbackMixin,
    OrdersMixin,
    GamificationMixin,
    WebhooksMixin,
    ImagesMixin,
    AbTestMixin,
    SyncMixin,
    AuthMixin,
    SurveysMixin,
    PcrMixin,
    _BaseRepository,
):
    """피부 분석 결과를 관리하는 SQLite DB 클래스 (도메인 Mixin 합성).

    공개 API는 분해 전과 동일. 인스턴스 생성/사용법 변화 없음:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        db.save_analysis(...); db.get_recent_analyses(...)
    """
    pass


__all__ = ["SkinAnalysisDB"]
