"""
시장 상태 감지 모듈 (Tier 3 개선)
전체 시장의 강세/약세/횡보 상태를 판단하여 거래 전략 조정
"""
from datetime import datetime
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators


class MarketRegimeDetector:
    """시장 상태 감지기"""

    def __init__(self, upbit):
        self.upbit = upbit
        self.last_check_time = None
        self.current_regime = None
        self.check_interval = 600  # 10분마다 체크

    def detect_market_regime(self):
        """
        시장 전체 상태 감지

        Returns:
            dict: {
                'regime': 'bull' | 'bear' | 'sideways',
                'strength': 0-100 (신뢰도),
                'btc_trend': 'up' | 'down' | 'flat',
                'market_sentiment': 0-100,
                'recommendation': str
            }
        """
        try:
            # 비트코인 추세 분석 (시장 대표)
            btc_candles_1h = self.upbit.get_candles("KRW-BTC", "minutes", 60, 100)
            btc_candles_4h = self.upbit.get_candles("KRW-BTC", "minutes", 240, 100)

            if not btc_candles_1h or not btc_candles_4h:
                return None

            # BTC 1시간 분석
            btc_prices_1h = [c['trade_price'] for c in btc_candles_1h]
            btc_rsi_1h = TechnicalIndicators.calculate_rsi(btc_prices_1h, 14)
            btc_ma20_1h = sum(btc_prices_1h[:20]) / 20
            btc_ma50_1h = sum(btc_prices_1h[:50]) / 50

            # BTC 4시간 분석
            btc_prices_4h = [c['trade_price'] for c in btc_candles_4h]
            btc_rsi_4h = TechnicalIndicators.calculate_rsi(btc_prices_4h, 14)
            btc_ma20_4h = sum(btc_prices_4h[:20]) / 20
            btc_ma50_4h = sum(btc_prices_4h[:50]) / 50

            # 주요 알트코인 추세 분석
            major_alts = ['KRW-ETH', 'KRW-XRP', 'KRW-SOL', 'KRW-ADA']
            alt_trends = []

            for market in major_alts:
                try:
                    candles = self.upbit.get_candles(market, "minutes", 60, 50)
                    if candles and len(candles) >= 50:
                        prices = [c['trade_price'] for c in candles]
                        ma20 = sum(prices[:20]) / 20
                        ma50 = sum(prices[:50]) / 50
                        trend = "up" if ma20 > ma50 else "down"
                        alt_trends.append(trend)
                except:
                    pass

            # === 시장 상태 판단 ===
            score_bull = 0
            score_bear = 0

            # 1. BTC 추세 (40점)
            if btc_ma20_1h > btc_ma50_1h and btc_ma20_4h > btc_ma50_4h:
                score_bull += 40
            elif btc_ma20_1h < btc_ma50_1h and btc_ma20_4h < btc_ma50_4h:
                score_bear += 40
            elif btc_ma20_1h > btc_ma50_1h:
                score_bull += 20
            else:
                score_bear += 20

            # 2. BTC RSI (30점)
            if btc_rsi_1h > 50 and btc_rsi_4h > 50:
                score_bull += 30
            elif btc_rsi_1h < 50 and btc_rsi_4h < 50:
                score_bear += 30
            else:
                score_bull += 15
                score_bear += 15

            # 3. 알트코인 동조화 (30점)
            alt_up = alt_trends.count("up")
            alt_down = alt_trends.count("down")

            if alt_up > alt_down:
                score_bull += 30 * (alt_up / len(alt_trends))
                score_bear += 30 * (alt_down / len(alt_trends))
            else:
                score_bear += 30 * (alt_down / len(alt_trends))
                score_bull += 30 * (alt_up / len(alt_trends))

            # === 최종 판단 ===
            total_score = score_bull + score_bear
            bull_pct = (score_bull / total_score) * 100 if total_score > 0 else 50
            bear_pct = (score_bear / total_score) * 100 if total_score > 0 else 50

            if bull_pct > 65:
                regime = 'bull'
                strength = bull_pct
                recommendation = "공격적 매수, 포지션 확대"
            elif bear_pct > 65:
                regime = 'bear'
                strength = bear_pct
                recommendation = "보수적 매수, 포지션 축소"
            else:
                regime = 'sideways'
                strength = 100 - abs(bull_pct - bear_pct)
                recommendation = "중립 전략, 빠른 익절"

            # BTC 추세
            if btc_ma20_1h > btc_ma50_1h:
                btc_trend = 'up'
            elif btc_ma20_1h < btc_ma50_1h:
                btc_trend = 'down'
            else:
                btc_trend = 'flat'

            result = {
                'regime': regime,
                'strength': strength,
                'btc_trend': btc_trend,
                'btc_rsi_1h': btc_rsi_1h,
                'btc_rsi_4h': btc_rsi_4h,
                'market_sentiment': bull_pct,
                'bull_score': score_bull,
                'bear_score': score_bear,
                'alt_up_ratio': alt_up / len(alt_trends) if alt_trends else 0,
                'recommendation': recommendation,
                'timestamp': datetime.now()
            }

            self.current_regime = result
            self.last_check_time = datetime.now()

            return result

        except Exception as e:
            print(f"시장 상태 감지 실패: {e}")
            return None

    def get_regime_adjusted_params(self, base_params):
        """
        시장 상태에 따라 파라미터 조정

        Args:
            base_params: dict with keys like 'position_size', 'stop_loss', 'take_profit'

        Returns:
            dict: 조정된 파라미터
        """
        if not self.current_regime:
            self.detect_market_regime()

        if not self.current_regime:
            return base_params

        regime = self.current_regime['regime']
        adjusted = base_params.copy()

        if regime == 'bull':
            # 강세장: 공격적
            adjusted['position_size'] = base_params.get('position_size', 1.0) * 1.2
            adjusted['stop_loss'] = base_params.get('stop_loss', -0.015) * 1.3  # 더 넓은 손절
            adjusted['take_profit'] = base_params.get('take_profit', 0.025) * 1.2  # 더 높은 익절
            adjusted['rsi_buy'] = base_params.get('rsi_buy', 40) + 5  # 매수 완화

        elif regime == 'bear':
            # 약세장: 보수적
            adjusted['position_size'] = base_params.get('position_size', 1.0) * 0.7
            adjusted['stop_loss'] = base_params.get('stop_loss', -0.015) * 0.7  # 더 타이트한 손절
            adjusted['take_profit'] = base_params.get('take_profit', 0.025) * 0.8  # 더 낮은 익절
            adjusted['rsi_buy'] = base_params.get('rsi_buy', 40) - 5  # 매수 강화 (더 과매도)

        else:  # sideways
            # 횡보장: 빠른 회전
            adjusted['position_size'] = base_params.get('position_size', 1.0) * 0.9
            adjusted['stop_loss'] = base_params.get('stop_loss', -0.015) * 0.8
            adjusted['take_profit'] = base_params.get('take_profit', 0.025) * 0.7  # 빠른 익절
            adjusted['rsi_buy'] = base_params.get('rsi_buy', 40)  # 유지

        return adjusted

    def should_trade(self):
        """
        현재 시장 상태에서 거래해야 하는지 판단

        Returns:
            bool: True if should trade
        """
        if not self.current_regime:
            self.detect_market_regime()

        if not self.current_regime:
            return True  # 데이터 없으면 기본 거래

        regime = self.current_regime['regime']
        strength = self.current_regime['strength']

        # 약세장이 매우 강할 때만 거래 중단
        if regime == 'bear' and strength > 80:
            return False

        return True
