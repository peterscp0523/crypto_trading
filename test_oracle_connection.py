#!/usr/bin/env python3
"""
Oracle DB 연결 테스트 스크립트
문제 진단을 위한 상세한 로그 출력
"""
import os
import sys
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

print("=" * 70)
print("🔍 Oracle DB 연결 진단")
print("=" * 70)

# 1. 환경변수 확인
print("\n📋 1. 환경변수 확인")
print("-" * 70)

required_vars = ['ORACLE_DB_USER', 'ORACLE_DB_PASSWORD', 'ORACLE_DB_DSN']
for var in required_vars:
    value = os.environ.get(var, '')
    if var == 'ORACLE_DB_PASSWORD':
        # 비밀번호는 마스킹
        masked = value[:3] + '*' * (len(value) - 6) + value[-3:] if len(value) > 6 else '***'
        print(f"  {var}: {masked}")
    else:
        print(f"  {var}: {value}")

oracle_user = os.environ.get('ORACLE_DB_USER', '')
oracle_password = os.environ.get('ORACLE_DB_PASSWORD', '')
oracle_dsn = os.environ.get('ORACLE_DB_DSN', '')

if not all([oracle_user, oracle_password, oracle_dsn]):
    print("\n❌ 환경변수가 설정되지 않았습니다.")
    print("다음 명령으로 환경변수를 설정하세요:")
    print("  export ORACLE_DB_USER='your_user'")
    print("  export ORACLE_DB_PASSWORD='your_password'")
    print("  export ORACLE_DB_DSN='your_dsn'")
    sys.exit(1)

# 2. Wallet 파일 확인
print("\n📁 2. Wallet 파일 확인")
print("-" * 70)

wallet_location = os.environ.get('TNS_ADMIN', '/tmp/wallet')
print(f"  Wallet 위치: {wallet_location}")

if os.path.exists(wallet_location):
    print(f"  ✅ Wallet 디렉토리 존재")

    # Wallet 파일 목록
    wallet_files = os.listdir(wallet_location)
    print(f"  파일 목록:")
    for f in wallet_files:
        file_path = os.path.join(wallet_location, f)
        file_size = os.path.getsize(file_path)
        print(f"    - {f} ({file_size} bytes)")

    # 필수 파일 확인
    required_files = ['tnsnames.ora', 'sqlnet.ora', 'cwallet.sso']
    missing_files = [f for f in required_files if f not in wallet_files]

    if missing_files:
        print(f"\n  ⚠️  누락된 파일: {', '.join(missing_files)}")
    else:
        print(f"  ✅ 필수 파일 모두 존재")
else:
    print(f"  ❌ Wallet 디렉토리 없음: {wallet_location}")
    print("\n  Wallet을 다운로드하고 압축을 풀어주세요:")
    print("  1. Oracle Cloud Console > Autonomous Database > DB Connection")
    print("  2. Download Wallet")
    print(f"  3. unzip wallet.zip -d {wallet_location}")
    sys.exit(1)

# 3. DSN 파싱
print("\n🔗 3. DSN 정보 분석")
print("-" * 70)

try:
    # DSN에서 호스트와 포트 추출
    import re

    host_match = re.search(r'host=([^)]+)', oracle_dsn)
    port_match = re.search(r'port=(\d+)', oracle_dsn)
    service_match = re.search(r'service_name=([^)]+)', oracle_dsn)

    if host_match:
        print(f"  Host: {host_match.group(1)}")
    if port_match:
        print(f"  Port: {port_match.group(1)}")
    if service_match:
        print(f"  Service: {service_match.group(1)}")

    # 지역 확인
    if 'ap-chuncheon-1' in oracle_dsn:
        print(f"  ✅ 지역: ap-chuncheon-1 (춘천)")
    elif 'ap-seoul-1' in oracle_dsn:
        print(f"  ⚠️  지역: ap-seoul-1 (서울) - Wallet과 불일치 가능성")
    else:
        print(f"  ⚠️  알 수 없는 지역")

except Exception as e:
    print(f"  ⚠️  DSN 파싱 실패: {e}")

# 4. oracledb 모듈 확인
print("\n📦 4. oracledb 모듈 확인")
print("-" * 70)

try:
    import oracledb
    print(f"  ✅ oracledb 버전: {oracledb.__version__}")
    try:
        print(f"  클라이언트 버전: {oracledb.clientversion()}")
    except:
        print(f"  클라이언트 버전: Thin mode (no client needed)")
except ImportError:
    print(f"  ❌ oracledb 모듈이 설치되지 않았습니다")
    print("  설치: pip install oracledb")
    sys.exit(1)

# 5. 실제 연결 시도
print("\n🔌 5. Oracle DB 연결 시도")
print("-" * 70)

try:
    import oracledb

    # Thin 모드로 연결 (Wallet 사용)
    print("  연결 시도 중...")
    print(f"  사용자: {oracle_user}")
    print(f"  DSN: {oracle_dsn[:50]}...")

    conn = oracledb.connect(
        user=oracle_user,
        password=oracle_password,
        dsn=oracle_dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=None  # Auto-login wallet
    )

    print(f"\n  ✅✅✅ 연결 성공! ✅✅✅")

    # 간단한 쿼리 실행
    cursor = conn.cursor()
    cursor.execute("SELECT 'Hello from Oracle!' as message FROM DUAL")
    result = cursor.fetchone()
    print(f"  테스트 쿼리 결과: {result[0]}")

    # 테이블 목록 확인
    cursor.execute("""
        SELECT table_name
        FROM user_tables
        ORDER BY table_name
    """)
    tables = cursor.fetchall()

    if tables:
        print(f"\n  📊 존재하는 테이블 ({len(tables)}개):")
        for table in tables[:10]:  # 최대 10개만 표시
            print(f"    - {table[0]}")
        if len(tables) > 10:
            print(f"    ... 외 {len(tables) - 10}개")
    else:
        print(f"\n  ℹ️  테이블 없음 (새 데이터베이스)")

    cursor.close()
    conn.close()

    print("\n" + "=" * 70)
    print("✅ Oracle DB 연결 테스트 성공!")
    print("=" * 70)

except oracledb.Error as e:
    error_obj, = e.args
    print(f"\n  ❌ 연결 실패!")
    print(f"\n  에러 코드: {error_obj.code if hasattr(error_obj, 'code') else 'N/A'}")
    print(f"  에러 메시지: {error_obj.message if hasattr(error_obj, 'message') else str(e)}")

    print("\n  🔍 가능한 원인:")

    if "DPY-6000" in str(e) or "listener refused" in str(e).lower():
        print("  1. ❌ Network ACL 차단")
        print("     해결: Oracle Cloud Console > Network Access > ACL에 VM IP 추가")
        print(f"     추가할 IP: 140.245.69.95/32")
        print()
        print("  2. ❌ DB가 'Updating' 상태")
        print("     해결: ACL 변경 후 DB가 'Available' 상태가 될 때까지 대기 (5-10분)")
        print()
        print("  3. ❌ 방화벽/보안그룹 차단")
        print("     해결: VM의 아웃바운드 1522 포트 허용 확인")

    elif "DPY-4011" in str(e) or "invalid username" in str(e).lower():
        print("  ❌ 사용자명 또는 비밀번호 오류")
        print(f"     확인: 사용자명 '{oracle_user}' 확인")
        print("     확인: 비밀번호는 대소문자 구분")

    elif "wallet" in str(e).lower():
        print("  ❌ Wallet 파일 문제")
        print(f"     확인: {wallet_location} 디렉토리에 wallet 파일 존재 여부")
        print("     확인: cwallet.sso 파일 손상 여부")

    else:
        print(f"  ❌ 알 수 없는 오류")
        print(f"     전체 에러: {e}")

    print("\n" + "=" * 70)
    print("❌ Oracle DB 연결 테스트 실패")
    print("=" * 70)
    sys.exit(1)

except Exception as e:
    print(f"\n  ❌ 예상치 못한 오류: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
