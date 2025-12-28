"""
이동평균 크로스오버 전략 (MA Crossover Strategy)
단기 MA가 장기 MA를 돌파하는 시점 포착
"""
from datetime import datetime


class MACrossoverStrategy:
    """이동평균 크로스오버 기반 매매 전략"""

    def __init__(self, fast_period=7, slow_period=25):
        """
        Args:
            fast_period: 단기 이동평균 기간 (기본 7)
            slow_period: 장기 이동평균 기간 (기본 25)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.last_signal = None  # 마지막 신호 (중복 방지)

    def calculate_ma(self, candles, period):
        """이동평균 계산"""
        if len(candles) < period:
            return None

        prices = [c['trade_price'] for c in candles[:period]]
        return sum(prices) / len(prices)

    def detect_crossover(self, candles):
        """
        크로스오버 감지

        Returns:
            {
                'signal': 'golden' | 'death' | None,
                'fast_ma': float,
                'slow_ma': float,
                'strength': float  # 0-1
            }
        """
        if len(candles) < self.slow_period + 1:
            return None

        # 현재 MA
        fast_ma_current = self.calculate_ma(candles, self.fast_period)
        slow_ma_current = self.calculate_ma(candles, self.slow_period)

        # 이전 MA (1캔들 전)
        fast_ma_prev = self.calculate_ma(candles[1:], self.fast_period)
        slow_ma_prev = self.calculate_ma(candles[1:], self.slow_period)

        if not all([fast_ma_current, slow_ma_current, fast_ma_prev, slow_ma_prev]):
            return None

        # 크로스오버 감지
        golden_cross = (fast_ma_prev <= slow_ma_prev and
                       fast_ma_current > slow_ma_current)
        death_cross = (fast_ma_prev >= slow_ma_prev and
                      fast_ma_current < slow_ma_current)

        # 신호 강도 계산 (MA 간격이 클수록 강함)
        gap_pct = abs(fast_ma_current - slow_ma_current) / slow_ma_current * 100

        signal = None
        if golden_cross:
            signal = 'golden'
        elif death_cross:
            signal = 'death'

        return {
            'signal': signal,
            'fast_ma': fast_ma_current,
            'slow_ma': slow_ma_current,
            'strength': min(gap_pct / 2.0, 1.0)  # 최대 1.0
        }

    def check_trading_opportunity(self, market, upbit, position=None):
        """
        MA 크로스오버 매매 기회 체크

        Returns:
            {
                'action': 'buy' | 'sell' | None,
                'reason': str,
                'confidence': float,
                'fast_ma': float,
                'slow_ma': float
            }
        """
        try:
            # 1분봉 데이터 (충분한 양 필요)
            candles = upbit.get_candles(market, "minutes", 1, self.slow_period + 10)

            if not candles or len(candles) < self.slow_period + 1:
                return None

            crossover = self.detect_crossover(candles)

            if not crossover or not crossover['signal']:
                return None

            current_price = candles[0]['trade_price']
            fast_ma = crossover['fast_ma']
            slow_ma = crossover['slow_ma']
            strength = crossover['strength']

            # === 골든 크로스 (매수) ===
            if crossover['signal'] == 'golden' and not position:
                # 중복 신호 방지
                if self.last_signal == 'golden':
                    return None

                self.last_signal = 'golden'

                # 현재가가 MA 위에 있어야 함 (확실한 상승)
                if current_price > fast_ma:
                    confidence = 0.75 + (strength * 0.25)  # 0.75 - 1.0

                    return {
                        'action': 'buy',
                        'reason': f'골든크로스 (MA{self.fast_period}/{self.slow_period})',
                        'confidence': confidence,
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'target_profit': 3.0,  # 3% 목표 (수수료 30배, 중기 추세)
                        'stop_loss': -1.2  # -1.2% 손절
                    }

            # === 데드 크로스 (매도) ===
            elif crossover['signal'] == 'death' and position:
                # 중복 신호 방지
                if self.last_signal == 'death':
                    return None

                self.last_signal = 'death'

                # 현재가가 MA 아래 있어야 함 (확실한 하락)
                if current_price < fast_ma:
                    buy_price = position.get('buy_price', current_price)
                    profit_rate = ((current_price - buy_price) / buy_price) * 100

                    confidence = 0.8 + (strength * 0.2)  # 0.8 - 1.0

                    return {
                        'action': 'sell',
                        'reason': f'데드크로스 ({profit_rate:.2f}%)',
                        'confidence': confidence,
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'target_profit': None,
                        'stop_loss': None
                    }

            return None

        except Exception as e:
            print(f"MA 크로스오버 체크 실패: {e}")
            return None


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    strategy = MACrossoverStrategy(fast_period=7, slow_period=25)

    # TOP 코인 크로스오버 기회 체크
    markets = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-SOL', 'KRW-DOGE']

    print("=" * 70)
    print("📈 MA 크로스오버 분석 (MA7/MA25)")
    print("=" * 70)

    for market in markets:
        print(f"\n{market}:")

        opportunity = strategy.check_trading_opportunity(market, upbit)

        if opportunity:
            action = opportunity['action'].upper()
            reason = opportunity['reason']
            confidence = opportunity['confidence'] * 100
            fast_ma = opportunity['fast_ma']
            slow_ma = opportunity['slow_ma']

            print(f"  {'💰 매수' if action == 'BUY' else '💸 매도'} 신호!")
            print(f"  사유: {reason}")
            print(f"  신뢰도: {confidence:.0f}%")
            print(f"  MA7: {fast_ma:,.0f}원")
            print(f"  MA25: {slow_ma:,.0f}원")
        else:
            print(f"  대기")
