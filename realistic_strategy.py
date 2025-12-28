"""
현실적인 초단타 전략
목표: 수수료 3-5배 (0.15~0.25%) 익절
손절: -0.15% 타이트 손절
"""
from datetime import datetime, timedelta

class RealisticScalpingStrategy:
    """현실적인 초단타 전략 (수수료 고려)"""

    def __init__(self):
        # === 핵심 파라미터 (현실적) ===
        self.target_profit = 0.0025  # 0.25% 목표 (수수료 5배)
        self.stop_loss = -0.0015     # -0.15% 손절 (타이트)

        # === 매수 조건 (매우 보수적) ===
        self.min_volume_krw = 100_000_000_000  # 1000억 이상 (유동성 필수)
        self.max_positions = 1  # 동시 포지션 1개만 (집중 투자)

        # === 빠른 익절 시스템 ===
        self.quick_exit_time = 120  # 2분 이내
        self.quick_exit_profit = 0.0015  # 0.15% (수수료 3배)

        # === 시간 기반 강제 청산 ===
        self.force_exit_time = 600  # 10분 초과 시 무조건 청산
        self.force_exit_min_profit = 0.0005  # 최소 0.05% 이상이면 익절

    def check_buy_signal(self, candles_1m):
        """
        매우 보수적인 매수 신호
        - 급락 후 즉시 반등 (V자 반등)
        - 5분 이내만 유효
        """
        if len(candles_1m) < 6:
            return None

        # 최근 5개 캔들의 변화율
        changes = []
        for i in range(5):
            change = ((candles_1m[i]['trade_price'] - candles_1m[i+1]['trade_price'])
                     / candles_1m[i+1]['trade_price']) * 100
            changes.append(change)

        # 패턴 감지: 급락 → 즉시 반등
        # [0]최신 [1] [2] [3] [4]오래됨

        # 조건 1: 2-3분 전에 -0.5% 이상 급락
        sharp_drop = any(c < -0.5 for c in changes[2:5])

        # 조건 2: 최근 2분 동안 반등 중 (양봉 2개 이상)
        recent_up = sum(1 for c in changes[0:2] if c > 0)

        # 조건 3: 현재 상승 모멘텀 (최신 캔들 양봉)
        current_up = changes[0] > 0.1

        if sharp_drop and recent_up >= 2 and current_up:
            # 추가 검증: 거래량 급증
            current_volume = candles_1m[0]['candle_acc_trade_price']
            avg_volume = sum(c['candle_acc_trade_price'] for c in candles_1m[1:6]) / 5

            volume_surge = current_volume > avg_volume * 1.5  # 50% 이상 증가

            if volume_surge:
                return {
                    'signal': 'buy',
                    'reason': 'V자 반등 (급락 후 즉시 회복)',
                    'confidence': 0.8,
                    'target_profit': self.target_profit,
                    'stop_loss': self.stop_loss
                }

        return None

    def check_sell_signal(self, position, current_price):
        """
        초단타 매도 조건
        1. 0.25% 목표 달성 → 즉시 익절
        2. -0.15% 손실 → 즉시 손절
        3. 2분 + 0.15% → 빠른 익절
        4. 10분 초과 + 0.05% 이상 → 강제 익절
        """
        buy_price = position['buy_price']
        buy_time = position['buy_time']

        profit_pct = ((current_price - buy_price) / buy_price) * 100
        hold_seconds = (datetime.now() - buy_time).total_seconds()

        # 1. 목표 달성
        if profit_pct >= self.target_profit * 100:
            return {
                'signal': 'sell',
                'reason': f'목표 달성 ({profit_pct:.2f}%)',
                'confidence': 1.0
            }

        # 2. 손절
        if profit_pct <= self.stop_loss * 100:
            return {
                'signal': 'sell',
                'reason': f'손절 ({profit_pct:.2f}%)',
                'confidence': 1.0
            }

        # 3. 빠른 익절 (2분 + 0.15%)
        if hold_seconds < self.quick_exit_time and profit_pct >= self.quick_exit_profit * 100:
            return {
                'signal': 'sell',
                'reason': f'빠른 익절 ({int(hold_seconds)}초, {profit_pct:.2f}%)',
                'confidence': 1.0
            }

        # 4. 강제 청산 (10분 초과)
        if hold_seconds > self.force_exit_time:
            if profit_pct >= self.force_exit_min_profit * 100:
                return {
                    'signal': 'sell',
                    'reason': f'시간 초과 익절 ({int(hold_seconds/60)}분, {profit_pct:.2f}%)',
                    'confidence': 0.9
                }
            else:
                # 10분 넘었는데 수익 없으면 무조건 청산
                return {
                    'signal': 'sell',
                    'reason': f'시간 초과 강제 청산 ({int(hold_seconds/60)}분, {profit_pct:.2f}%)',
                    'confidence': 1.0
                }

        return None


class SingleCoinFocusSelector:
    """단일 코인 집중 투자 선택기"""

    def __init__(self, upbit_api):
        self.upbit = upbit_api

    def get_best_single_coin(self):
        """
        가장 좋은 코인 1개만 선택
        - 거래량 1000억 이상
        - 변동성 3% 이상
        - 최근 급락 후 반등 중
        """
        # 1. 거래량 상위 10개
        markets = self.upbit.get_market_all()
        krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]

        tickers = self.upbit.get_ticker(krw_markets[:50])  # 상위 50개만

        # 2. 거래량 필터 (1000억 이상)
        high_volume = [
            t for t in tickers
            if t['acc_trade_price_24h'] >= 100_000_000_000
        ]

        if not high_volume:
            return None

        # 3. 변동성 필터 (당일 변동폭 3% 이상)
        volatile = [
            t for t in high_volume
            if abs(t['signed_change_rate']) * 100 >= 3.0
        ]

        if not volatile:
            # 변동성 낮으면 거래량 1위 선택
            volatile = [high_volume[0]]

        # 4. 점수 계산 (거래량 × 변동성)
        scored = []
        for ticker in volatile:
            volume_score = ticker['acc_trade_price_24h'] / 1_000_000_000_000  # 1조 기준
            volatility_score = abs(ticker['signed_change_rate']) * 100  # %

            total_score = volume_score * 0.4 + volatility_score * 0.6

            scored.append({
                'market': ticker['market'],
                'score': total_score,
                'volume': ticker['acc_trade_price_24h'],
                'volatility': volatility_score,
                'change_24h': ticker['signed_change_rate'] * 100
            })

        # 5. 점수 1위 반환
        scored.sort(key=lambda x: x['score'], reverse=True)

        best = scored[0]
        print(f"\n🎯 선택된 코인: {best['market']}")
        print(f"  거래량: {best['volume']/1e9:.0f}억원")
        print(f"  변동성: {best['volatility']:.2f}%")
        print(f"  24h 변화: {best['change_24h']:+.2f}%")
        print(f"  종합점수: {best['score']:.2f}")

        return best['market']


if __name__ == "__main__":
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 최적 코인 선택
    selector = SingleCoinFocusSelector(upbit)
    best_coin = selector.get_best_single_coin()

    # 전략 테스트
    strategy = RealisticScalpingStrategy()

    if best_coin:
        candles = upbit.get_candles(best_coin, "minutes", 1, 10)

        signal = strategy.check_buy_signal(candles)

        if signal:
            print(f"\n💰 매수 신호!")
            print(f"  사유: {signal['reason']}")
            print(f"  신뢰도: {signal['confidence']*100:.0f}%")
            print(f"  목표: +{signal['target_profit']*100:.2f}%")
            print(f"  손절: {signal['stop_loss']*100:.2f}%")
        else:
            print(f"\n⏸️ 대기")
