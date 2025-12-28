"""
코인 선택 시스템 (거래량 × 변동성 기반)
소액 투자에 최적화된 알트코인 선택
"""
from datetime import datetime, timedelta


class CoinSelector:
    """거래량과 변동성을 고려한 코인 선택"""

    def __init__(self, upbit_api):
        self.upbit = upbit_api

    def get_top_volume_coins(self, top_n=20):
        """24시간 거래대금 상위 코인 조회"""
        try:
            # 전체 KRW 마켓 조회
            markets = self.upbit.get_market_all()
            krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]

            # 24시간 거래량 조회
            tickers = self.upbit.get_ticker(krw_markets)

            if not tickers:
                return []

            # 거래대금(거래량 × 현재가) 기준 정렬
            coins_with_volume = []
            for ticker in tickers:
                volume_krw = ticker['acc_trade_price_24h']  # 24시간 누적 거래대금
                coins_with_volume.append({
                    'market': ticker['market'],
                    'volume_krw': volume_krw,
                    'price': ticker['trade_price'],
                    'change_rate': ticker['signed_change_rate'] * 100
                })

            # 거래대금 상위 정렬
            coins_with_volume.sort(key=lambda x: x['volume_krw'], reverse=True)

            return coins_with_volume[:top_n]

        except Exception as e:
            print(f"거래량 조회 실패: {e}")
            return []

    def calculate_volatility_score(self, market):
        """변동성 점수 계산 (ATR 기반)"""
        try:
            # 1시간봉 24개 (1일)
            candles = self.upbit.get_candles(market, "minutes", 60, 24)

            if not candles or len(candles) < 24:
                return 0

            # ATR 계산
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

            if not true_ranges:
                return 0

            atr = sum(true_ranges) / len(true_ranges)
            current_price = candles[0]['trade_price']
            volatility_pct = (atr / current_price) * 100

            return volatility_pct

        except Exception as e:
            print(f"{market} 변동성 계산 실패: {e}")
            return 0

    def get_best_coins_for_scalping(self, min_volume_krw=50_000_000_000, top_n=5):
        """
        스캘핑에 최적인 코인 선택

        Args:
            min_volume_krw: 최소 24h 거래대금 (기본 500억)
            top_n: 반환할 코인 개수

        Returns:
            [{'market': 'KRW-DOGE', 'score': 85.5, ...}, ...]
        """
        print("=" * 70)
        print("🎯 스캘핑 최적 코인 선택")
        print("=" * 70)

        # 1단계: 거래량 상위 20개
        top_volume = self.get_top_volume_coins(20)

        # 2단계: 거래대금 필터 (유동성 확보)
        filtered = [c for c in top_volume if c['volume_krw'] >= min_volume_krw]

        if not filtered:
            print(f"⚠️ 거래대금 {min_volume_krw:,.0f}원 이상인 코인이 없습니다.")
            print(f"   기준을 완화하여 상위 10개 코인 사용")
            filtered = top_volume[:10]

        print(f"\n✅ 거래대금 필터 통과: {len(filtered)}개 코인")

        # 3단계: 변동성 점수 계산
        print("\n📊 변동성 분석 중...")
        scored_coins = []
        for coin in filtered:
            market = coin['market']
            volatility = self.calculate_volatility_score(market)

            # 점수 = 변동성 × 거래량 가중치
            # 거래량 정규화 (1조 = 1.0)
            volume_score = min(coin['volume_krw'] / 1_000_000_000_000, 1.0)

            # 변동성 정규화 (5% = 1.0)
            volatility_score = min(volatility / 5.0, 1.0)

            # 종합 점수 (변동성 70%, 거래량 30%)
            total_score = (volatility_score * 70) + (volume_score * 30)

            scored_coins.append({
                'market': market,
                'price': coin['price'],
                'volume_krw': coin['volume_krw'],
                'volatility': volatility,
                'change_24h': coin['change_rate'],
                'score': total_score
            })

            print(f"  {market}: 변동성={volatility:.2f}%, "
                  f"거래대금={coin['volume_krw']/1e9:.0f}억, 점수={total_score:.1f}")

        # 4단계: 점수 기준 정렬
        scored_coins.sort(key=lambda x: x['score'], reverse=True)

        # 5단계: 고가 코인 제외 (소액 투자 최적화)
        # BTC, ETH처럼 가격이 높은 코인은 소액으로 수량 확보가 어려움
        final_coins = []
        for coin in scored_coins:
            # 50만원 이하 가격 우선 (소액으로 수량 확보 용이)
            if coin['price'] < 500_000:
                coin['priority'] = 'high'  # 알트코인 우선
            elif coin['price'] < 5_000_000:
                coin['priority'] = 'medium'
            else:
                coin['priority'] = 'low'  # BTC/ETH 등 후순위

            final_coins.append(coin)

        # 우선순위 재정렬 (high → medium → low)
        priority_order = {'high': 3, 'medium': 2, 'low': 1}
        final_coins.sort(key=lambda x: (priority_order[x['priority']], x['score']), reverse=True)

        print(f"\n🏆 스캘핑 추천 코인 Top {top_n}:")
        for i, coin in enumerate(final_coins[:top_n], 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            print(f"\n{emoji} {coin['market']}")
            print(f"   가격: {coin['price']:,.0f}원 (우선순위: {coin['priority']})")
            print(f"   변동성: {coin['volatility']:.2f}%")
            print(f"   거래대금: {coin['volume_krw']/1e9:.0f}억원")
            print(f"   24h 변화: {coin['change_24h']:+.2f}%")
            print(f"   종합점수: {coin['score']:.1f}")

        print("\n" + "=" * 70)

        return final_coins[:top_n]


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    selector = CoinSelector(upbit)

    # 스캘핑 최적 코인 5개 선택
    best_coins = selector.get_best_coins_for_scalping(
        min_volume_krw=50_000_000_000,  # 500억 이상
        top_n=5
    )

    if best_coins:
        print("\n✅ 선택된 코인:")
        for coin in best_coins:
            print(f"  - {coin['market']}")
