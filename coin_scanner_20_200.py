"""
20/200 SMA 전략에 적합한 코인 실시간 스캐너

핵심 기능:
1. 바이낸스 전체 USDT 마켓 스캔
2. 20/200 SMA 전략 조건 충족 코인 필터링
3. 최적 코인 순위 매기기
4. 실시간 모니터링

전략 조건:
1. 20MA 명확한 상승 중 (기울기 0.2%+)
2. 가격 > 200MA (구조적 상승 바이어스)
3. 20MA 근처 (±3% 이내)
4. 거래량 충분 (최소 거래대금)
"""
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time


class CoinScanner_20_200:
    """20/200 SMA 전략 코인 스캐너"""

    def __init__(self, min_volume_usdt=10_000_000, timeframe='1m'):
        """
        Args:
            min_volume_usdt: 최소 24시간 거래대금 (USDT) - 기본 1000만 USDT
            timeframe: 타임프레임 (기본 1분봉)
        """
        self.exchange = ccxt.binance()
        self.min_volume_usdt = min_volume_usdt
        self.timeframe = timeframe

    def get_all_usdt_markets(self):
        """모든 USDT 마켓 가져오기"""
        try:
            markets = self.exchange.load_markets()
            usdt_pairs = [
                symbol for symbol in markets.keys()
                if symbol.endswith('/USDT') and markets[symbol]['active']
            ]
            return usdt_pairs
        except Exception as e:
            print(f"❌ 마켓 로딩 실패: {e}")
            return []

    def get_candles(self, symbol, limit=250):
        """
        캔들 데이터 가져오기

        Args:
            symbol: 거래쌍 (예: 'BTC/USDT')
            limit: 캔들 개수 (200MA 계산 위해 최소 250개)
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                self.timeframe,
                limit=limit
            )

            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            return df

        except Exception as e:
            return None

    def calculate_sma(self, df):
        """SMA 20, 200 계산"""
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['sma200'] = df['close'].rolling(window=200).mean()

        # 20MA 기울기
        df['sma20_prev'] = df['sma20'].shift(1)
        df['sma20_slope'] = (df['sma20'] - df['sma20_prev']) / df['sma20_prev']

        # 가격과 MA 간 거리
        df['distance_to_20ma'] = (df['close'] - df['sma20']) / df['sma20'] * 100
        df['distance_to_200ma'] = (df['close'] - df['sma200']) / df['sma200'] * 100

        return df

    def check_strategy_conditions(self, df):
        """
        전략 조건 체크

        Returns:
            dict: {
                'qualified': bool,
                'score': float,
                'details': dict
            }
        """
        if len(df) < 200:
            return {'qualified': False, 'score': 0, 'details': {}}

        latest = df.iloc[-1]

        # 데이터 검증
        if pd.isna(latest['sma20']) or pd.isna(latest['sma200']):
            return {'qualified': False, 'score': 0, 'details': {}}

        # 1. 20MA 상승 기울기 체크 (0.2% 이상)
        slope = latest['sma20_slope']
        is_uptrend = slope > 0.002

        # 2. 가격 > 200MA
        above_200ma = latest['close'] > latest['sma200']

        # 3. 20MA 근처 (±3% 이내)
        distance = abs(latest['distance_to_20ma'])
        near_20ma = distance <= 3.0

        # 모든 조건 충족 여부
        qualified = is_uptrend and above_200ma and near_20ma

        # 점수 계산 (0-100)
        score = 0

        if is_uptrend:
            # 기울기가 클수록 높은 점수 (최대 40점)
            slope_score = min(slope * 10000, 40)
            score += slope_score

        if above_200ma:
            # 200MA 위 거리에 따라 점수 (최대 30점)
            gap_200 = latest['distance_to_200ma']
            if gap_200 > 0:
                gap_score = min(gap_200 * 2, 30)
                score += gap_score

        if near_20ma:
            # 20MA에 가까울수록 높은 점수 (최대 30점)
            proximity_score = 30 - (distance * 10)
            score += max(0, proximity_score)

        details = {
            'price': latest['close'],
            'sma20': latest['sma20'],
            'sma200': latest['sma200'],
            'slope': slope,
            'slope_pct': slope * 100,
            'distance_20ma': latest['distance_to_20ma'],
            'distance_200ma': latest['distance_to_200ma'],
            'is_uptrend': is_uptrend,
            'above_200ma': above_200ma,
            'near_20ma': near_20ma
        }

        return {
            'qualified': qualified,
            'score': score,
            'details': details
        }

    def scan_market(self, max_coins=50):
        """
        전체 마켓 스캔

        Args:
            max_coins: 스캔할 최대 코인 수 (거래량 상위)

        Returns:
            list: 적합한 코인 리스트 (점수 순)
        """
        print(f"\n{'='*70}")
        print(f"📊 20/200 SMA 전략 코인 스캐너")
        print(f"{'='*70}")
        print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"타임프레임: {self.timeframe}")
        print(f"최소 거래대금: ${self.min_volume_usdt:,.0f}")
        print(f"{'='*70}\n")

        # 1. 모든 USDT 마켓 가져오기
        all_markets = self.get_all_usdt_markets()
        print(f"총 {len(all_markets)}개 USDT 마켓 발견")

        # 2. 24시간 거래량 조회 (상위 코인만)
        print(f"거래량 상위 {max_coins}개 코인 선택 중...")
        tickers = self.exchange.fetch_tickers()

        volume_filtered = []
        for symbol in all_markets:
            if symbol in tickers:
                ticker = tickers[symbol]
                volume_usdt = ticker.get('quoteVolume', 0)

                if volume_usdt >= self.min_volume_usdt:
                    volume_filtered.append({
                        'symbol': symbol,
                        'volume_usdt': volume_usdt,
                        'price': ticker['last']
                    })

        # 거래량 순 정렬
        volume_filtered.sort(key=lambda x: x['volume_usdt'], reverse=True)
        top_coins = volume_filtered[:max_coins]

        print(f"✅ {len(top_coins)}개 코인 선정 (거래량 ${self.min_volume_usdt:,.0f} 이상)")

        # 3. 각 코인 전략 조건 체크
        print(f"\n전략 조건 체크 중...")
        qualified_coins = []

        for idx, coin_info in enumerate(top_coins):
            symbol = coin_info['symbol']

            # 진행 상황 출력
            if (idx + 1) % 10 == 0:
                print(f"  {idx + 1}/{len(top_coins)} 진행 중...")

            # 캔들 데이터 가져오기
            df = self.get_candles(symbol)
            if df is None:
                continue

            # SMA 계산
            df = self.calculate_sma(df)

            # 조건 체크
            result = self.check_strategy_conditions(df)

            if result['qualified']:
                qualified_coins.append({
                    'symbol': symbol,
                    'score': result['score'],
                    'volume_usdt': coin_info['volume_usdt'],
                    'details': result['details']
                })

            # API 제한 방지
            time.sleep(0.1)

        # 4. 점수 순 정렬
        qualified_coins.sort(key=lambda x: x['score'], reverse=True)

        return qualified_coins

    def print_results(self, qualified_coins):
        """결과 출력"""
        print(f"\n{'='*70}")
        print(f"🎯 전략 조건 충족 코인: {len(qualified_coins)}개")
        print(f"{'='*70}\n")

        if not qualified_coins:
            print("❌ 조건을 만족하는 코인이 없습니다.")
            print("   - 20MA 상승 추세")
            print("   - 가격 > 200MA")
            print("   - 20MA 근처 (±3%)")
            return

        print(f"{'순위':<6} {'코인':<12} {'점수':<8} {'거래대금':<15} {'가격위치':<12} {'추세강도'}")
        print("-" * 70)

        for idx, coin in enumerate(qualified_coins[:20]):  # 상위 20개만
            details = coin['details']

            rank = f"#{idx + 1}"
            symbol = coin['symbol'].replace('/USDT', '')
            score = f"{coin['score']:.1f}"
            volume = f"${coin['volume_usdt']/1e6:.1f}M"

            # 가격 위치 (20MA 대비)
            dist = details['distance_20ma']
            if dist > 0:
                position = f"+{dist:.1f}%"
            else:
                position = f"{dist:.1f}%"

            # 추세 강도
            slope_pct = details['slope_pct']
            strength = f"{slope_pct:.2f}%"

            print(f"{rank:<6} {symbol:<12} {score:<8} {volume:<15} {position:<12} {strength}")

        print(f"\n{'='*70}")

        # 최고 점수 코인 상세 정보
        if qualified_coins:
            best = qualified_coins[0]
            print(f"\n🏆 최적 코인: {best['symbol']}")
            print(f"{'='*70}")
            print(f"점수: {best['score']:.1f}/100")
            print(f"24시간 거래대금: ${best['volume_usdt']:,.0f}")

            d = best['details']
            print(f"\n현재 가격: ${d['price']:.4f}")
            print(f"20MA: ${d['sma20']:.4f} (거리: {d['distance_20ma']:+.2f}%)")
            print(f"200MA: ${d['sma200']:.4f} (거리: {d['distance_200ma']:+.2f}%)")
            print(f"\n20MA 기울기: {d['slope_pct']:.3f}% ({'상승 ✅' if d['is_uptrend'] else '약함 ❌'})")
            print(f"200MA 위치: {'위 ✅' if d['above_200ma'] else '아래 ❌'}")
            print(f"20MA 근처: {'예 ✅' if d['near_20ma'] else '아니오 ❌'}")
            print(f"{'='*70}")

    def monitor_continuous(self, interval_seconds=60):
        """
        지속적 모니터링 모드

        Args:
            interval_seconds: 스캔 간격 (초)
        """
        print(f"\n🔄 지속 모니터링 시작 (간격: {interval_seconds}초)")
        print("   종료하려면 Ctrl+C를 누르세요\n")

        try:
            while True:
                qualified_coins = self.scan_market()
                self.print_results(qualified_coins)

                print(f"\n⏰ {interval_seconds}초 후 다시 스캔...")
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n\n모니터링 종료")


def main():
    """메인 함수"""
    import sys

    # 옵션 파싱
    mode = sys.argv[1] if len(sys.argv) > 1 else 'once'
    timeframe = sys.argv[2] if len(sys.argv) > 2 else '1m'

    # 스캐너 생성
    scanner = CoinScanner_20_200(
        min_volume_usdt=10_000_000,  # 1000만 USDT 이상
        timeframe=timeframe
    )

    if mode == 'monitor':
        # 지속 모니터링
        scanner.monitor_continuous(interval_seconds=60)
    else:
        # 1회 스캔
        qualified_coins = scanner.scan_market(max_coins=50)
        scanner.print_results(qualified_coins)

        # 결과 저장
        if qualified_coins:
            df = pd.DataFrame([
                {
                    'symbol': c['symbol'],
                    'score': c['score'],
                    'volume_usdt': c['volume_usdt'],
                    'price': c['details']['price'],
                    'distance_20ma': c['details']['distance_20ma'],
                    'distance_200ma': c['details']['distance_200ma'],
                    'slope_pct': c['details']['slope_pct'],
                    'timestamp': datetime.now()
                }
                for c in qualified_coins
            ])
            df.to_csv('qualified_coins.csv', index=False)
            print(f"\n💾 저장: qualified_coins.csv")


if __name__ == "__main__":
    main()
