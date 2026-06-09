"""공용 모듈 (server·engine 등 여러 진입점이 공유).

의존성 최소화 원칙: 이 패키지의 모듈은 무거운 의존성(torch, fastapi 등)을
import 하지 않는다. server/engine 양쪽에서 안전하게 import 가능해야 한다.
"""
