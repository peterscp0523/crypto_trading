"""
하락장 대응 전략
업비트는 숏이 불가능하므로 역발상 전략 사용
"""
from datetime import datetime, timedelta


class BearMarketStrategy:
    """하락장 전용 전략"""

    def __init__(self):
        # 하락장 감지 임계값
        self.bear_market_threshold = -0.03  # -3% 이상 하락
        self.oversold_rsi = 25  # RSI 25 이하 (극도의 과매도)

    def detect_market_trend(self, candles_1h):
        """
        시장 추세 감지

        Returns:
            'bull': 상승장
            'bear': 하락장
            'sideways': 횡보장
        """
        if len(candles_1h) < 24:
            return 'sideways'

        # 24시간 변화율
        change_24h = ((candles_1h[0]['trade_price'] - candles_1h[23]['trade_price'])
                     / candles_1h[23]['trade_price']) * 100

        # 최근 6시간 변화율
        change_6h = ((candles_1h[0]['trade_price'] - candles_1h[5]['trade_price'])
                    / candles_1h[5]['trade_price']) * 100

        # 하락장 판정
        if change_24h < -3.0 and change_6h < -1.5:
            return 'bear'
        # 상승장 판정
        elif change_24h > 3.0 and change_6h > 1.5:
            return 'bull'
        else:
            return 'sideways'

    def find_bounce_opportunity(self, market, upbit):
        """
        하락장에서 반등 기회 포착
        - 급락 후 과매도 구간에서 매수
        - 빠른 반등 수익 (데드캣 바운스)
        """
        try:
            # 1시간봉으로 추세 확인
            candles_1h = upbit.get_candles(market, "minutes", 60, 24)
            # 1분봉으로 진입 타이밍
            candles_1m = upbit.get_candles(market, "minutes", 1, 30)

            if not candles_1h or not candles_1m:
                return None

            trend = self.detect_market_trend(candles_1h)

            # 하락장이 아니면 일반 전략 사용
            if trend != 'bear':
                return None

            # === 하락장 역발상 매수 조건 ===
            current_price = candles_1m[0]['trade_price']

            # 1. 급락 확인 (최근 1시간 -2% 이상)
            change_1h = ((candles_1m[0]['trade_price'] - candles_1m[29]['trade_price'])
                        / candles_1m[29]['trade_price']) * 100

            if change_1h > -2.0:
                return None  # 충분히 떨어지지 않음

            # 2. 과매도 확인 (RSI)
            rsi = self._calculate_rsi(candles_1m, period=14)

            if rsi is None or rsi > 30:
                return None  # 충분히 과매도 아님

            # 3. 반등 시작 확인 (최근 3분 연속 상승)
            recent_changes = []
            for i in range(3):
                change = ((candles_1m[i]['trade_price'] - candles_1m[i+1]['trade_price'])
                         / candles_1m[i+1]['trade_price']) * 100
                recent_changes.append(change)

            # 3개 중 2개 이상 양봉
            bounce_candles = sum(1 for c in recent_changes if c > 0)

            if bounce_candles >= 2:
                return {
                    'action': 'buy',
                    'reason': f'하락장 반등 ({change_1h:.1f}%, RSI {rsi:.0f})',
                    'confidence': 0.65,
                    'target_profit': 0.015,  # 1.5% 목표 (반등은 짧음)
                    'stop_loss': -0.005,  # -0.5% 손절 (매우 타이트)
                    'strategy': 'bear_bounce'
                }

            return None

        except Exception as e:
            print(f"하락장 기회 체크 실패: {e}")
            return None

    def _calculate_rsi(self, candles, period=14):
        """RSI 계산"""
        if len(candles) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(period):
            change = candles[i]['trade_price'] - candles[i+1]['trade_price']
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def should_avoid_trading(self, market, upbit):
        """
        거래 회피 조건 (극단적 하락장)
        - 너무 급격한 하락 시 매수 금지
        - 시장 전체가 패닉 상태
        """
        try:
            candles_1h = upbit.get_candles(market, "minutes", 60, 6)

            if not candles_1h:
                return False

            # 최근 6시간 변화율
            change_6h = ((candles_1h[0]['trade_price'] - candles_1h[5]['trade_price'])
                        / candles_1h[5]['trade_price']) * 100

            # -5% 이상 급락 시 거래 중지
            if change_6h < -5.0:
                print(f"⚠️ 극단적 하락장 감지 ({change_6h:.1f}%) - 거래 회피")
                return True

            return False

        except Exception as e:
            print(f"거래 회피 체크 실패: {e}")
            return False


class StableCoinHedging:
    """
    USDT 헷지 전략
    하락장에서 원화를 USDT로 교환하여 하락 회피
    """

    def __init__(self, upbit_api):
        self.upbit = upbit_api

    def should_convert_to_usdt(self, current_positions):
        """
        USDT 전환 조건
        - 시장 전체가 하락장
        - 현재 포지션 손실 중
        """
        try:
            # 비트코인 추세 확인 (시장 대표)
            btc_candles = self.upbit.get_candles("KRW-BTC", "minutes", 60, 24)

            if not btc_candles:
                return False

            # 24시간 BTC 변화율
            btc_change_24h = ((btc_candles[0]['trade_price'] - btc_candles[23]['trade_price'])
                             / btc_candles[23]['trade_price']) * 100

            # BTC -3% 이상 하락 = 전체 시장 하락
            if btc_change_24h < -3.0:
                print(f"⚠️ 시장 하락장 감지 (BTC {btc_change_24h:.1f}%)")
                print(f"💡 권장: USDT 전환 고려")
                return True

            return False

        except Exception as e:
            print(f"USDT 전환 체크 실패: {e}")
            return False

    def convert_to_usdt(self, krw_amount):
        """
        원화 → USDT 전환
        하락장에서 자산 보호
        """
        try:
            print(f"💱 USDT 전환 시도: {krw_amount:,.0f}원")

            result = self.upbit.order_market_buy("KRW-USDT", krw_amount)

            if result and 'uuid' in result:
                print(f"✅ USDT 전환 완료")
                return True
            else:
                print(f"❌ USDT 전환 실패: {result}")
                return False

        except Exception as e:
            print(f"❌ USDT 전환 오류: {e}")
            return False

    def convert_to_krw(self, usdt_amount):
        """
        USDT → 원화 전환
        하락장 종료 후 복귀
        """
        try:
            print(f"💱 원화 전환 시도: {usdt_amount:.4f} USDT")

            result = self.upbit.order_market_sell("KRW-USDT", usdt_amount)

            if result and 'uuid' in result:
                print(f"✅ 원화 전환 완료")
                return True
            else:
                print(f"❌ 원화 전환 실패: {result}")
                return False

        except Exception as e:
            print(f"❌ 원화 전환 오류: {e}")
            return False


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 하락장 전략 테스트
    bear_strategy = BearMarketStrategy()

    markets = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP']

    print("=== 하락장 반등 기회 분석 ===\n")

    for market in markets:
        print(f"{market}:")

        # 거래 회피 체크
        if bear_strategy.should_avoid_trading(market, upbit):
            print("  ⚠️ 거래 회피 권장\n")
            continue

        # 반등 기회 체크
        opportunity = bear_strategy.find_bounce_opportunity(market, upbit)

        if opportunity:
            print(f"  💰 {opportunity['action'].upper()} 기회!")
            print(f"  사유: {opportunity['reason']}")
            print(f"  신뢰도: {opportunity['confidence']*100:.0f}%")
            print(f"  목표: +{opportunity['target_profit']*100:.2f}%")
            print(f"  손절: {opportunity['stop_loss']*100:.2f}%")
        else:
            print(f"  대기")

        print()

    # USDT 헷지 테스트
    print("\n=== USDT 헷지 분석 ===\n")
    hedge_strategy = StableCoinHedging(upbit)

    if hedge_strategy.should_convert_to_usdt({}):
        print("💡 USDT 전환 권장!")
    else:
        print("✅ 현재 시장 양호, USDT 불필요")
