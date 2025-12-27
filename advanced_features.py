"""
고급 트레이딩 기능
- 변동성 기반 포지션 사이징
- 시간대별 전략 조절
"""
from datetime import datetime
from trading_indicators import TechnicalIndicators


class VolatilityManager:
    """변동성 기반 포지션 사이징"""

    @staticmethod
    def calculate_atr(candles, period=14):
        """
        ATR (Average True Range) 계산

        Args:
            candles: 캔들 데이터
            period: ATR 기간
        """
        if len(candles) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i]['high_price']
            low = candles[i]['low_price']
            prev_close = candles[i-1]['trade_price']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return None

        atr = sum(true_ranges[:period]) / period
        return atr

    @staticmethod
    def get_position_size(krw_balance, current_price, atr, atr_threshold_low=2, atr_threshold_high=4):
        """
        변동성에 따른 포지션 크기 결정

        Args:
            krw_balance: 사용 가능한 KRW
            current_price: 현재가
            atr: ATR 값
            atr_threshold_low: 낮은 변동성 기준 (%)
            atr_threshold_high: 높은 변동성 기준 (%)

        Returns:
            투자할 금액 (KRW)
        """
        if not atr:
            return krw_balance  # ATR 없으면 전액

        # ATR을 %로 변환
        atr_pct = (atr / current_price) * 100

        # 변동성별 포지션 크기 조절
        if atr_pct < atr_threshold_low:
            # 낮은 변동성: 80-100% 투자
            position_ratio = 0.9
            risk_level = "낮음"
        elif atr_pct < atr_threshold_high:
            # 중간 변동성: 60-70% 투자
            position_ratio = 0.65
            risk_level = "중간"
        else:
            # 높은 변동성: 40-50% 투자
            position_ratio = 0.45
            risk_level = "높음"

        position_size = int(krw_balance * position_ratio)

        print(f"📊 변동성 분석:")
        print(f"  • ATR: {atr_pct:.2f}%")
        print(f"  • 리스크: {risk_level}")
        print(f"  • 투자비율: {position_ratio*100:.0f}%")
        print(f"  • 투자금액: {position_size:,}원 / {krw_balance:,}원")

        return position_size


class TimeBasedStrategy:
    """시간대별 전략 조절"""

    @staticmethod
    def get_trading_session(now=None):
        """
        현재 시간대 세션 판단

        Returns:
            {
                'session': 'asia' | 'europe' | 'us' | 'night',
                'volatility': 'low' | 'medium' | 'high',
                'aggression': 0.5 ~ 1.5
            }
        """
        if now is None:
            now = datetime.now()

        hour = now.hour

        # 한국 시간 기준
        if 9 <= hour < 12:
            # 아시아 시작 (한국/중국/일본 시장)
            return {
                'session': 'asia',
                'name': '아시아장',
                'volatility': 'medium',
                'aggression': 1.1,  # 약간 공격적
                'description': '변동성 증가, 적극 매매'
            }
        elif 14 <= hour < 18:
            # 유럽장
            return {
                'session': 'europe',
                'name': '유럽장',
                'volatility': 'medium',
                'aggression': 1.0,  # 보통
                'description': '안정적 거래'
            }
        elif 22 <= hour or hour < 2:
            # 미국장 (가장 활발)
            return {
                'session': 'us',
                'name': '미국장',
                'volatility': 'high',
                'aggression': 1.3,  # 매우 공격적
                'description': '최고 변동성, 기회 많음'
            }
        else:
            # 새벽/한산한 시간
            return {
                'session': 'night',
                'name': '한산한시간',
                'volatility': 'low',
                'aggression': 0.7,  # 보수적
                'description': '낮은 유동성, 신중'
            }

    @staticmethod
    def adjust_parameters(base_params, session_info):
        """
        시간대에 따라 파라미터 조절

        Args:
            base_params: 기본 파라미터
            session_info: get_trading_session() 결과
        """
        aggression = session_info['aggression']
        adjusted = base_params.copy()

        # 공격성에 따라 익절/손절 조정
        if aggression > 1.0:
            # 공격적: 익절 타이트하게, 더 많은 기회
            adjusted['quick_profit'] = base_params['quick_profit'] * 0.9
            adjusted['take_profit_1'] = base_params['take_profit_1'] * 0.95
            adjusted['rsi_buy'] = min(base_params.get('rsi_buy', 35) + 5, 45)
        elif aggression < 1.0:
            # 보수적: 익절 여유롭게, 선택적 진입
            adjusted['quick_profit'] = base_params['quick_profit'] * 1.15
            adjusted['take_profit_1'] = base_params['take_profit_1'] * 1.1
            adjusted['rsi_buy'] = max(base_params.get('rsi_buy', 35) - 5, 25)

        return adjusted

    @staticmethod
    def should_trade_now(min_volatility='low'):
        """
        현재 시간대에 거래해야 하는지 판단

        Args:
            min_volatility: 최소 변동성 요구 ('low', 'medium', 'high')
        """
        session = TimeBasedStrategy.get_trading_session()

        volatility_levels = {'low': 0, 'medium': 1, 'high': 2}
        current_level = volatility_levels.get(session['volatility'], 1)
        required_level = volatility_levels.get(min_volatility, 0)

        return current_level >= required_level, session


class AdvancedRiskManager:
    """고급 리스크 관리"""

    @staticmethod
    def calculate_kelly_criterion(win_rate, avg_win, avg_loss):
        """
        켈리 공식으로 최적 베팅 비율 계산

        Args:
            win_rate: 승률 (0-1)
            avg_win: 평균 수익률
            avg_loss: 평균 손실률 (양수)
        """
        if avg_loss == 0:
            return 0

        # Kelly % = W - [(1 - W) / R]
        # W = 승률, R = (평균수익 / 평균손실)
        r = avg_win / avg_loss
        kelly = win_rate - ((1 - win_rate) / r)

        # 켈리의 절반 사용 (보수적)
        kelly_half = max(0, min(kelly * 0.5, 1.0))

        return kelly_half

    @staticmethod
    def get_optimal_position_ratio(trade_history):
        """
        거래 기록을 바탕으로 최적 포지션 비율 계산

        Args:
            trade_history: 거래 내역 리스트
        """
        if len(trade_history) < 10:
            return 0.8  # 기본값

        # 최근 30개 거래 분석
        recent_trades = trade_history[-30:]

        wins = [t for t in recent_trades if t.get('profit', 0) > 0]
        losses = [t for t in recent_trades if t.get('profit', 0) <= 0]

        if not wins or not losses:
            return 0.8

        win_rate = len(wins) / len(recent_trades)
        avg_win = sum(t['profit_rate'] for t in wins) / len(wins)
        avg_loss = abs(sum(t['profit_rate'] for t in losses) / len(losses))

        kelly = AdvancedRiskManager.calculate_kelly_criterion(win_rate, avg_win, avg_loss)

        # 켈리 + 변동성 고려
        position_ratio = min(max(kelly, 0.4), 0.95)  # 40%-95% 범위

        print(f"📊 리스크 분석 (최근 {len(recent_trades)}회):")
        print(f"  • 승률: {win_rate*100:.1f}%")
        print(f"  • 평균수익: {avg_win*100:+.2f}%")
        print(f"  • 평균손실: {avg_loss*100:.2f}%")
        print(f"  • 켈리비율: {kelly*100:.1f}%")
        print(f"  • 권장포지션: {position_ratio*100:.0f}%")

        return position_ratio


if __name__ == "__main__":
    """테스트"""

    # 시간대별 전략 테스트
    print("=" * 60)
    print("⏰ 시간대별 전략 테스트")
    print("=" * 60)

    for hour in [10, 15, 23, 4]:
        test_time = datetime.now().replace(hour=hour, minute=0)
        session = TimeBasedStrategy.get_trading_session(test_time)

        print(f"\n{hour}:00 시")
        print(f"  • 세션: {session['name']}")
        print(f"  • 변동성: {session['volatility']}")
        print(f"  • 공격성: {session['aggression']}")
        print(f"  • 설명: {session['description']}")

    # 파라미터 조절 테스트
    print("\n" + "=" * 60)
    print("🎯 파라미터 조절 테스트")
    print("=" * 60)

    base_params = {
        'quick_profit': 0.008,
        'take_profit_1': 0.015,
        'rsi_buy': 35
    }

    for hour in [10, 23, 4]:
        test_time = datetime.now().replace(hour=hour, minute=0)
        session = TimeBasedStrategy.get_trading_session(test_time)
        adjusted = TimeBasedStrategy.adjust_parameters(base_params, session)

        print(f"\n{session['name']} (공격성: {session['aggression']})")
        print(f"  퀵익절: {base_params['quick_profit']*100:.1f}% → {adjusted['quick_profit']*100:.1f}%")
        print(f"  1차익절: {base_params['take_profit_1']*100:.1f}% → {adjusted['take_profit_1']*100:.1f}%")
        print(f"  RSI매수: {base_params['rsi_buy']} → {adjusted.get('rsi_buy', 35)}")
