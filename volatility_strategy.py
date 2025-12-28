"""
변동성 기반 스캘핑 전략
코인 시장의 높은 변동성을 활용한 단기 매매
"""
from datetime import datetime, timedelta


class VolatilityScalpingStrategy:
    """변동성 기반 스캘핑 전략"""

    def __init__(self):
        self.recent_trades = []  # 최근 거래 기록
        self.cooldown_period = 300  # 5분 쿨다운

    def calculate_volatility(self, candles, period=20):
        """변동성 계산 (ATR 기반)"""
        if len(candles) < period:
            return None

        # True Range 계산
        true_ranges = []
        for i in range(1, min(period, len(candles))):
            high = candles[i]['high_price']
            low = candles[i]['low_price']
            prev_close = candles[i-1]['trade_price']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        if not true_ranges:
            return None

        # ATR (Average True Range)
        atr = sum(true_ranges) / len(true_ranges)

        # 현재가 대비 ATR 비율
        current_price = candles[0]['trade_price']
        volatility_pct = (atr / current_price) * 100

        return {
            'atr': atr,
            'volatility_pct': volatility_pct,
            'is_high': volatility_pct > 2.0,  # 2% 이상이면 높은 변동성
            'is_very_high': volatility_pct > 3.5  # 3.5% 이상이면 매우 높음
        }

    def detect_momentum_spike(self, candles_1m, candles_5m):
        """급격한 모멘텀 변화 감지"""
        try:
            if len(candles_1m) < 5 or len(candles_5m) < 2:
                return None

            # 1분봉: 최근 5개의 가격 변화율
            recent_changes = []
            for i in range(min(5, len(candles_1m)-1)):
                change = ((candles_1m[i]['trade_price'] - candles_1m[i+1]['trade_price'])
                         / candles_1m[i+1]['trade_price']) * 100
                recent_changes.append(change)

            # 5분봉: 최근 2개의 가격 변화율
            change_5m = ((candles_5m[0]['trade_price'] - candles_5m[1]['trade_price'])
                        / candles_5m[1]['trade_price']) * 100

            # 급등 감지 (1분봉에서 연속 상승)
            consecutive_up = sum(1 for c in recent_changes if c > 0)
            strong_up = sum(1 for c in recent_changes if c > 0.5)

            # 급락 감지 (1분봉에서 연속 하락)
            consecutive_down = sum(1 for c in recent_changes if c < 0)
            strong_down = sum(1 for c in recent_changes if c < -0.5)

            return {
                'spike_up': consecutive_up >= 4 or strong_up >= 3,
                'spike_down': consecutive_down >= 4 or strong_down >= 3,
                'change_1m_avg': sum(recent_changes) / len(recent_changes),
                'change_5m': change_5m,
                'strong_momentum': abs(change_5m) > 2.0
            }

        except Exception as e:
            print(f"모멘텀 스파이크 감지 실패: {e}")
            return None

    def check_scalping_opportunity(self, market, upbit, position=None):
        """스캘핑 기회 체크

        Returns:
            {
                'action': 'buy' | 'sell' | None,
                'reason': str,
                'confidence': float (0-1),
                'target_profit': float,
                'stop_loss': float
            }
        """
        try:
            # 쿨다운 체크 (같은 코인 반복 매매 방지)
            last_trade = self._get_last_trade(market)
            if last_trade:
                time_since = (datetime.now() - last_trade['time']).total_seconds()
                if time_since < self.cooldown_period:
                    return None

            # 캔들 데이터
            candles_1m = upbit.get_candles(market, "minutes", 1, 30)
            candles_5m = upbit.get_candles(market, "minutes", 5, 20)

            if not candles_1m or not candles_5m:
                return None

            # 변동성 분석
            volatility = self.calculate_volatility(candles_1m, 20)
            if not volatility:
                return None

            # 모멘텀 스파이크 감지
            momentum = self.detect_momentum_spike(candles_1m, candles_5m)
            if not momentum:
                return None

            current_price = candles_1m[0]['trade_price']

            # === 매수 기회 (공격적 스캘핑) ===
            if not position:
                # 조건 1: 급락 후 반등 (가장 일반적인 스캘핑 패턴)
                # - 최근 1분봉 3개 이상 하락 후 상승 전환
                if (momentum['spike_down'] and momentum['change_1m_avg'] > -0.5):
                    return {
                        'action': 'buy',
                        'reason': '급락 후 반등 진입',
                        'confidence': 0.7 if volatility['is_high'] else 0.6,
                        'target_profit': 1.2,  # 1.2% 목표
                        'stop_loss': -0.8  # -0.8% 손절
                    }

                # 조건 2: 상승 모멘텀 추세추종
                # - 2개 이상 연속 상승 (조건 완화)
                if momentum['spike_up']:
                    return {
                        'action': 'buy',
                        'reason': '상승 모멘텀 추세추종',
                        'confidence': 0.75,
                        'target_profit': 1.5,  # 1.5% 목표
                        'stop_loss': -0.8  # -0.8% 손절
                    }

                # 조건 3: 단순 변동성 매수 (가장 공격적)
                # - 1분 평균 변화율이 양수이고 5분 변화율도 양수
                if (momentum['change_1m_avg'] > 0.2 and
                    momentum['change_5m'] > 0.5):
                    return {
                        'action': 'buy',
                        'reason': '양봉 변동성 매수',
                        'confidence': 0.65,
                        'target_profit': 1.0,  # 1.0% 목표
                        'stop_loss': -0.7  # -0.7% 손절
                    }

                # 조건 4: 반대 방향 전환 포착
                # - 5분봉 하락 중 1분봉 반등
                if (momentum['change_5m'] < -0.5 and
                    momentum['change_1m_avg'] > 0.3):
                    return {
                        'action': 'buy',
                        'reason': '하락 중 반등 포착',
                        'confidence': 0.7,
                        'target_profit': 1.3,  # 1.3% 목표
                        'stop_loss': -0.8  # -0.8% 손절
                    }

            # === 매도 기회 (포지션 있을 때) ===
            else:
                buy_price = position['buy_price']
                profit_rate = ((current_price - buy_price) / buy_price) * 100
                hold_minutes = (datetime.now() - position['buy_time']).total_seconds() / 60

                # 조건 1: 목표 수익 달성
                target = position.get('target_profit', 1.5)
                if profit_rate >= target:
                    return {
                        'action': 'sell',
                        'reason': f'목표 수익 달성 ({profit_rate:.2f}% >= {target:.2f}%)',
                        'confidence': 1.0,
                        'target_profit': None,
                        'stop_loss': None
                    }

                # 조건 2: 손절
                stop_loss = position.get('stop_loss', -1.5)
                if profit_rate <= stop_loss:
                    return {
                        'action': 'sell',
                        'reason': f'손절 ({profit_rate:.2f}% <= {stop_loss:.2f}%)',
                        'confidence': 1.0,
                        'target_profit': None,
                        'stop_loss': None
                    }

                # 조건 3: 급등 후 급락 조짐 (이익 보호)
                if (profit_rate > 0.5 and  # 최소 0.5% 이익
                    momentum['spike_down'] and
                    hold_minutes > 3):  # 최소 3분 보유

                    return {
                        'action': 'sell',
                        'reason': f'급락 조짐 - 이익 보호 ({profit_rate:.2f}%)',
                        'confidence': 0.8,
                        'target_profit': None,
                        'stop_loss': None
                    }

                # 조건 4: 시간 기반 청산 (15분 이상 보유 + 미미한 수익)
                if (hold_minutes > 15 and
                    -0.3 < profit_rate < 0.5):

                    return {
                        'action': 'sell',
                        'reason': f'시간 청산 ({hold_minutes:.0f}분 보유, {profit_rate:.2f}%)',
                        'confidence': 0.6,
                        'target_profit': None,
                        'stop_loss': None
                    }

            return None

        except Exception as e:
            print(f"스캘핑 기회 체크 실패: {e}")
            return None

    def _get_last_trade(self, market):
        """특정 코인의 마지막 거래 조회"""
        for trade in reversed(self.recent_trades):
            if trade['market'] == market:
                return trade
        return None

    def record_trade(self, market, action, price):
        """거래 기록"""
        self.recent_trades.append({
            'market': market,
            'action': action,
            'price': price,
            'time': datetime.now()
        })

        # 최근 50개만 유지
        if len(self.recent_trades) > 50:
            self.recent_trades = self.recent_trades[-50:]


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    strategy = VolatilityScalpingStrategy()

    # TOP 코인 스캘핑 기회 체크
    markets = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-SOL', 'KRW-DOGE']

    print("=" * 70)
    print("🎯 변동성 스캘핑 기회 분석")
    print("=" * 70)

    for market in markets:
        print(f"\n{market}:")

        opportunity = strategy.check_scalping_opportunity(market, upbit)

        if opportunity:
            action = opportunity['action'].upper()
            reason = opportunity['reason']
            confidence = opportunity['confidence'] * 100

            print(f"  {'💰 매수' if action == 'BUY' else '💸 매도'} 기회!")
            print(f"  사유: {reason}")
            print(f"  신뢰도: {confidence:.0f}%")

            if opportunity['target_profit']:
                print(f"  목표 수익: +{opportunity['target_profit']:.2f}%")
            if opportunity['stop_loss']:
                print(f"  손절: {opportunity['stop_loss']:.2f}%")
        else:
            print(f"  대기")
