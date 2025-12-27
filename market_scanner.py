"""
멀티 코인 모멘텀 스캐너
업비트 거래량 상위 코인 중 모멘텀이 강한 코인을 자동 선택
"""
import time
from datetime import datetime
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators


class MarketScanner:
    """시장 스캔 및 코인 선택"""

    def __init__(self, upbit):
        self.upbit = upbit
        self.last_scan_time = None
        self.cached_rankings = []
        self.scan_interval = 120  # 2분마다 스캔 (1분봉 대응)

    def get_krw_markets(self):
        """KRW 마켓 목록 가져오기"""
        try:
            # 업비트 API에서 마켓 정보 가져오기
            markets = self.upbit.get_market_all()

            # KRW 마켓만 필터링
            krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]

            return krw_markets
        except Exception as e:
            print(f"마켓 목록 조회 실패: {e}")
            return []

    def calculate_momentum_score(self, market, ticker, candles_1h):
        """모멘텀 점수 계산 (0-100)"""
        try:
            if not ticker or not candles_1h or len(candles_1h) < 50:
                return 0

            # === 1. 가격 모멘텀 (30점) ===
            change_24h = ticker.get('signed_change_rate', 0) * 100

            # 24시간 변화율 점수 (0-30)
            if change_24h > 10:
                price_score = 30
            elif change_24h > 5:
                price_score = 25
            elif change_24h > 2:
                price_score = 20
            elif change_24h > 0:
                price_score = 15
            elif change_24h > -2:
                price_score = 10
            elif change_24h > -5:
                price_score = 5
            else:
                price_score = 0

            # === 2. 거래량 모멘텀 (30점) ===
            current_volume = ticker.get('acc_trade_price_24h', 0)

            # 24시간 거래대금 기준 (억원)
            volume_100m = current_volume / 100_000_000

            if volume_100m > 1000:  # 1000억 이상
                volume_score = 30
            elif volume_100m > 500:
                volume_score = 25
            elif volume_100m > 200:
                volume_score = 20
            elif volume_100m > 100:
                volume_score = 15
            elif volume_100m > 50:
                volume_score = 10
            else:
                volume_score = 5

            # === 3. RSI 모멘텀 (20점) ===
            prices = [c['trade_price'] for c in candles_1h]
            rsi = TechnicalIndicators.calculate_rsi(prices, 14)

            if not rsi:
                rsi_score = 0
            elif 40 <= rsi <= 60:  # 중립 구간 (상승 여력)
                rsi_score = 20
            elif 30 <= rsi < 40:  # 과매도 구간
                rsi_score = 15
            elif 60 < rsi <= 70:  # 상승 중
                rsi_score = 15
            elif 20 <= rsi < 30:  # 극단 과매도
                rsi_score = 10
            else:
                rsi_score = 5

            # === 4. 추세 모멘텀 (20점) ===
            # MA20 vs MA50
            ma20 = sum(prices[:20]) / 20
            ma50 = sum(prices[:50]) / 50
            current_price = prices[0]

            if ma20 > ma50 and current_price > ma20:  # 골든크로스 + 상승
                trend_score = 20
            elif ma20 > ma50:  # 골든크로스
                trend_score = 15
            elif current_price > ma20:  # 단기 상승
                trend_score = 10
            else:
                trend_score = 5

            # === 총점 계산 ===
            total_score = price_score + volume_score + rsi_score + trend_score

            return total_score

        except Exception as e:
            print(f"{market} 점수 계산 실패: {e}")
            return 0

    def scan_top_coins(self, top_n=20, min_volume_100m=50):
        """
        상위 코인 스캔 및 모멘텀 순위 매기기

        Args:
            top_n: 스캔할 코인 개수 (거래량 상위)
            min_volume_100m: 최소 거래대금 (억원)
        """
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 시장 스캔 시작...")

            # KRW 마켓 목록
            markets = self.get_krw_markets()
            if not markets:
                print("⚠️ 마켓 목록이 없습니다")
                return []

            # 모든 코인의 현재가 정보 가져오기
            tickers = self.upbit.get_current_prices(markets)
            if not tickers:
                print("⚠️ 시세 정보를 가져올 수 없습니다")
                return []

            # 거래대금 기준 정렬
            tickers_sorted = sorted(
                tickers,
                key=lambda x: x.get('acc_trade_price_24h', 0),
                reverse=True
            )

            # 상위 N개 + 최소 거래대금 필터
            min_volume = min_volume_100m * 100_000_000
            top_tickers = [
                t for t in tickers_sorted[:top_n]
                if t.get('acc_trade_price_24h', 0) >= min_volume
            ]

            print(f"📊 거래량 상위 {len(top_tickers)}개 코인 분석 중...")

            # 각 코인의 모멘텀 점수 계산
            coin_scores = []

            for ticker in top_tickers:
                market = ticker['market']

                # 1시간봉 데이터 (점수 계산용)
                candles_1h = self.upbit.get_candles(market, "minutes", 60, 50)

                # 모멘텀 점수 계산
                score = self.calculate_momentum_score(market, ticker, candles_1h)

                if score > 0:
                    coin_scores.append({
                        'market': market,
                        'name': market.replace('KRW-', ''),
                        'score': score,
                        'price': ticker['trade_price'],
                        'change_24h': ticker.get('signed_change_rate', 0) * 100,
                        'volume_24h': ticker.get('acc_trade_price_24h', 0),
                        'timestamp': datetime.now()
                    })

                # API 호출 제한 (초당 10회)
                time.sleep(0.15)

            # 점수 기준 정렬
            coin_scores.sort(key=lambda x: x['score'], reverse=True)

            self.cached_rankings = coin_scores
            self.last_scan_time = datetime.now()

            # 상위 5개 출력
            print(f"\n🏆 모멘텀 랭킹 TOP 5:")
            for i, coin in enumerate(coin_scores[:5], 1):
                print(f"{i}. {coin['name']:6s} | 점수: {coin['score']:3.0f} | "
                      f"24H: {coin['change_24h']:+6.2f}% | "
                      f"거래액: {coin['volume_24h']/100_000_000:,.0f}억")

            return coin_scores

        except Exception as e:
            print(f"❌ 스캔 실패: {e}")
            return []

    def get_best_coin(self, exclude_markets=None):
        """
        최고 모멘텀 코인 선택

        Args:
            exclude_markets: 제외할 마켓 리스트 (현재 보유 중인 코인 등)
        """
        # 캐시된 결과가 오래되었으면 재스캔
        if (not self.last_scan_time or
            (datetime.now() - self.last_scan_time).total_seconds() > self.scan_interval):
            self.scan_top_coins()

        if not self.cached_rankings:
            return None

        # 제외 목록 필터링
        exclude_markets = exclude_markets or []

        for coin in self.cached_rankings:
            if coin['market'] not in exclude_markets:
                return coin

        return None

    def should_switch_coin(self, current_market, min_score_diff=15):
        """
        현재 코인에서 다른 코인으로 전환할지 결정

        Args:
            current_market: 현재 보유 중인 마켓
            min_score_diff: 최소 점수 차이 (전환 기준)

        Returns:
            (should_switch, new_coin)
        """
        if not self.cached_rankings:
            return False, None

        # 현재 코인의 점수 찾기
        current_score = 0
        for coin in self.cached_rankings:
            if coin['market'] == current_market:
                current_score = coin['score']
                break

        # 1위 코인
        best_coin = self.cached_rankings[0]

        # 이미 1위 코인 보유 중
        if best_coin['market'] == current_market:
            return False, None

        # 점수 차이가 기준 이상이면 전환
        score_diff = best_coin['score'] - current_score

        if score_diff >= min_score_diff:
            print(f"💱 코인 전환 추천: {current_market} ({current_score}) → "
                  f"{best_coin['market']} ({best_coin['score']}) | 차이: +{score_diff}")
            return True, best_coin

        return False, None


if __name__ == "__main__":
    """테스트"""
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
    scanner = MarketScanner(upbit)

    # 스캔 테스트
    results = scanner.scan_top_coins(top_n=30, min_volume_100m=50)

    if results:
        print(f"\n✅ 총 {len(results)}개 코인 분석 완료")

        best = scanner.get_best_coin()
        if best:
            print(f"\n🎯 최고 모멘텀: {best['name']} (점수: {best['score']})")

        # 코인 전환 테스트
        should_switch, new_coin = scanner.should_switch_coin('KRW-BTC', min_score_diff=15)
        if should_switch:
            print(f"\n💱 BTC → {new_coin['name']} 전환 권장")
