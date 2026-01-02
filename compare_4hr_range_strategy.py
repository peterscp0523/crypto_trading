#!/usr/bin/env python3
"""
4시간 레인지 재진입 스캘핑 전략 - 바이낸스 vs 업비트 비교

바이낸스: 뉴욕 시간 기준 (09:00~13:00 EST)
업비트: 한국 시간 기준 (09:00~13:00 KST)
"""
import pandas as pd
from backtest_4hr_range_binance import FourHourRangeBacktest
from backtest_4hr_range_upbit import FourHourRangeBacktestUpbit


def run_comparison():
    """바이낸스 vs 업비트 비교"""
    print("=" * 120)
    print("4시간 레인지 재진입 스캘핑 전략 - 바이낸스 (00:00 EST) vs 업비트 (09:00 KST) 비교")
    print("=" * 120)

    # 테스트 설정
    days = 180
    initial_balance = 1000000

    # === 바이낸스 테스트 ===
    print(f"\n{'='*120}")
    print("📊 바이낸스 백테스팅 (00:00 EST 기준)")
    print(f"{'='*120}")

    tester_binance = FourHourRangeBacktest(initial_balance=initial_balance)
    df_5m_binance, df_4h_binance = tester_binance.fetch_binance_data(symbol='BTC/USDT', days=days)

    perf_binance = None
    if df_5m_binance is not None and df_4h_binance is not None:
        print("\n백테스팅 실행 중...")
        perf_binance = tester_binance.backtest(df_5m_binance, df_4h_binance)
        print_performance(perf_binance, "바이낸스")

    # === 업비트 테스트 ===
    print(f"\n{'='*120}")
    print("📊 업비트 백테스팅 (09:00 KST 기준)")
    print(f"{'='*120}")

    tester_upbit = FourHourRangeBacktestUpbit(initial_balance=initial_balance)
    df_5m_upbit, df_4h_upbit = tester_upbit.fetch_upbit_data(market='KRW-BTC', days=days)

    perf_upbit = None
    if df_5m_upbit is not None and df_4h_upbit is not None:
        print("\n백테스팅 실행 중...")
        perf_upbit = tester_upbit.backtest(df_5m_upbit, df_4h_upbit)
        print_performance(perf_upbit, "업비트")

    # === 비교 ===
    if perf_binance and perf_upbit:
        # 안전하게 필드 가져오기
        b_win = perf_binance.get('win_trades', 0)
        b_loss = perf_binance.get('loss_trades', 0)
        u_win = perf_upbit.get('win_trades', 0)
        u_loss = perf_upbit.get('loss_trades', 0)

        print(f"\n{'='*120}")
        print("📊 바이낸스 vs 업비트 상세 비교")
        print(f"{'='*120}")
        print(f"{'지표':<25} {'바이낸스':>20} {'업비트':>20} {'차이':>20}")
        print(f"{'='*120}")
        print(f"{'수익률':<25} {perf_binance['total_return']:>19.2f}% {perf_upbit['total_return']:>19.2f}% {perf_upbit['total_return']-perf_binance['total_return']:>19.2f}%p")
        print(f"{'거래 횟수':<25} {perf_binance['total_trades']:>20} {perf_upbit['total_trades']:>20} {perf_upbit['total_trades']-perf_binance['total_trades']:>20}")
        print(f"{'승리 거래':<25} {b_win:>20} {u_win:>20} {u_win-b_win:>20}")
        print(f"{'손실 거래':<25} {b_loss:>20} {u_loss:>20} {u_loss-b_loss:>20}")
        print(f"{'승률':<25} {perf_binance['win_rate']:>19.2f}% {perf_upbit['win_rate']:>19.2f}% {perf_upbit['win_rate']-perf_binance['win_rate']:>19.2f}%p")
        print(f"{'평균 수익 (%)':<25} {perf_binance['avg_profit']:>19.2f}% {perf_upbit['avg_profit']:>19.2f}% {perf_upbit['avg_profit']-perf_binance['avg_profit']:>19.2f}%p")
        print(f"{'평균 손실 (%)':<25} {perf_binance['avg_loss']:>19.2f}% {perf_upbit['avg_loss']:>19.2f}% {perf_upbit['avg_loss']-perf_binance['avg_loss']:>19.2f}%p")
        print(f"{'Profit Factor':<25} {perf_binance['profit_factor']:>20.2f} {perf_upbit['profit_factor']:>20.2f} {perf_upbit['profit_factor']-perf_binance['profit_factor']:>20.2f}")
        print(f"{'MDD':<25} {perf_binance['max_drawdown']:>19.2f}% {perf_upbit['max_drawdown']:>19.2f}% {perf_upbit['max_drawdown']-perf_binance['max_drawdown']:>19.2f}%p")
        print(f"{'최종 자산':<25} {perf_binance['final_balance']:>19,.0f}원 {perf_upbit['final_balance']:>19,.0f}원 {perf_upbit['final_balance']-perf_binance['final_balance']:>19,.0f}원")

        # 결론
        print(f"\n{'='*120}")
        print("💡 결론")
        print(f"{'='*120}")

        if perf_binance['total_return'] > perf_upbit['total_return']:
            better = "바이낸스"
            diff = perf_binance['total_return'] - perf_upbit['total_return']
        else:
            better = "업비트"
            diff = perf_upbit['total_return'] - perf_binance['total_return']

        print(f"\n✅ 수익률 측면에서 {better}가 {diff:.2f}%p 더 우수합니다.")

        # 승률 비교
        if perf_binance['win_rate'] > perf_upbit['win_rate']:
            better_wr = "바이낸스"
            diff_wr = perf_binance['win_rate'] - perf_upbit['win_rate']
        else:
            better_wr = "업비트"
            diff_wr = perf_upbit['win_rate'] - perf_binance['win_rate']

        print(f"✅ 승률 측면에서 {better_wr}가 {diff_wr:.2f}%p 더 높습니다.")

        # Profit Factor 비교
        if perf_binance['profit_factor'] > perf_upbit['profit_factor']:
            better_pf = "바이낸스"
            diff_pf = perf_binance['profit_factor'] - perf_upbit['profit_factor']
        else:
            better_pf = "업비트"
            diff_pf = perf_upbit['profit_factor'] - perf_binance['profit_factor']

        print(f"✅ Profit Factor 측면에서 {better_pf}가 {diff_pf:.2f} 더 우수합니다.")

        # MDD 비교 (낮을수록 좋음)
        if perf_binance['max_drawdown'] < perf_upbit['max_drawdown']:
            better_mdd = "바이낸스"
            diff_mdd = perf_upbit['max_drawdown'] - perf_binance['max_drawdown']
        else:
            better_mdd = "업비트"
            diff_mdd = perf_binance['max_drawdown'] - perf_upbit['max_drawdown']

        print(f"✅ MDD 측면에서 {better_mdd}가 {abs(diff_mdd):.2f}%p 더 안정적입니다.")

        # 거래 빈도 비교
        print(f"\n📊 거래 빈도:")
        print(f"   - 바이낸스: 평균 {perf_binance['total_trades']/(days/30):.1f}회/월")
        print(f"   - 업비트:   평균 {perf_upbit['total_trades']/(days/30):.1f}회/월")

        # 종합 추천
        print(f"\n{'='*120}")
        print("🎯 종합 추천")
        print(f"{'='*120}")

        # 점수 계산 (수익률, 승률, PF, MDD 종합)
        score_binance = 0
        score_upbit = 0

        if perf_binance['total_return'] > perf_upbit['total_return']:
            score_binance += 2
        else:
            score_upbit += 2

        if perf_binance['win_rate'] > perf_upbit['win_rate']:
            score_binance += 1
        else:
            score_upbit += 1

        if perf_binance['profit_factor'] > perf_upbit['profit_factor']:
            score_binance += 1
        else:
            score_upbit += 1

        if perf_binance['max_drawdown'] > perf_upbit['max_drawdown']:
            score_upbit += 1
        else:
            score_binance += 1

        if score_binance > score_upbit:
            print(f"✨ 바이낸스가 종합적으로 더 우수합니다. (점수: {score_binance} vs {score_upbit})")
            print(f"   → Oracle Cloud 봇에는 바이낸스 전략 적용을 추천합니다.")
        elif score_upbit > score_binance:
            print(f"✨ 업비트가 종합적으로 더 우수합니다. (점수: {score_upbit} vs {score_binance})")
            print(f"   → Oracle Cloud 봇에는 업비트 전략 적용을 추천합니다.")
        else:
            print(f"✨ 두 거래소 모두 비슷한 성과를 보입니다. (점수: {score_binance} vs {score_upbit})")
            print(f"   → 사용자의 선호도나 수수료 조건에 따라 선택하세요.")

        # 상세 거래 내역 비교
        print(f"\n{'='*120}")
        print("📋 최근 거래 내역 비교 (각 10개)")
        print(f"{'='*120}")

        if perf_binance['total_trades'] > 0:
            print("\n[바이낸스 최근 거래]")
            trades_binance = perf_binance['trades']
            print(trades_binance.tail(10).to_string(index=False))

        if perf_upbit['total_trades'] > 0:
            print("\n[업비트 최근 거래]")
            trades_upbit = perf_upbit['trades']
            print(trades_upbit.tail(10).to_string(index=False))


def print_performance(perf, exchange_name):
    """성과 출력"""
    print(f"\n{'─'*80}")
    print(f"거래소: {exchange_name}")
    print(f"{'─'*80}")

    win_trades = perf.get('win_trades', 0)
    loss_trades = perf.get('loss_trades', 0)

    print(f"총 거래:        {perf['total_trades']}회 (승: {win_trades}회, 패: {loss_trades}회)")
    print(f"최종 수익률:    {perf['total_return']:.2f}%")
    print(f"승률:           {perf['win_rate']:.2f}%")
    print(f"평균 수익:      {perf['avg_profit']:.2f}%")
    print(f"평균 손실:      {perf['avg_loss']:.2f}%")
    print(f"Profit Factor:  {perf['profit_factor']:.2f}")
    print(f"MDD:            {perf['max_drawdown']:.2f}%")
    print(f"최종 자산:      {perf['final_balance']:,.0f}원")


if __name__ == "__main__":
    run_comparison()
