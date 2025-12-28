"""
동적 코인 스캐너
여러 코인을 실시간 스캔하여 가장 좋은 기회 포착
신호가 없으면 다른 코인으로 즉시 전환
"""
from datetime import datetime, timedelta


class DynamicCoinScanner:
    """실시간 다중 코인 스캔 → 최적 기회 선택"""

    def __init__(self, upbit_api):
        self.upbit = upbit_api
        self.scan_pool = []  # 스캔 대상 코인 풀
        self.last_pool_update = None
        self.pool_update_interval = 600  # 10분마다 풀 갱신

    def _calculate_technical_score(self, market):
        """
        기술적 지표 기반 상승 가능성 점수 계산

        지표:
        1. RSI (30 이하 과매도 = 반등 기회, 70 이상 과매수 = 위험)
        2. MACD (골든크로스 = 상승, 데드크로스 = 하락)
        3. 볼린저 밴드 (하단 근처 = 반등, 상단 근처 = 조정)
        4. 거래량 증가 (매수세 유입)

        Returns:
            0.0 ~ 1.0 점수
        """
        try:
            # 1분봉 30개로 단기 지표 계산
            candles = self.upbit.get_candles(market, "minutes", 1, 30)
            if not candles or len(candles) < 20:
                return 0.5  # 기본값

            score = 0.0

            # === 1. RSI (30점 배점) ===
            rsi = self._calculate_rsi(candles, period=14)
            if rsi is not None:
                if 30 <= rsi <= 40:  # 과매도 구간 (반등 기회)
                    score += 30
                elif 40 < rsi <= 50:  # 중립~약세
                    score += 20
                elif 50 < rsi <= 60:  # 중립~강세
                    score += 15
                elif 60 < rsi <= 70:  # 과매수 진입
                    score += 5
                # RSI > 70 or < 30: 0점 (극단적)

            # === 2. MACD (25점 배점) ===
            macd_line, signal_line = self._calculate_macd(candles)
            if macd_line is not None and signal_line is not None:
                if macd_line > signal_line and macd_line > 0:
                    # 골든크로스 + 양수 = 강한 상승
                    score += 25
                elif macd_line > signal_line:
                    # 골든크로스
                    score += 15
                elif macd_line < signal_line and macd_line < 0:
                    # 데드크로스 + 음수 = 강한 하락
                    score += 0

            # === 3. 볼린저 밴드 (25점 배점) ===
            bb_position = self._calculate_bb_position(candles)
            if bb_position is not None:
                if 0.0 <= bb_position <= 0.2:
                    # 하단 근처 (반등 기회)
                    score += 25
                elif 0.2 < bb_position <= 0.5:
                    # 중하단
                    score += 15
                elif 0.5 < bb_position <= 0.8:
                    # 중상단
                    score += 10
                # 상단(0.8~1.0): 0점 (조정 가능성)

            # === 4. 거래량 추세 (20점 배점) ===
            recent_volume = sum(c['candle_acc_trade_price'] for c in candles[:5])
            past_volume = sum(c['candle_acc_trade_price'] for c in candles[10:15])
            if past_volume > 0:
                volume_ratio = recent_volume / past_volume
                if volume_ratio > 1.5:
                    # 거래량 50% 이상 증가
                    score += 20
                elif volume_ratio > 1.2:
                    score += 10

            # 점수 정규화 (0.0 ~ 1.0)
            normalized_score = min(score / 100.0, 1.0)
            return normalized_score

        except Exception as e:
            # print(f"기술적 지표 계산 실패 ({market}): {e}")
            return 0.5  # 오류 시 중립 점수

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

    def _calculate_macd(self, candles):
        """MACD 계산 (간이버전)"""
        if len(candles) < 26:
            return None, None

        prices = [c['trade_price'] for c in reversed(candles)]

        # EMA 12, 26
        ema12 = self._calculate_ema(prices, 12)
        ema26 = self._calculate_ema(prices, 26)

        if ema12 is None or ema26 is None:
            return None, None

        macd_line = ema12 - ema26

        # Signal line (MACD의 9일 EMA) - 간단히 평균으로 근사
        signal_line = macd_line * 0.9  # 근사값

        return macd_line, signal_line

    def _calculate_ema(self, prices, period):
        """EMA 계산"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_bb_position(self, candles, period=20):
        """볼린저 밴드 내 위치 (0.0=하단, 0.5=중간, 1.0=상단)"""
        if len(candles) < period:
            return None

        prices = [c['trade_price'] for c in candles[:period]]
        current_price = candles[0]['trade_price']

        mean = sum(prices) / period
        variance = sum((p - mean) ** 2 for p in prices) / period
        std = variance ** 0.5

        upper_band = mean + (2 * std)
        lower_band = mean - (2 * std)

        if upper_band == lower_band:
            return 0.5

        position = (current_price - lower_band) / (upper_band - lower_band)
        return max(0.0, min(1.0, position))

    def update_scan_pool(self, pool_size=10):
        """
        스캔 대상 코인 풀 갱신

        기술적 지표 기반으로 상승 가능성 높은 코인 선택
        """
        try:
            # 전체 KRW 마켓
            markets = self.upbit.get_market_all()
            krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]

            # 티커 조회
            tickers = self.upbit.get_ticker(krw_markets[:50])

            if not tickers:
                return []

            # 필터링 및 점수 계산
            candidates = []

            print(f"\n🔍 기술적 분석 중...")

            for ticker in tickers:
                market = ticker['market']
                price = ticker['trade_price']
                volume_krw = ticker['acc_trade_price_24h']
                change_rate = abs(ticker['signed_change_rate']) * 100

                # 필터 1: 거래량 50억 이상
                if volume_krw < 5_000_000_000:
                    continue

                # 필터 2: 변동성 1.5% 이상
                if change_rate < 1.5:
                    continue

                # === 기술적 지표 점수 ===
                technical_score = self._calculate_technical_score(market)

                # 필터 3: 기술적 점수 0.6 이상 (60점 이상) - 보수적 전략
                if technical_score < 0.6:
                    continue

                # 필터 4: 가격 50만원 이하 우선
                priority = 'high' if price < 500_000 else 'medium' if price < 5_000_000 else 'low'

                # === 종합 점수 계산 ===
                # 기술적 지표 50%, 변동성 30%, 거래량 20%
                volume_score = min(volume_krw / 100_000_000_000, 1.0)
                volatility_score = min(change_rate / 5.0, 1.0)

                total_score = (technical_score * 50) + (volatility_score * 30) + (volume_score * 20)

                # 우선순위 가중치
                priority_weight = {'high': 1.2, 'medium': 1.0, 'low': 0.8}
                final_score = total_score * priority_weight[priority]

                candidates.append({
                    'market': market,
                    'price': price,
                    'volume_krw': volume_krw,
                    'volatility': change_rate,
                    'technical_score': technical_score,
                    'score': final_score,
                    'priority': priority
                })

            if not candidates:
                print(f"⚠️ 기술적 조건 만족하는 코인 없음 (기준 완화 필요)")
                return []

            # 점수 상위 N개 선택
            candidates.sort(key=lambda x: x['score'], reverse=True)
            self.scan_pool = candidates[:pool_size]
            self.last_pool_update = datetime.now()

            print(f"\n✅ 스캔 풀 갱신: {len(self.scan_pool)}개 코인")
            for i, coin in enumerate(self.scan_pool[:5], 1):
                print(f"   {i}. {coin['market']}: 기술={coin['technical_score']*100:.0f}점, "
                      f"변동={coin['volatility']:.1f}%, 거래={coin['volume_krw']/1e9:.0f}억, "
                      f"종합={coin['score']:.1f}")

            return self.scan_pool

        except Exception as e:
            print(f"❌ 스캔 풀 갱신 실패: {e}")
            import traceback
            traceback.print_exc()
            return []

    def should_update_pool(self):
        """풀 갱신 필요 여부"""
        if not self.last_pool_update:
            return True

        elapsed = (datetime.now() - self.last_pool_update).total_seconds()
        return elapsed >= self.pool_update_interval

    def scan_all_opportunities(self, strategies):
        """
        모든 코인을 스캔하여 최고 기회 찾기

        Args:
            strategies: {'scalping': strategy, 'bear': strategy, 'ma': strategy}

        Returns:
            {
                'market': 'KRW-DOGE',
                'strategy': 'scalping',
                'signal': {...},
                'score': 85.5
            }
        """
        try:
            # 풀 갱신 체크
            if self.should_update_pool():
                self.update_scan_pool(pool_size=10)

            if not self.scan_pool:
                print("⚠️ 스캔 풀 없음")
                return None

            best_opportunity = None
            best_score = 0

            print(f"\n🔍 {len(self.scan_pool)}개 코인 실시간 스캔 중...")

            for coin in self.scan_pool:
                market = coin['market']

                # === 1순위: 하락장 반등 ===
                if 'bear' in strategies:
                    # 극단적 하락장 체크
                    if strategies['bear'].should_avoid_trading(market, self.upbit):
                        continue  # 이 코인 스킵

                    bear_signal = strategies['bear'].find_bounce_opportunity(market, self.upbit)

                    if bear_signal and bear_signal['action'] == 'buy':
                        score = bear_signal['confidence'] * 120  # 최우선

                        if score > best_score:
                            best_score = score
                            best_opportunity = {
                                'market': market,
                                'strategy': 'bear_bounce',
                                'signal': bear_signal,
                                'score': score,
                                'coin_info': coin
                            }
                            print(f"   💰 {market}: 하락장 반등 ({score:.0f}점)")
                            continue  # 하락장 반등 찾았으면 다른 전략 체크 안함

                # === 2순위: 스캘핑 ===
                if 'scalping' in strategies:
                    scalp_signal = strategies['scalping'].check_scalping_opportunity(
                        market, self.upbit, None
                    )

                    if scalp_signal and scalp_signal['action'] == 'buy':
                        score = scalp_signal['confidence'] * 100

                        if score > best_score:
                            best_score = score
                            best_opportunity = {
                                'market': market,
                                'strategy': 'scalping',
                                'signal': scalp_signal,
                                'score': score,
                                'coin_info': coin
                            }
                            print(f"   💰 {market}: 스캘핑 ({score:.0f}점)")

                # === 3순위: MA 크로스오버 ===
                if 'ma' in strategies:
                    ma_signal = strategies['ma'].check_trading_opportunity(
                        market, self.upbit, None
                    )

                    if ma_signal and ma_signal['action'] == 'buy':
                        score = ma_signal['confidence'] * 90

                        if score > best_score:
                            best_score = score
                            best_opportunity = {
                                'market': market,
                                'strategy': 'ma_crossover',
                                'signal': ma_signal,
                                'score': score,
                                'coin_info': coin
                            }
                            print(f"   💰 {market}: MA크로스 ({score:.0f}점)")

            if best_opportunity:
                print(f"\n🎯 최고 기회: {best_opportunity['market']} ({best_opportunity['strategy']}, {best_opportunity['score']:.0f}점)")
            else:
                print(f"\n⏸️  매수 기회 없음 (다음 스캔 대기)")

            return best_opportunity

        except Exception as e:
            print(f"❌ 스캔 실패: {e}")
            import traceback
            traceback.print_exc()
            return None


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config
    from volatility_strategy import VolatilityScalpingStrategy
    from ma_crossover_strategy import MACrossoverStrategy
    from bear_market_strategy import BearMarketStrategy

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 스캐너 초기화
    scanner = DynamicCoinScanner(upbit)

    # 전략 초기화
    strategies = {
        'scalping': VolatilityScalpingStrategy(),
        'ma': MACrossoverStrategy(),
        'bear': BearMarketStrategy()
    }

    print("=== 동적 코인 스캐너 테스트 ===")

    # 1차 스캔
    opportunity = scanner.scan_all_opportunities(strategies)

    if opportunity:
        print(f"\n✅ 매수 기회 발견!")
        print(f"   코인: {opportunity['market']}")
        print(f"   전략: {opportunity['strategy']}")
        print(f"   점수: {opportunity['score']:.0f}")
        print(f"   사유: {opportunity['signal']['reason']}")
        print(f"   신뢰도: {opportunity['signal']['confidence']*100:.0f}%")
    else:
        print(f"\n⏸️  현재 매수 기회 없음")
