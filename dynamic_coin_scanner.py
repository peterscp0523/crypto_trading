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

    def update_scan_pool(self, pool_size=10):
        """
        스캔 대상 코인 풀 갱신

        상위 10개 코인을 동시에 스캔 → 그 중 최고 기회 선택
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

            for ticker in tickers:
                market = ticker['market']
                price = ticker['trade_price']
                volume_krw = ticker['acc_trade_price_24h']
                change_rate = abs(ticker['signed_change_rate']) * 100

                # 필터 1: 거래량 50억 이상 (10억에서 완화)
                if volume_krw < 5_000_000_000:
                    continue

                # 필터 2: 변동성 1.5% 이상 (2%에서 완화)
                if change_rate < 1.5:
                    continue

                # 필터 3: 가격 50만원 이하 우선
                priority = 'high' if price < 500_000 else 'medium' if price < 5_000_000 else 'low'

                # 점수 계산
                volume_score = min(volume_krw / 100_000_000_000, 1.0)
                volatility_score = min(change_rate / 5.0, 1.0)
                total_score = (volatility_score * 70) + (volume_score * 30)

                # 우선순위 가중치
                priority_weight = {'high': 1.2, 'medium': 1.0, 'low': 0.8}
                final_score = total_score * priority_weight[priority]

                candidates.append({
                    'market': market,
                    'price': price,
                    'volume_krw': volume_krw,
                    'volatility': change_rate,
                    'score': final_score,
                    'priority': priority
                })

            # 점수 상위 N개 선택
            candidates.sort(key=lambda x: x['score'], reverse=True)
            self.scan_pool = candidates[:pool_size]
            self.last_pool_update = datetime.now()

            print(f"\n🔄 스캔 풀 갱신: {len(self.scan_pool)}개 코인")
            for i, coin in enumerate(self.scan_pool[:5], 1):
                print(f"   {i}. {coin['market']}: {coin['volatility']:.1f}%, {coin['volume_krw']/1e9:.0f}억, 점수={coin['score']:.1f}")

            return self.scan_pool

        except Exception as e:
            print(f"❌ 스캔 풀 갱신 실패: {e}")
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
