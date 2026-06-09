#!/usr/bin/env python3
"""
Docker 시뮬레이션 스크립트

SkinLens Docker 컨테이너를 관리하고 테스트하는 단일 시뮬레이션 스크립트입니다.
"""

import os
import sys
import subprocess
import time
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
DOCKER_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
ENV_FILE = PROJECT_ROOT / "config" / "docker.env.example"


class DockerSimulation:
    """Docker 시뮬레이션 관리자"""

    def __init__(self, compose_file: Path, env_file: Optional[Path] = None):
        self.compose_file = compose_file
        self.env_file = env_file
        self.services = ["skinlens-engine", "skinlens-web"]

    def _run_command(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """명령어 실행"""
        print(f"실행: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        if check and result.returncode != 0:
            print(f"오류: {result.stderr}")
            sys.exit(1)
        return result

    def _docker_compose(self, *args) -> subprocess.CompletedProcess:
        """docker-compose 명령어 실행"""
        docker_path = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        cmd = [docker_path, "compose", "-f", str(self.compose_file)]
        if self.env_file and self.env_file.exists():
            cmd.extend(["--env-file", str(self.env_file)])
        cmd.extend(args)
        return self._run_command(cmd)

    def check_prerequisites(self) -> bool:
        """사전 요구사항 체크"""
        print("=" * 60)
        print("사전 요구사항 체크")
        print("=" * 60)

        # Docker 체크
        try:
            result = self._run_command(["docker", "--version"], check=False)
            if result.returncode == 0:
                print(f"✓ Docker: {result.stdout.strip()}")
            else:
                print("✗ Docker가 설치되지 않았습니다.")
                return False
        except FileNotFoundError:
            print("✗ Docker가 설치되지 않았습니다.")
            return False

        # Docker Compose 체크
        try:
            result = self._run_command(["docker-compose", "--version"], check=False)
            if result.returncode == 0:
                print(f"✓ Docker Compose: {result.stdout.strip()}")
            else:
                print("✗ Docker Compose가 설치되지 않았습니다.")
                return False
        except FileNotFoundError:
            print("✗ Docker Compose가 설치되지 않았습니다.")
            return False

        # GPU 체크 (선택사항)
        try:
            result = self._run_command(["nvidia-smi"], check=False)
            if result.returncode == 0:
                print("✓ NVIDIA GPU 감지됨")
            else:
                print("⚠ NVIDIA GPU 감지되지 않음 (CPU 모드 사용)")
        except FileNotFoundError:
            print("⚠ NVIDIA GPU 감지되지 않음 (CPU 모드 사용)")

        # 환경변수 파일 체크
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            print("✓ .env 파일 존재")
        else:
            print("⚠ .env 파일이 없습니다. config/docker.env.example를 복사하여 사용하세요.")
            print(f"  cp {ENV_FILE} .env")

        print()
        return True

    def build(self) -> None:
        """Docker 이미지 빌드"""
        print("=" * 60)
        print("Docker 이미지 빌드")
        print("=" * 60)
        self._docker_compose("build")
        print("✓ 빌드 완료")
        print()

    def start(self, engine_only: bool = False) -> None:
        """컨테이너 시작"""
        print("=" * 60)
        print("컨테이너 시작")
        print("=" * 60)

        if engine_only:
            print("엔진 서버만 시작합니다...")
            self._docker_compose("up", "-d", "skinlens-engine")
        else:
            print("전체 스택을 시작합니다...")
            self._docker_compose("up", "-d")

        print("✓ 컨테이너 시작 완료")
        print()

    def stop(self) -> None:
        """컨테이너 중지"""
        print("=" * 60)
        print("컨테이너 중지")
        print("=" * 60)
        self._docker_compose("down")
        print("✓ 컨테이너 중지 완료")
        print()

    def restart(self) -> None:
        """컨테이너 재시작"""
        print("=" * 60)
        print("컨테이너 재시작")
        print("=" * 60)
        self._docker_compose("restart")
        print("✓ 컨테이너 재시작 완료")
        print()

    def status(self) -> None:
        """컨테이너 상태 확인"""
        print("=" * 60)
        print("컨테이너 상태")
        print("=" * 60)
        result = self._docker_compose("ps")
        print(result.stdout)
        print()

    def logs(self, service: Optional[str] = None, follow: bool = False) -> None:
        """로그 확인"""
        print("=" * 60)
        print("로그 확인")
        print("=" * 60)

        cmd = ["logs"]
        if follow:
            cmd.append("-f")
        if service:
            cmd.append(service)
        else:
            cmd.extend(self.services)

        result = self._docker_compose(*cmd)
        print(result.stdout)
        print()

    def health_check(self) -> Dict[str, Any]:
        """헬스 체크"""
        print("=" * 60)
        print("헬스 체크")
        print("=" * 60)

        results = {}

        # 엔진 서버 헬스 체크
        try:
            result = self._run_command(
                ["curl", "-f", "http://localhost:8001/v1/engine/health"],
                check=False
            )
            if result.returncode == 0:
                print("✓ 엔진 서버: Healthy")
                results["engine"] = json.loads(result.stdout)
            else:
                print("✗ 엔진 서버: Unhealthy")
                results["engine"] = None
        except Exception as e:
            print(f"✗ 엔진 서버: 오류 - {e}")
            results["engine"] = None

        # 웹서버 헬스 체크
        try:
            result = self._run_command(
                ["curl", "-f", "http://localhost:8000/health"],
                check=False
            )
            if result.returncode == 0:
                print("✓ 웹서버: Healthy")
                results["web"] = json.loads(result.stdout)
            else:
                print("✗ 웹서버: Unhealthy")
                results["web"] = None
        except Exception as e:
            print(f"✗ 웹서버: 오류 - {e}")
            results["web"] = None

        print()
        return results

    def test_analysis(
        self, 
        image_path: Optional[str] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_contact: Optional[str] = None,
        customer_address: Optional[str] = None,
        gender: Optional[str] = None,
        age: Optional[int] = None,
        output_json: bool = True
    ) -> None:
        """분석 테스트"""
        print("=" * 60)
        print("분석 테스트")
        print("=" * 60)

        if not image_path:
            print("⚠ 테스트 이미지 경로가 필요합니다.")
            print("사용법: python scripts/docker_simulation.py test --image <path>")
            return

        if not Path(image_path).exists():
            print(f"✗ 이미지 파일이 존재하지 않습니다: {image_path}")
            return

        print(f"테스트 이미지: {image_path}")
        
        # 기본 사용자 정보 설정
        if not customer_id:
            customer_id = "test_customer_001"
        if not customer_name:
            customer_name = "테스트 고객"
        if not customer_contact:
            customer_contact = "010-1234-5678"
        if not customer_address:
            customer_address = "서울시 강남구"
        if not gender:
            gender = "female"
        if not age:
            age = 30

        print(f"고객 ID: {customer_id}")
        print(f"고객명: {customer_name}")
        print(f"성별: {gender}")
        print(f"나이: {age}")
        print()

        # 웹서버 API를 통한 분석 요청
        try:
            import requests
            
            # 분석 요청 데이터
            analysis_data = {
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_contact": customer_contact,
                "customer_address": customer_address,
                "gender": gender,
                "age": age,
                "do_restore": True,
                "include_base64": False,
                "score_safety_net": True,
                "llm_report": True,
                "use_multi_view_analysis": True,
                "debug": False
            }

            # multipart/form-data로 전송
            files = {
                "image": open(image_path, "rb")
            }
            data = {
                "analysis_request": json.dumps(analysis_data)
            }

            print("분석 요청 전송 중...")
            response = requests.post(
                "http://localhost:8000/v1/analysis/jobs",
                files=files,
                data=data,
                timeout=60
            )

            files["image"].close()

            if response.status_code == 202:
                result = response.json()
                job_id = result.get("job_id")
                print(f"✓ 분석 요청 성공: Job ID = {job_id}")
                print()

                # 작업 상태 폴링
                print("분석 진행 중...")
                max_wait = 600  # 10분
                wait_interval = 5
                elapsed = 0

                while elapsed < max_wait:
                    time.sleep(wait_interval)
                    elapsed += wait_interval

                    status_response = requests.get(
                        f"http://localhost:8000/v1/analysis/jobs/{job_id}",
                        timeout=30
                    )

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get("status")
                        print(f"  상태: {status} ({elapsed}s)")

                        if status == "succeeded":
                            print()
                            print("✓ 분석 완료")
                            
                            if output_json:
                                print()
                                print("=" * 60)
                                print("출력 JSON")
                                print("=" * 60)
                                print(json.dumps(status_data, indent=2, ensure_ascii=False))
                                print()
                            
                            # 결과 파일 저장
                            result_file = PROJECT_ROOT / "test_result.json"
                            with open(result_file, "w", encoding="utf-8") as f:
                                json.dump(status_data, f, indent=2, ensure_ascii=False)
                            print(f"✓ 결과 저장: {result_file}")
                            
                            return
                        elif status == "failed":
                            print()
                            print("✗ 분석 실패")
                            error = status_data.get("error", "Unknown error")
                            print(f"에러: {error}")
                            return
                    else:
                        print(f"✗ 상태 조회 실패: {status_response.status_code}")
                        return

                print("✗ 타임아웃: 분석이 10분 내에 완료되지 않았습니다.")
            else:
                print(f"✗ 분석 요청 실패: {response.status_code}")
                print(f"응답: {response.text}")

        except requests.exceptions.ConnectionError:
            print("✗ 웹서버에 연결할 수 없습니다.")
            print("컨테이너가 실행 중인지 확인하세요: python scripts/docker_simulation.py status")
        except Exception as e:
            print(f"✗ 오류 발생: {e}")
            import traceback
            traceback.print_exc()

        print()

    def cleanup(self) -> None:
        """정리"""
        print("=" * 60)
        print("정리")
        print("=" * 60)
        self._docker_compose("down", "-v", "--remove-orphans")
        print("✓ 정리 완료")
        print()

    def full_simulation(self) -> None:
        """전체 시뮬레이션"""
        print("=" * 60)
        print("전체 시뮬레이션 시작")
        print("=" * 60)
        print()

        # 사전 요구사항 체크
        if not self.check_prerequisites():
            print("사전 요구사항을 충족하지 못했습니다.")
            return

        # 빌드
        self.build()

        # 시작
        self.start()

        # 대기
        print("컨테이너가 시작될 때까지 대기합니다...")
        time.sleep(10)

        # 상태 확인
        self.status()

        # 헬스 체크
        self.health_check()

        print("=" * 60)
        print("시뮬레이션 완료")
        print("=" * 60)
        print()
        print("다음 명령어를 사용하여 로그를 확인하세요:")
        print("  python scripts/docker_simulation.py logs --follow")
        print()
        print("시뮬레이션을 중지하려면:")
        print("  python scripts/docker_simulation.py stop")


def main():
    parser = argparse.ArgumentParser(description="SkinLens Docker 시뮬레이션")
    parser.add_argument("command", choices=[
        "check", "build", "start", "stop", "restart", "status",
        "logs", "health", "test", "cleanup", "simulate"
    ], help="실행할 명령어")
    parser.add_argument("--engine-only", action="store_true", help="엔진 서버만 시작")
    parser.add_argument("--follow", "-f", action="store_true", help="로그 팔로우")
    parser.add_argument("--service", "-s", help="특정 서비스 로그 확인")
    parser.add_argument("--image", help="테스트 이미지 경로")
    parser.add_argument("--customer-id", help="고객 ID")
    parser.add_argument("--customer-name", help="고객명")
    parser.add_argument("--customer-contact", help="고객 연락처")
    parser.add_argument("--customer-address", help="고객 주소")
    parser.add_argument("--gender", help="성별 (male/female)")
    parser.add_argument("--age", type=int, help="나이")
    parser.add_argument("--no-output-json", action="store_true", help="출력 JSON 표시 안함")

    args = parser.parse_args()

    sim = DockerSimulation(DOCKER_COMPOSE_FILE, ENV_FILE)

    if args.command == "check":
        sim.check_prerequisites()
    elif args.command == "build":
        sim.build()
    elif args.command == "start":
        sim.start(engine_only=args.engine_only)
    elif args.command == "stop":
        sim.stop()
    elif args.command == "restart":
        sim.restart()
    elif args.command == "status":
        sim.status()
    elif args.command == "logs":
        sim.logs(service=args.service, follow=args.follow)
    elif args.command == "health":
        sim.health_check()
    elif args.command == "test":
        sim.test_analysis(
            image_path=args.image,
            customer_id=args.customer_id,
            customer_name=args.customer_name,
            customer_contact=args.customer_contact,
            customer_address=args.customer_address,
            gender=args.gender,
            age=args.age,
            output_json=not args.no_output_json
        )
    elif args.command == "cleanup":
        sim.cleanup()
    elif args.command == "simulate":
        sim.full_simulation()


if __name__ == "__main__":
    main()
