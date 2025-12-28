#!/usr/bin/env python3
"""
매수 조건 진단 스크립트
왜 매수가 일어나지 않는지 실시간 분석
"""
from telegram_bot import TelegramBot, TradingBot
from upbit_api import UpbitAPI
from market_scanner import MarketScanner
from config import get_config
import sys

config = get_config()

# API 초기화
upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
scanner = MarketScanner(upbit)

print("=" * 70)
print("🔍 매수 조건 진단")
print("=" * 70)

# TOP 5 코인 스캔
print("\n📊 TOP 5 모멘텀 코인 스캔 중...")
scanner.scan_top_coins(top_n=20, min_volume_100m=50)

if not scanner.cached_rankings:
    print("❌ 스캔 실패")
    sys.exit(1)

# 텔레그램 봇 초기화 (로깅용)
telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

# 트레이딩 봇 초기화
bot = TradingBot(
    upbit,
    telegram,
    config['market'],
    dry_run=True,  # 드라이런 모드
    signal_timeframe=1,
    enable_multi_coin=True,
    db=None
)

print(f"\n📈 TOP 10 코인 매수 조건 체크:")
print("-" * 70)

for i, coin in enumerate(scanner.cached_rankings[:10], 1):
    market = coin['market']
    name = coin['name']

    print(f"\n{i}. {name} (모멘텀: {coin['score']:.0f})")

    # 임시로 마켓 변경
    original_market = bot.market
    bot.market = market

    # 다중 시간대 신호 분석
    try:
        signals = bot.get_multi_timeframe_signals()

        if not signals:
            print(f"   ❌ 신호 없음")
            bot.market = original_market
            continue

        # 각 시간대별 매수 신호
        buy_count = signals.get('buy_signal_count', 0)

        print(f"   RSI: {signals['rsi']:.1f}")
        print(f"   볼린저 위치: {signals['bb_pos']:.1f}%")
        print(f"   거래량 비율: {signals['vol_ratio']:.2f}x (필요: {signals['vol_threshold']:.2f}x)")
        print(f"   거래량 OK: {'✅' if signals['volume_ok'] else '❌'}")

        # 추세 정보
        if signals.get('trend'):
            trend = signals['trend']
            print(f"   추세: {trend['trend_state']} (매수 허용: {'✅' if trend['buy_allowed'] else '❌'})")
            print(f"   RSI 임계값: {trend.get('rsi_threshold', 'N/A')}")

        # 시간대별 신호
        print(f"\n   📊 매수 신호: {buy_count}/3")

        # 1분봉
        signals_1m = bot.get_signals(1)
        if signals_1m:
            print(f"      1분봉: {'✅ 매수' if signals_1m['buy'] else '❌ 대기'} (RSI: {signals_1m['rsi']:.1f}, 볼륨: {signals_1m['vol_ratio']:.2f}x)")

        # 5분봉
        signals_5m = bot.get_signals(5)
        if signals_5m:
            print(f"      5분봉: {'✅ 매수' if signals_5m['buy'] else '❌ 대기'} (RSI: {signals_5m['rsi']:.1f}, 볼륨: {signals_5m['vol_ratio']:.2f}x)")

        # 15분봉
        signals_15m = bot.get_signals(15)
        if signals_15m:
            print(f"     15분봉: {'✅ 매수' if signals_15m['buy'] else '❌ 대기'} (RSI: {signals_15m['rsi']:.1f}, 볼륨: {signals_15m['vol_ratio']:.2f}x)")

        # 매수 가능 여부 (1개 이상으로 완화)
        if buy_count >= 1:
            print(f"\n   🎯 매수 신호 충분! (1개 이상 시간대 매수)")
        else:
            print(f"\n   ⚠️  매수 신호 부족 ({buy_count}/3, 최소 1개 필요)")

    except Exception as e:
        print(f"   ❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()

    bot.market = original_market

print("\n" + "=" * 70)
print("✅ 진단 완료")
print("=" * 70)
