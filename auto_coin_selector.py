"""
자동 코인 선택기
10분마다 최적의 코인 1개를 선택하여 집중 투자
"""
from datetime import datetime, timedelta


class AutoCoinSelector:
    """단일 코인 자동 선택"""

    def __init__(self, upbit_api):
        self.upbit = upbit_api
        self.current_coin = None
        self.last_selection = None
        self.selection_interval = 600  # 10분마다 재선택

    def should_reselect(self):
        """코인 재선택이 필요한지 확인"""
        if not self.last_selection:
            return True

        elapsed = (datetime.now() - self.last_selection).total_seconds()
        return elapsed >= self.selection_interval

    def select_best_coin(self):
        """
        최적의 코인 1개 선택

        기준:
        1. 거래량 상위 20개
        2. 변동성 2% 이상
        3. 가격 50만원 이하 (소액 투자 최적화)
        4. 종합 점수 = (변동성 × 70) + (거래량 × 30)
        """
        try:
            # 전체 KRW 마켓
            markets = self.upbit.get_market_all()
            krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]

            # 티커 조회
            tickers = self.upbit.get_ticker(krw_markets[:50])

            if not tickers:
                return None

            # 필터링 및 점수 계산
            candidates = []

            for ticker in tickers:
                market = ticker['market']
                price = ticker['trade_price']
                volume_krw = ticker['acc_trade_price_24h']
                change_rate = abs(ticker['signed_change_rate']) * 100

                # 필터 1: 거래량 100억 이상
                if volume_krw < 10_000_000_000:
                    continue

                # 필터 2: 변동성 2% 이상
                if change_rate < 2.0:
                    continue

                # 필터 3: 가격 50만원 이하 (소액 투자 최적화)
                priority = 'high' if price < 500_000 else 'medium' if price < 5_000_000 else 'low'

                # 점수 계산
                volume_score = min(volume_krw / 100_000_000_000, 1.0)  # 1000억 = 1.0
                volatility_score = min(change_rate / 5.0, 1.0)  # 5% = 1.0

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

            if not candidates:
                print("⚠️ 조건에 맞는 코인 없음")
                return None

            # 점수 1위 선택
            candidates.sort(key=lambda x: x['score'], reverse=True)
            best = candidates[0]

            print(f"\n🎯 최적 코인 선택: {best['market']}")
            print(f"   가격: {best['price']:,.0f}원")
            print(f"   변동성: {best['volatility']:.2f}%")
            print(f"   거래량: {best['volume_krw']/1e9:.0f}억원")
            print(f"   점수: {best['score']:.1f}")
            print(f"   우선순위: {best['priority']}")

            self.current_coin = best['market']
            self.last_selection = datetime.now()

            return best['market']

        except Exception as e:
            print(f"❌ 코인 선택 실패: {e}")
            return None

    def get_current_coin(self):
        """현재 선택된 코인 반환 (재선택 체크 포함)"""
        if self.should_reselect():
            print("🔄 코인 재선택 시간...")
            return self.select_best_coin()

        return self.current_coin


if __name__ == "__main__":
    """테스트"""
    from upbit_api import UpbitAPI
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    selector = AutoCoinSelector(upbit)

    print("=== 자동 코인 선택 테스트 ===\n")

    # 1차 선택
    coin1 = selector.select_best_coin()
    print(f"\n1차 선택: {coin1}")

    # 바로 다시 호출 (재선택 안됨)
    coin2 = selector.get_current_coin()
    print(f"\n2차 호출: {coin2} (재선택 안됨)")

    # 강제 재선택 (테스트용)
    selector.last_selection = datetime.now() - timedelta(seconds=700)
    coin3 = selector.get_current_coin()
    print(f"\n3차 호출: {coin3} (재선택됨)")
