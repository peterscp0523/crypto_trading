# 데이터베이스 통합 기능 완료

## 📋 구현된 기능 요약

### 1. 데이터베이스 관리 시스템
**파일**: `database_manager.py`

- ✅ Oracle Cloud Autonomous Database 지원 (Always Free Tier)
- ✅ SQLite 로컬 개발 모드 지원
- ✅ 자동 테이블 생성 (candles, trades, parameter_history, daily_performance)
- ✅ 캔들 데이터 저장/조회
- ✅ 거래 기록 저장
- ✅ 파라미터 최적화 결과 저장/조회
- ✅ 일일 성과 집계

**주요 테이블**:
```sql
candles              -- 캔들 데이터 (15분봉, 1시간봉 등)
trades               -- 거래 기록 (매수/매도)
parameter_history    -- 파라미터 최적화 기록
daily_performance    -- 일일 성과 요약
```

---

### 2. 자동 데이터 수집 스케줄러
**파일**: `data_collector.py`

- ✅ 1시간마다 캔들 데이터 자동 수집
- ✅ 거래량 상위 20개 코인 자동 선택
- ✅ 15분봉, 1시간봉 데이터 저장
- ✅ 각 코인당 최대 200개 캔들 저장
- ✅ API 요청 제한 방지 (0.1초 대기)

**실행 방법**:
```bash
# 1회 수집 테스트
python data_collector.py

# 스케줄러 모드 (1시간마다)
RUN_DATA_COLLECTOR=true python data_collector.py

# Docker로 실행
docker run -d \
  --name crypto-data-collector \
  -e RUN_DATA_COLLECTOR="true" \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="..." \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  crypto-trading-bot:latest \
  python data_collector.py
```

---

### 3. 자동 파라미터 최적화 스케줄러
**파일**: `auto_optimizer.py`

- ✅ 7일마다 자동 파라미터 최적화
- ✅ 데이터베이스 저장된 캔들로 백테스팅
- ✅ 192개 파라미터 조합 그리드 서치
- ✅ 최적 파라미터 자동 저장 (is_active=1)
- ✅ 종합 점수 기반 선택 (수익률 40% + 승률 30% + 샤프비율 30%)

**최적화 파라미터**:
- quick_profit (0.5%, 0.8%, 1.0%, 1.2%)
- take_profit_1 (1.2%, 1.5%, 2.0%, 2.5%)
- stop_loss (-1.0%, -1.5%, -2.0%, -2.5%)
- trailing_stop_tight (0.2%, 0.3%, 0.5%)

**실행 방법**:
```bash
# 1회 최적화 테스트
python auto_optimizer.py

# 스케줄러 모드 (7일마다)
RUN_AUTO_OPTIMIZER=true MARKET=KRW-ETH python auto_optimizer.py

# Docker로 실행
docker run -d \
  --name crypto-auto-optimizer \
  -e RUN_AUTO_OPTIMIZER="true" \
  -e MARKET="KRW-ETH" \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="..." \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  crypto-trading-bot:latest \
  python auto_optimizer.py
```

---

### 4. 트레이딩 봇 데이터베이스 통합
**파일**: `telegram_bot.py`

- ✅ 시작 시 DB에서 최적 파라미터 자동 로드
- ✅ 매도 시 거래 기록 자동 저장
- ✅ 파라미터 로드 실패 시 기본값 사용 (안전성)
- ✅ DB 없이도 정상 작동 (선택적 기능)

**새로운 메서드**:
```python
def load_optimized_parameters(self):
    """DB에서 최적화된 파라미터 로드"""

def save_trade_to_db(self, trade_data):
    """거래 기록을 DB에 저장"""
```

**실행 예시**:
```python
# DB 사용
db = DatabaseManager(use_oracle=True)
bot = TradingBot(upbit, telegram, market="KRW-ETH", db=db)
bot.run()

# DB 미사용 (기존과 동일)
bot = TradingBot(upbit, telegram, market="KRW-ETH")
bot.run()
```

---

### 5. Docker & 배포 설정
**파일**: `Dockerfile`, `.github/workflows/deploy.yml`

- ✅ Oracle Instant Client 21.11 설치
- ✅ cx_Oracle 패키지 포함
- ✅ Wallet 디렉토리 마운트 지원
- ✅ GitHub Secrets에서 Wallet Base64 디코딩
- ✅ 환경변수로 DB 연결 정보 전달

**GitHub Secrets 추가**:
```
ORACLE_DB_USER          # ADMIN
ORACLE_DB_PASSWORD      # DB 비밀번호
ORACLE_DB_DSN           # cryptodb_medium
ORACLE_WALLET_BASE64    # Wallet.zip의 base64 인코딩
USE_ORACLE_DB           # true
```

**배포 시 자동 설정**:
- Wallet 파일 자동 압축 해제
- Oracle 환경변수 자동 설정
- TNS_ADMIN 자동 구성

---

## 🔄 전체 시스템 흐름

```
[1] 데이터 수집 (1시간마다)
    data_collector.py
    ↓
    상위 20개 코인 캔들 → Database

[2] 파라미터 최적화 (7일마다)
    auto_optimizer.py
    ↓
    DB 캔들 → 백테스팅 → 최적 파라미터 → Database

[3] 트레이딩 봇 (실시간)
    telegram_bot.py
    ↓
    DB 최적 파라미터 로드
    ↓
    매매 실행
    ↓
    거래 기록 → Database
```

---

## 📊 데이터 축적 효과

### Before (API만 사용)
- ❌ 최대 200개 캔들만 조회 가능
- ❌ 과거 데이터 제한적
- ❌ 파라미터 최적화 정확도 낮음
- ❌ 거래 기록 메모리에만 저장

### After (DB 통합)
- ✅ 무제한 과거 데이터 축적
- ✅ 30일+ 데이터로 정확한 최적화
- ✅ 거래 기록 영구 저장
- ✅ 성과 분석 및 리포트 가능
- ✅ 여러 코인의 히스토리 관리

---

## 🎯 사용 시나리오

### 시나리오 1: 로컬 개발 (SQLite)
```bash
# 로컬에서 SQLite로 테스트
USE_DB=true python run_multi_coin.py
```

### 시나리오 2: 프로덕션 (Oracle Cloud)
```bash
# Oracle Cloud VM에서 실행
USE_ORACLE_DB=true \
ORACLE_DB_USER=ADMIN \
ORACLE_DB_PASSWORD="..." \
ORACLE_DB_DSN=cryptodb_medium \
python run_multi_coin.py
```

### 시나리오 3: 3개 컨테이너 분산 실행
```bash
# 1. 트레이딩 봇
docker run -d --name crypto-bot ...

# 2. 데이터 수집기 (1시간마다)
docker run -d --name crypto-collector \
  -e RUN_DATA_COLLECTOR=true ...

# 3. 자동 최적화기 (7일마다)
docker run -d --name crypto-optimizer \
  -e RUN_AUTO_OPTIMIZER=true ...
```

---

## 🔍 성능 및 비용

### Oracle Always Free Tier 한도
- ✅ Autonomous Database: 2개 (1 OCPU, 20GB)
- ✅ 완전 무료 (Always Free)
- ✅ 상위 20개 코인 × 30일 데이터 충분히 저장 가능

### 예상 데이터량
- 15분봉: 20개 코인 × 96개/일 × 30일 = 57,600개 레코드
- 1시간봉: 20개 코인 × 24개/일 × 30일 = 14,400개 레코드
- 거래 기록: 하루 5-10건 × 30일 = 150-300개 레코드

**총 용량**: ~10MB (20GB 한도의 0.05%)

---

## 📝 다음 단계 (선택적 개선)

### 1. 대시보드 추가
- Grafana 연동
- 실시간 성과 차트
- 파라미터 변화 추이

### 2. 고급 분석
- 코인별 성과 비교
- 시간대별 수익률 분석
- 최적 파라미터 트렌드

### 3. 알림 확장
- 주간 성과 리포트 텔레그램 전송
- 파라미터 최적화 완료 알림
- 데이터 수집 실패 알림

---

## ✅ 완료 체크리스트

- [x] Oracle Cloud DB 연동 (`database_manager.py`)
- [x] SQLite 로컬 모드 (`database_manager.py`)
- [x] 자동 데이터 수집 (`data_collector.py`)
- [x] 자동 파라미터 최적화 (`auto_optimizer.py`)
- [x] 봇 DB 통합 (`telegram_bot.py`)
- [x] Docker Oracle Client (`Dockerfile`)
- [x] GitHub Actions 배포 (`deploy.yml`)
- [x] 설정 가이드 (`ORACLE_DB_SETUP.md`)
- [x] README 업데이트
- [x] Git 커밋 & 푸시

---

## 🚀 바로 시작하기

1. **Oracle Cloud DB 설정** (30분)
   - [ORACLE_DB_SETUP.md](ORACLE_DB_SETUP.md) 참고
   - Autonomous Database 생성
   - Wallet 다운로드

2. **GitHub Secrets 설정** (5분)
   - ORACLE_DB_USER
   - ORACLE_DB_PASSWORD
   - ORACLE_DB_DSN
   - ORACLE_WALLET_BASE64
   - USE_ORACLE_DB=true

3. **배포** (자동)
   ```bash
   git push origin main
   ```
   GitHub Actions가 자동으로 배포!

4. **데이터 수집 & 최적화 시작**
   ```bash
   # VM에 접속하여
   docker run -d --name crypto-collector -e RUN_DATA_COLLECTOR=true ...
   docker run -d --name crypto-optimizer -e RUN_AUTO_OPTIMIZER=true ...
   ```

---

## 🎉 완료!

이제 트레이딩 봇이:
- 📊 **1시간마다** 시장 데이터를 자동 수집
- 🔍 **7일마다** 파라미터를 자동 최적화
- ⚙️ **항상** 최적화된 파라미터로 거래
- 💾 **모든** 거래 기록을 영구 저장합니다!
