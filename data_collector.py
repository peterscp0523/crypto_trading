"""
데이터 수집 스케줄러
주기적으로 캔들 데이터를 수집하여 데이터베이스에 저장
"""
import time
from datetime import datetime
from upbit_api import UpbitAPI
from database_manager import DatabaseManager
from config import get_config


class DataCollector:
    """캔들 데이터 수집 및 저장"""

    def __init__(self, upbit, db, markets=None):
        """
        Args:
            upbit: UpbitAPI 인스턴스
            db: DatabaseManager 인스턴스
            markets: 수집할 마켓 리스트 (None이면 거래량 상위 20개)
        """
        self.upbit = upbit
        self.db = db
        self.markets = markets or []

    def get_top_markets(self, limit=20):
        """거래량 상위 마켓 조회"""
        try:
            all_markets = self.upbit.get_market_all()
            krw_markets = [m['market'] for m in all_markets if m['market'].startswith('KRW-')]

            # 현재가 조회로 거래량 정보 가져오기
            tickers = self.upbit.get_current_prices(krw_markets)

            # 24시간 거래대금 기준 정렬
            sorted_tickers = sorted(
                tickers,
                key=lambda x: x.get('acc_trade_price_24h', 0),
                reverse=True
            )

            return [t['market'] for t in sorted_tickers[:limit]]

        except Exception as e:
            print(f"⚠️ 상위 마켓 조회 실패: {e}")
            return ['KRW-BTC', 'KRW-ETH', 'KRW-XRP']  # 기본값

    def collect_candles(self, market, timeframe='15', count=200):
        """
        특정 마켓의 캔들 데이터 수집 및 저장

        Args:
            market: 마켓 (KRW-BTC 등)
            timeframe: 타임프레임 ('1', '5', '15', '60', '240', 'day')
            count: 수집할 캔들 개수
        """
        try:
            # 업비트 API에서 캔들 조회
            if timeframe == 'day':
                candles = self.upbit.get_candles(market, 'days', None, count)
                tf_key = '1d'
            else:
                candles = self.upbit.get_candles(market, 'minutes', int(timeframe), count)
                tf_key = f'{timeframe}m'

            if not candles:
                print(f"⚠️ {market} 캔들 데이터 없음")
                return 0

            # 데이터베이스에 저장
            saved = self.db.save_candles(market, tf_key, candles)

            if saved > 0:
                print(f"✅ {market} {tf_key}: {saved}개 캔들 저장")

            return saved

        except Exception as e:
            print(f"❌ {market} 데이터 수집 실패: {e}")
            return 0

    def collect_all_markets(self, timeframes=['15', '60']):
        """
        모든 관심 마켓의 데이터 수집

        Args:
            timeframes: 수집할 타임프레임 리스트
        """
        # 마켓 리스트가 비어있으면 상위 20개 조회
        if not self.markets:
            self.markets = self.get_top_markets(20)

        print(f"\n{'='*60}")
        print(f"📊 데이터 수집 시작 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(f"마켓: {len(self.markets)}개")
        print(f"타임프레임: {timeframes}")
        print(f"{'='*60}\n")

        total_saved = 0

        for market in self.markets:
            for tf in timeframes:
                saved = self.collect_candles(market, tf, count=200)
                total_saved += saved
                time.sleep(0.1)  # API 요청 제한 방지

        print(f"\n{'='*60}")
        print(f"✅ 수집 완료: 총 {total_saved}개 캔들 저장")
        print(f"{'='*60}\n")

        return total_saved

    def run_scheduler(self, interval_minutes=60):
        """
        주기적 데이터 수집 실행

        Args:
            interval_minutes: 수집 주기 (분)
        """
        print(f"🔄 데이터 수집 스케줄러 시작 (주기: {interval_minutes}분)")

        while True:
            try:
                self.collect_all_markets(timeframes=['15', '60'])

                # 다음 수집 시간 출력
                next_time = datetime.now().timestamp() + (interval_minutes * 60)
                next_time_str = datetime.fromtimestamp(next_time).strftime('%Y-%m-%d %H:%M:%S')
                print(f"⏰ 다음 수집: {next_time_str}")

                time.sleep(interval_minutes * 60)

            except KeyboardInterrupt:
                print("\n데이터 수집 중지")
                break
            except Exception as e:
                print(f"❌ 데이터 수집 오류: {e}")
                print(f"⏰ 10분 후 재시도...")
                time.sleep(600)


if __name__ == "__main__":
    """테스트 및 실행"""
    import os

    # 설정 로드
    config = get_config()

    # API 초기화
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 데이터베이스 초기화
    use_oracle = os.environ.get('USE_ORACLE_DB', 'false').lower() == 'true'
    db = DatabaseManager(use_oracle=use_oracle)

    # 데이터 수집기 생성
    collector = DataCollector(upbit, db)

    # 1회 수집 테스트
    print("=== 1회 데이터 수집 테스트 ===")
    collector.collect_all_markets(timeframes=['15', '60'])

    # 스케줄러 실행 여부
    run_scheduler = os.environ.get('RUN_DATA_COLLECTOR', 'false').lower() == 'true'

    if run_scheduler:
        # 주기적 수집 시작 (1시간마다)
        collector.run_scheduler(interval_minutes=60)
    else:
        print("\n💡 스케줄러를 실행하려면 RUN_DATA_COLLECTOR=true 환경변수 설정")
        db.close()
