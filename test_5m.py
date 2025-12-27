"""
5분봉 전략 백테스트
더 빠른 매매를 위한 테스트
"""
from upbit_api import UpbitAPI
from backtest import Backtester
from config import get_config

if __name__ == "__main__":
    try:
        config = get_config()
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

        print("\n" + "="*60)
        print("5분봉 백테스트 vs 15분봉 비교")
        print("="*60 + "\n")

        # 5분봉 백테스트
        print("🔵 5분봉 전략 테스트 (약 17시간)")
        backtester_5m = Backtester(upbit, config['market'])
        result_5m = backtester_5m.run(initial_balance=1000000, debug=False, timeframe="5m")

        # 15분봉 백테스트
        print("\n🟢 15분봉 전략 테스트 (약 2일)")
        backtester_15m = Backtester(upbit, config['market'])
        result_15m = backtester_15m.run(initial_balance=1000000, debug=False, timeframe="15m")

        # 비교
        print("\n" + "="*60)
        print("📊 비교 결과")
        print("="*60)
        if result_5m and result_15m:
            print(f"\n5분봉:")
            print(f"  • 총 손익: {result_5m['profit']:+,.0f}원 ({result_5m['profit_rate']:+.2f}%)")
            print(f"  • 거래 횟수: {result_5m['trades']}회")
            print(f"  • 승률: {result_5m['win_rate']:.1f}%")

            print(f"\n15분봉:")
            print(f"  • 총 손익: {result_15m['profit']:+,.0f}원 ({result_15m['profit_rate']:+.2f}%)")
            print(f"  • 거래 횟수: {result_15m['trades']}회")
            print(f"  • 승률: {result_15m['win_rate']:.1f}%")

            print(f"\n💡 추천:")
            if result_5m['profit_rate'] > result_15m['profit_rate']:
                print("  5분봉이 더 나은 성과를 보였습니다.")
            else:
                print("  15분봉이 더 나은 성과를 보였습니다.")

        print("="*60 + "\n")

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
