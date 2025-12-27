"""
전략 테스트 스크립트
실시간 시그널 확인 및 검증
"""
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators
from datetime import datetime


def test_trend_analysis(upbit, market="KRW-ETH"):
    """다중 시간대 추세 분석 테스트"""
    print(f"\n{'='*60}")
    print("📊 다중 시간대 추세 분석 테스트")
    print(f"{'='*60}\n")

    try:
        # 1시간봉 200개
        candles_1h = upbit.get_candles(market, "minutes", 60, 200)
        # 4시간봉 200개
        candles_4h = upbit.get_candles(market, "minutes", 240, 200)

        print(f"✅ 1시간봉: {len(candles_1h)}개")
        print(f"✅ 4시간봉: {len(candles_4h)}개\n")

        if len(candles_1h) < 50 or len(candles_4h) < 50:
            print("❌ 데이터 부족")
            return

        # 1시간 추세
        prices_1h = [c['trade_price'] for c in candles_1h]
        rsi_1h = TechnicalIndicators.calculate_rsi(prices_1h, 14)
        ma20_1h = sum(prices_1h[:20]) / 20
        ma50_1h = sum(prices_1h[:50]) / 50
        trend_1h = "up" if ma20_1h > ma50_1h and prices_1h[0] > ma20_1h else "down"

        # 4시간 추세
        prices_4h = [c['trade_price'] for c in candles_4h]
        rsi_4h = TechnicalIndicators.calculate_rsi(prices_4h, 14)
        ma20_4h = sum(prices_4h[:20]) / 20
        ma50_4h = sum(prices_4h[:50]) / 50
        trend_4h = "up" if ma20_4h > ma50_4h and prices_4h[0] > ma20_4h else "down"

        print("⏱️  1시간봉:")
        print(f"   추세: {'↑ 상승' if trend_1h == 'up' else '↓ 하락'}")
        print(f"   RSI: {rsi_1h:.1f}")
        print(f"   MA20: {ma20_1h:,.0f}원")
        print(f"   MA50: {ma50_1h:,.0f}원")
        print(f"   현재가: {prices_1h[0]:,.0f}원\n")

        print("⏱️  4시간봉:")
        print(f"   추세: {'↑ 상승' if trend_4h == 'up' else '↓ 하락'}")
        print(f"   RSI: {rsi_4h:.1f}")
        print(f"   MA20: {ma20_4h:,.0f}원")
        print(f"   MA50: {ma50_4h:,.0f}원")
        print(f"   현재가: {prices_4h[0]:,.0f}원\n")

        # 추세 상태 판단
        if trend_1h == "up" and trend_4h == "up":
            state = "🚀 강한 상승"
            buy_allowed = True
            rsi_threshold = 40
        elif trend_1h == "down" and trend_4h == "up":
            state = "📊 조정 (상승장 내)"
            buy_allowed = True
            rsi_threshold = 35
        elif trend_1h == "up" and trend_4h == "down":
            state = "⚡ 약한 반등"
            buy_allowed = True
            rsi_threshold = 30
        else:
            state = "🔻 강한 하락"
            buy_allowed = False
            rsi_threshold = 25

        print(f"📈 추세 상태: {state}")
        print(f"🎯 매수 허용: {'✅ 가능' if buy_allowed else '❌ 금지'}")
        print(f"🎯 RSI 기준: < {rsi_threshold}")

    except Exception as e:
        print(f"❌ 오류: {e}")


def test_signals(upbit, market="KRW-ETH"):
    """매매 신호 테스트"""
    print(f"\n{'='*60}")
    print("🔍 매매 신호 테스트")
    print(f"{'='*60}\n")

    try:
        # 15분봉 50개
        candles = upbit.get_candles(market, "minutes", 15, 50)

        if len(candles) < 50:
            print("❌ 데이터 부족")
            return

        prices = [c['trade_price'] for c in candles]
        volumes = [c['candle_acc_trade_volume'] for c in candles]

        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        upper, middle, lower = AdvancedIndicators.calculate_bollinger_bands(prices, 20, 2)
        vol_ma = AdvancedIndicators.calculate_volume_ma(volumes, 20)

        current_price = prices[0]
        current_vol = volumes[0]
        bb_pos = ((current_price - lower) / (upper - lower)) * 100

        print(f"💰 현재가: {current_price:,.0f}원\n")

        print("📊 15분봉 지표:")
        print(f"   RSI: {rsi:.1f}")
        print(f"   볼린저 위치: {bb_pos:.1f}%")
        print(f"   볼린저 상단: {upper:,.0f}원")
        print(f"   볼린저 중단: {middle:,.0f}원")
        print(f"   볼린저 하단: {lower:,.0f}원")
        print(f"   거래량 비율: {current_vol/vol_ma:.2f}x\n")

        # 매수 신호 체크 (예시)
        buy_conditions = []

        if rsi < 35:
            buy_conditions.append(f"✅ RSI < 35 ({rsi:.1f})")
        else:
            buy_conditions.append(f"❌ RSI < 35 ({rsi:.1f})")

        if current_price <= lower * 1.02:
            buy_conditions.append(f"✅ 가격 ≤ 볼린저 하단*1.02")
        else:
            buy_conditions.append(f"❌ 가격 ≤ 볼린저 하단*1.02")

        if current_vol >= vol_ma * 1.15:
            buy_conditions.append(f"✅ 거래량 ≥ 1.15배 ({current_vol/vol_ma:.2f}x)")
        else:
            buy_conditions.append(f"❌ 거래량 ≥ 1.15배 ({current_vol/vol_ma:.2f}x)")

        print("📋 매수 조건 (조정 추세 기준):")
        for cond in buy_conditions:
            print(f"   {cond}")

        # 매도 신호 체크
        print("\n📋 매도 조건:")
        if rsi > 70:
            print(f"   ✅ RSI > 70 ({rsi:.1f})")
        else:
            print(f"   ❌ RSI > 70 ({rsi:.1f})")

        if current_price >= upper * 0.99:
            print(f"   ✅ 가격 ≥ 볼린저 상단*0.99")
        else:
            print(f"   ❌ 가격 ≥ 볼린저 상단*0.99")

    except Exception as e:
        print(f"❌ 오류: {e}")


def test_api_connection(upbit):
    """API 연결 테스트"""
    print(f"\n{'='*60}")
    print("🔌 API 연결 테스트")
    print(f"{'='*60}\n")

    try:
        # 계좌 조회
        accounts = upbit.get_accounts()
        print(f"✅ 계좌 조회 성공: {len(accounts)}개 화폐\n")

        for acc in accounts:
            currency = acc['currency']
            balance = float(acc['balance'])
            if balance > 0:
                print(f"   {currency}: {balance:,.2f}")

        # 시세 조회
        ticker = upbit.get_current_price("KRW-ETH")
        print(f"\n✅ 시세 조회 성공")
        print(f"   ETH: {ticker['trade_price']:,.0f}원")
        print(f"   24h 변동: {ticker.get('signed_change_rate', 0)*100:+.2f}%")

    except Exception as e:
        print(f"❌ API 오류: {e}")


def test_all(access_key, secret_key):
    """모든 테스트 실행"""
    print(f"\n{'#'*60}")
    print(f"{'#'*60}")
    print("🧪 전략 테스트 시작")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    print(f"{'#'*60}")

    upbit = UpbitAPI(access_key, secret_key)

    # 1. API 연결 테스트
    test_api_connection(upbit)

    # 2. 추세 분석 테스트
    test_trend_analysis(upbit)

    # 3. 매매 신호 테스트
    test_signals(upbit)

    print(f"\n{'#'*60}")
    print("✅ 모든 테스트 완료")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    from config import get_config

    try:
        # .env 파일에서 설정 로드
        config = get_config()

        print("✅ 설정 로드 완료\n")

        test_all(config['upbit_access_key'], config['upbit_secret_key'])

    except Exception as e:
        print(f"❌ 설정 로드 실패: {e}")
        print("\n.env 파일을 확인해주세요.")
