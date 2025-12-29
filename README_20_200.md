# 업비트 20/200 SMA 자동매매 봇

20일/200일 단순 이동평균선(SMA) 기반 자동매매 시스템

## 🎯 전략 개요

### 핵심 원칙
- **추세 구간에서만 거래**: 횡보장 완전 배제
- **작게 지고, 크게 먹는다**: 손익비 2:1+ 목표
- **부분 익절 전략**: 수익 극대화

### 매수 조건 (모두 충족 필요)
1. 20MA 명확한 상승 중 (기울기 0.2% 이상)
2. 가격 > 200MA (구조적 상승 바이어스)
3. 20MA 근처 (±3% 이내)

### 매도 조건
1. **손절**: -0.7% (빠른 손절)
2. **부분 익절**: +1.5%에서 50% 청산
3. **최종 익절**: +3% 또는 20MA 이탈
4. **긴급**: 추세 전환 시 즉시 청산

## 📁 파일 구조

```
crypto_trading/
├── upbit_coin_scanner_20_200.py   # 코인 스캐너
├── upbit_20_200_bot.py            # 트레이딩 봇
├── upbit_api.py                   # 업비트 API 래퍼
├── coin_scanner_20_200.py         # 바이낸스 스캐너 (백테스팅용)
├── altcoin_volatility_backtest.py # 백테스팅 엔진
├── Dockerfile                     # Docker 이미지
├── requirements.txt               # Python 패키지
└── .env.example                   # 환경변수 예시
```

## 🚀 사용 방법

### 1. 코인 스캐너 (전략 조건 충족 코인 찾기)

```bash
# 1회 스캔 (1분봉)
python3 upbit_coin_scanner_20_200.py once 1

# 5분봉으로 스캔
python3 upbit_coin_scanner_20_200.py once 5

# 지속 모니터링 (60초 간격)
python3 upbit_coin_scanner_20_200.py monitor 1
```

### 2. 백테스팅 (바이낸스 데이터)

```bash
# 1분봉 60일 백테스트
python3 altcoin_volatility_backtest.py 1m 60

# 5분봉 30일 백테스트
python3 altcoin_volatility_backtest.py 5m 30
```

### 3. 트레이딩 봇 실행

#### 로컬 실행

```bash
# 시뮬레이션 모드 (1분봉)
python3 upbit_20_200_bot.py 1

# 실거래 모드 (주의!)
python3 upbit_20_200_bot.py live 1
```

#### Docker 실행

```bash
# 이미지 빌드
docker build -t crypto-trading-bot:latest .

# 컨테이너 실행 (시뮬레이션)
docker run -d \
  --name crypto-bot \
  --restart unless-stopped \
  -e UPBIT_ACCESS_KEY="your_key" \
  -e UPBIT_SECRET_KEY="your_secret" \
  -e TELEGRAM_TOKEN="your_token" \
  -e TELEGRAM_CHAT_ID="your_chat_id" \
  crypto-trading-bot:latest
```

### 4. Oracle Cloud 자동 배포

```bash
# main 브랜치에 push하면 자동 배포
git add .
git commit -m "Update bot"
git push origin main
```

GitHub Actions가 자동으로:
1. Docker 이미지 빌드
2. Oracle Cloud에 전송
3. 기존 컨테이너 교체
4. 새 봇 시작

## 🔧 환경 설정

### 필수 환경변수

```.env
# 업비트 API (https://upbit.com/mypage/open_api_management)
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key

# 텔레그램 (@BotFather에서 봇 생성)
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### GitHub Secrets 설정

Oracle Cloud 배포를 위해 필요한 Secrets:

```
ORACLE_HOST          # Oracle Cloud 인스턴스 IP
ORACLE_USERNAME      # SSH 사용자명
ORACLE_SSH_KEY       # SSH private key

UPBIT_ACCESS_KEY     # 업비트 API 키
UPBIT_SECRET_KEY     # 업비트 Secret
TELEGRAM_TOKEN       # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID     # 텔레그램 채팅 ID
```

## 📊 백테스트 결과

### GMT/USDT (바이낸스 1분봉, 60일)
- **승률**: 54.2% (13승/24거래)
- **손익비**: 2.59 (목표 2.0 초과 ✅)
- **수익률**: +5.19% vs Buy & Hold -28.60%
- **평균 보유**: 4.8분

### UNI/USDT (바이낸스 1분봉, 60일)
- **승률**: 61.1% (11승/18거래)
- **손익비**: 2.33
- **수익률**: +5.82%
- **평균 수익**: +0.99%

## 🔍 봇 작동 흐름

```
1. 코인 스캐너 실행
   └─> 전체 KRW 마켓 스캔
   └─> 거래량 상위 30개 선정
   └─> 전략 조건 체크
   └─> 최고 점수 코인 선택

2. 매수 신호 재확인
   └─> 20MA 상승 (0.2%+)
   └─> 가격 > 200MA
   └─> 20MA 근처 (±3%)

3. 매수 실행
   └─> 잔고의 95% 투자
   └─> 텔레그램 알림

4. 포지션 모니터링
   └─> 1~3초마다 가격 체크
   └─> 손절/익절 조건 확인

5. 매도 실행
   ├─> 손절: -0.7%
   ├─> 부분익절: +1.5% (50%)
   └─> 최종익절: +3%

6. 포지션 청산 후
   └─> 10초 대기
   └─> 1번으로 돌아가 재스캔
```

## ⚙️ 파라미터 조정

### 봇 파라미터 (upbit_20_200_bot.py)

```python
# 전략 파라미터
self.stop_loss_pct = -0.7        # 손절
self.partial_profit_pct = 1.5    # 부분 익절
self.final_profit_pct = 3.0      # 최종 익절

# 스캐너 설정
min_volume_krw=10_000_000_000    # 최소 거래대금 100억원
timeframe=1                      # 타임프레임 (분)
```

### 스캐너 파라미터 (upbit_coin_scanner_20_200.py)

```python
# 전략 조건
slope > 0.002           # 20MA 기울기 0.2% 이상
distance <= 3.0         # 20MA 거리 ±3% 이내
above_200ma = True      # 가격 > 200MA
```

## 📈 성능 모니터링

### 로그 확인

```bash
# Docker 로그 실시간 확인
docker logs -f crypto-trading-bot

# 최근 100줄
docker logs --tail 100 crypto-trading-bot
```

### 텔레그램 알림

봇이 다음 상황에서 자동 알림:
- ✅ 봇 시작/종료
- 🎯 최적 코인 발견
- 🟢 매수 체결
- 🔴 매도 체결 (손절/익절)
- ❌ 오류 발생

## 🛡️ 리스크 관리

### 안전 장치
1. **손절 -0.7%**: 빠른 손절로 손실 제한
2. **부분 익절**: 수익 일부 확보 후 나머지는 추적
3. **횡보장 필터**: 20MA 기울기 0.2% 미만 시 거래 금지
4. **과확장 회피**: 20MA에서 ±3% 벗어나면 진입 금지

### 주의사항
- ⚠️ **실거래 전 반드시 시뮬레이션 테스트**
- ⚠️ **API 키 보안 관리 (GitHub Secrets 사용)**
- ⚠️ **초기 자본은 손실 가능한 금액으로**
- ⚠️ **봇은 24/7 실행되므로 모니터링 필요**

## 📝 업데이트 이력

### 2025-12-29
- ✅ 업비트 20/200 SMA 봇 구현
- ✅ 코인 스캐너 통합
- ✅ 부분 익절 전략 적용
- ✅ 텔레그램 알림 시스템
- ✅ Oracle Cloud 자동 배포

## 🔗 참고

- [업비트 API 문서](https://docs.upbit.com/)
- [바이낸스 API 문서](https://binance-docs.github.io/apidocs/)
- [CCXT 라이브러리](https://github.com/ccxt/ccxt)
