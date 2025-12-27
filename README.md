# 🤖 Crypto Trading Bot
업비트(Upbit) 암호화폐 자동매매 봇 with 텔레그램 알림

## ✨ 주요 기능

- 🚀 **멀티 코인 모멘텀 전략** (모멘텀 강한 코인 자동 선택)
- 📊 **다중 시간대 추세 분석** (1H + 4H)
- 🎯 **다층 익절 시스템** (0.8%, 1.5%, 2.5%, 4.0%)
- 🛡️ **동적 트레일링 스톱** (0.3% 수익부터 작동)
- ⏰ **포지션 타임아웃** (3시간 자동 청산)
- 📱 **텔레그램 실시간 알림** (매수/매도/코인전환/상태)
- 🔄 **자동 배포** (GitHub Actions → Oracle Cloud)
- 🧪 **드라이런 모드** (실제 거래 없이 시뮬레이션)
- 📈 **백테스팅** (과거 데이터로 전략 검증)

## 🚀 빠른 시작

### 1. 로컬 테스트

```bash
# 저장소 클론
git clone https://github.com/YOUR_USERNAME/crypto_trading.git
cd crypto_trading

# 환경변수 설정
cp .env.example .env
# .env 파일 편집

# 단일 코인 모드
python run_dry_run.py

# 멀티 코인 모드 (모멘텀 자동 선택)
python run_multi_coin.py
```

### 2. 자동 배포

[DEPLOYMENT.md](DEPLOYMENT.md) 참고

## 📊 전략

### 🚀 멀티 코인 모멘텀

- **자동 코인 선택**: 거래량 상위 20개 중 모멘텀 점수 최고 코인
- **모멘텀 점수**: 가격변화(30점) + 거래량(30점) + RSI(20점) + 추세(20점)
- **자동 전환**: 10분마다 재평가, 더 나은 코인 발견 시 자동 전환

### 📈 다중 시간대 추세 분석

- **🚀 강한 상승** (1H↑ + 4H↑): RSI < 50
- **📊 조정** (1H↓ + 4H↑): RSI < 45
- **⚡ 약한 반등** (1H↑ + 4H↓): RSI < 40
- **🔻 강한 하락** (1H↓ + 4H↓): RSI < 30

### 🎯 다층 익절 시스템

- ⚡ 퀵익절: +0.8% (30분 이내)
- 1차 익절: +1.5%
- 2차 익절: +2.5%
- 최종 익절: +4.0%

### 🛡️ 리스크 관리

- 손절: -1.5%
- 동적 트레일링: 0.3%↑시 -0.3%, 0.8%↑시 -0.5%, 1.5%↑시 -0.8%
- 포지션 타임아웃: 3시간

## 📁 프로젝트 구조

```
crypto_trading/
├── telegram_bot.py       # 메인 트레이딩 봇
├── upbit_api.py          # 업비트 API 래퍼
├── trading_indicators.py # 기술적 지표
├── advanced_strategy.py  # 고급 전략
├── backtest.py           # 백테스팅 엔진
├── run_dry_run.py        # 드라이런 모드
├── test_5m.py            # 타임프레임 비교 테스트
├── config.py             # 환경변수 로더
├── Dockerfile            # Docker 이미지
├── .github/workflows/    # GitHub Actions
│   └── deploy.yml        # 자동 배포 워크플로우
└── DEPLOYMENT.md         # 배포 가이드
```

## 🛠️ 설정

### 필수 환경변수 (.env)

```bash
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
MARKET=KRW-ETH
CHECK_INTERVAL=300
```

## 📱 텔레그램 명령어

- `/status` - 현재 상태
- `/position` - 포지션 정보
- `/market` - 시장 현황
- `/trend` - 추세 분석
- `/report` - 일일 리포트
- `/help` - 도움말

## 🧪 테스팅

```bash
# 백테스트 (1시간봉)
python backtest.py

# 5분봉 vs 15분봉 비교
python test_5m.py

# 전략 테스트
python test_strategy.py

# 드라이런 모드
python run_dry_run.py
```

## ⚠️ 주의사항

- 이 봇은 교육 및 연구 목적으로 제작되었습니다
- 실제 거래 시 손실 위험이 있으니 신중하게 사용하세요
- 백테스팅 결과가 실제 거래 성과를 보장하지 않습니다
- 본인의 판단과 책임 하에 사용하세요

## 📄 라이센스

MIT License

## 🤝 기여

Issues와 Pull Requests를 환영합니다!

---
<!-- Auto-deployment test: 2024-12-27 -->
