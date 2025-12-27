#!/bin/bash

# 데이터베이스 초기화 스크립트
# Terraform으로 생성된 Autonomous Database에 테이블을 생성합니다

set -e

echo "======================================"
echo "🗄️  Database 초기화 시작"
echo "======================================"

# Wallet 디렉토리 확인
WALLET_DIR="$(dirname "$0")/outputs/wallet"
if [ ! -d "$WALLET_DIR" ]; then
  echo "❌ Wallet 디렉토리를 찾을 수 없습니다: $WALLET_DIR"
  echo "   먼저 'terraform apply'를 실행하세요."
  exit 1
fi

# tnsnames.ora 확인
TNSNAMES_FILE="$WALLET_DIR/tnsnames.ora"
if [ ! -f "$TNSNAMES_FILE" ]; then
  echo "❌ tnsnames.ora 파일을 찾을 수 없습니다: $TNSNAMES_FILE"
  exit 1
fi

# DB 이름 추출
DB_NAME=$(grep -o '[a-z0-9]*_medium' "$TNSNAMES_FILE" | head -1 | sed 's/_medium//')

if [ -z "$DB_NAME" ]; then
  echo "❌ Database 이름을 찾을 수 없습니다."
  exit 1
fi

echo "✅ Database: $DB_NAME"

# Admin 비밀번호 입력
read -sp "🔑 ADMIN 비밀번호 입력: " ADMIN_PASSWORD
echo ""

# 환경변수 설정
export TNS_ADMIN="$WALLET_DIR"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/opt/oracle/instantclient_21_11"

# Python으로 데이터베이스 초기화
echo ""
echo "📊 테이블 생성 중..."
python3 - <<EOF
import os
import sys

# 프로젝트 루트로 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath('$0'))))

try:
    import cx_Oracle

    # 연결 정보
    dsn = "${DB_NAME}_medium"
    user = "ADMIN"
    password = "$ADMIN_PASSWORD"

    # 연결
    print(f"🔌 연결 중: {user}@{dsn}")
    connection = cx_Oracle.connect(user, password, dsn)
    cursor = connection.cursor()

    # 연결 확인
    cursor.execute("SELECT 'Connected to Oracle DB!' FROM DUAL")
    result = cursor.fetchone()
    print(f"✅ {result[0]}")

    # database_manager.py의 SQL 실행
    print("\n📋 테이블 생성 중...")

    # 1. candles 테이블
    cursor.execute('''
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE candles';
        EXCEPTION
            WHEN OTHERS THEN NULL;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE candles (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            market VARCHAR2(20) NOT NULL,
            timeframe VARCHAR2(10) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            open_price NUMBER(20, 8),
            high_price NUMBER(20, 8),
            low_price NUMBER(20, 8),
            close_price NUMBER(20, 8),
            volume NUMBER(30, 8),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT candles_unique UNIQUE(market, timeframe, timestamp)
        )
    ''')
    print("  ✅ candles 테이블 생성")

    # 2. trades 테이블
    cursor.execute('''
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE trades';
        EXCEPTION
            WHEN OTHERS THEN NULL;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE trades (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            market VARCHAR2(20) NOT NULL,
            trade_type VARCHAR2(10) NOT NULL,
            price NUMBER(20, 8),
            amount NUMBER(30, 8),
            krw_amount NUMBER(20, 2),
            profit NUMBER(20, 2),
            profit_rate NUMBER(10, 4),
            reason VARCHAR2(100),
            hold_time_minutes NUMBER,
            peak_profit NUMBER(10, 4),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("  ✅ trades 테이블 생성")

    # 3. parameter_history 테이블
    cursor.execute('''
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE parameter_history';
        EXCEPTION
            WHEN OTHERS THEN NULL;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE parameter_history (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            market VARCHAR2(20),
            optimization_date TIMESTAMP,
            quick_profit NUMBER(6, 4),
            take_profit_1 NUMBER(6, 4),
            take_profit_2 NUMBER(6, 4),
            stop_loss NUMBER(6, 4),
            trailing_stop_tight NUMBER(6, 4),
            trailing_stop_medium NUMBER(6, 4),
            trailing_stop_wide NUMBER(6, 4),
            backtest_return NUMBER(10, 2),
            backtest_winrate NUMBER(6, 2),
            backtest_sharpe NUMBER(10, 4),
            score NUMBER(10, 2),
            is_active NUMBER(1) DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("  ✅ parameter_history 테이블 생성")

    # 4. daily_performance 테이블
    cursor.execute('''
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE daily_performance';
        EXCEPTION
            WHEN OTHERS THEN NULL;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE daily_performance (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            date DATE NOT NULL,
            total_trades NUMBER,
            winning_trades NUMBER,
            win_rate NUMBER(6, 2),
            total_profit NUMBER(20, 2),
            best_trade NUMBER(10, 2),
            worst_trade NUMBER(10, 2),
            avg_hold_time_minutes NUMBER,
            sharpe_ratio NUMBER(10, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT daily_perf_unique UNIQUE(date)
        )
    ''')
    print("  ✅ daily_performance 테이블 생성")

    # 인덱스 생성
    print("\n📊 인덱스 생성 중...")

    cursor.execute('''
        CREATE INDEX idx_candles_market_time
        ON candles(market, timeframe, timestamp DESC)
    ''')
    print("  ✅ idx_candles_market_time")

    cursor.execute('''
        CREATE INDEX idx_trades_timestamp
        ON trades(timestamp DESC)
    ''')
    print("  ✅ idx_trades_timestamp")

    # 커밋
    connection.commit()

    # 테이블 확인
    print("\n📋 생성된 테이블 목록:")
    cursor.execute("""
        SELECT table_name, num_rows
        FROM user_tables
        WHERE table_name IN ('CANDLES', 'TRADES', 'PARAMETER_HISTORY', 'DAILY_PERFORMANCE')
        ORDER BY table_name
    """)

    for row in cursor:
        print(f"  • {row[0]}")

    cursor.close()
    connection.close()

    print("\n✅ 데이터베이스 초기화 완료!")

except ImportError:
    print("❌ cx_Oracle 패키지가 설치되지 않았습니다.")
    print("   pip install cx_Oracle")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

EOF

echo ""
echo "======================================"
echo "✅ 초기화 완료!"
echo "======================================"
