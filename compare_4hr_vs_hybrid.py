#!/usr/bin/env python3
"""
4시간 레인지 재진입 전략 vs 하이브리드 전략 비교

업비트 KRW-BTC 기준으로 두 전략 성과 비교
"""
import pandas as pd
from backtest_4hr_range_upbit import FourHourRangeBacktestUpbit
from hybrid_strategy import HybridStrategy


def run_strategy_comparison():
    """4시간 레인지 vs 하이브리드 전략 비교"""
    print("=" * 120)
    print("업비트 전략 비교: 4시간 레인지 재진입 (09:00 KST) vs 하이브리드 (BOX+TREND)")
    print("=" * 120)

    # 테스트 설정
    days = 180
    initial_balance = 1000000

    # === 4시간 레인지 전략 테스트 ===
    print(f"\n{'='*120}")
    print("📊 4시간 레인지 재진입 전략 백테스팅")
    print(f"{'='*120}")

    tester_4hr = FourHourRangeBacktestUpbit(initial_balance=initial_balance)
    df_5m_4hr, df_4h_4hr = tester_4hr.fetch_upbit_data(market='KRW-BTC', days=days)

    perf_4hr = None
    if df_5m_4hr is not None and df_4h_4hr is not None:
        print("\n백테스팅 실행 중...")
        perf_4hr = tester_4hr.backtest(df_5m_4hr, df_4h_4hr)
        print_performance(perf_4hr, "4시간 레인지")

    # === 하이브리드 전략 테스트 ===
    print(f"\n{'='*120}")
    print("📊 하이브리드 전략 (BOX+TREND) 백테스팅")
    print(f"{'='*120}")

    tester_hybrid = HybridStrategy(initial_balance=initial_balance)
    df_hybrid = tester_hybrid.fetch_upbit_data(market='KRW-BTC', days=days, timeframe=5)

    perf_hybrid = None
    if df_hybrid is not None:
        print("\n백테스팅 실행 중...")
        perf_hybrid = tester_hybrid.backtest(df_hybrid)
        print_performance(perf_hybrid, "하이브리드")

    # === 비교 ===
    if perf_4hr and perf_hybrid:
        # 안전하게 필드 가져오기
        r4_win = perf_4hr.get('win_trades', 0)
        r4_loss = perf_4hr.get('loss_trades', 0)
        h_win = perf_hybrid.get('win_trades', 0)
        h_loss = perf_hybrid.get('loss_trades', 0)

        print(f"\n{'='*120}")
        print("📊 4시간 레인지 vs 하이브리드 상세 비교")
        print(f"{'='*120}")
        print(f"{'지표':<25} {'4시간 레인지':>20} {'하이브리드':>20} {'차이':>20}")
        print(f"{'='*120}")
        print(f"{'수익률':<25} {perf_4hr['total_return']:>19.2f}% {perf_hybrid['total_return']:>19.2f}% {perf_hybrid['total_return']-perf_4hr['total_return']:>19.2f}%p")
        print(f"{'거래 횟수':<25} {perf_4hr['total_trades']:>20} {perf_hybrid['total_trades']:>20} {perf_hybrid['total_trades']-perf_4hr['total_trades']:>20}")
        print(f"{'승리 거래':<25} {r4_win:>20} {h_win:>20} {h_win-r4_win:>20}")
        print(f"{'손실 거래':<25} {r4_loss:>20} {h_loss:>20} {h_loss-r4_loss:>20}")
        print(f"{'승률':<25} {perf_4hr['win_rate']:>19.2f}% {perf_hybrid['win_rate']:>19.2f}% {perf_hybrid['win_rate']-perf_4hr['win_rate']:>19.2f}%p")
        print(f"{'평균 수익 (%)':<25} {perf_4hr['avg_profit']:>19.2f}% {perf_hybrid['avg_profit']:>19.2f}% {perf_hybrid['avg_profit']-perf_4hr['avg_profit']:>19.2f}%p")
        print(f"{'평균 손실 (%)':<25} {perf_4hr['avg_loss']:>19.2f}% {perf_hybrid['avg_loss']:>19.2f}% {perf_hybrid['avg_loss']-perf_4hr['avg_loss']:>19.2f}%p")
        print(f"{'Profit Factor':<25} {perf_4hr['profit_factor']:>20.2f} {perf_hybrid['profit_factor']:>20.2f} {perf_hybrid['profit_factor']-perf_4hr['profit_factor']:>20.2f}")
        print(f"{'MDD':<25} {perf_4hr['max_drawdown']:>19.2f}% {perf_hybrid['max_drawdown']:>19.2f}% {perf_hybrid['max_drawdown']-perf_4hr['max_drawdown']:>19.2f}%p")
        print(f"{'최종 자산':<25} {perf_4hr['final_balance']:>19,.0f}원 {perf_hybrid['final_balance']:>19,.0f}원 {perf_hybrid['final_balance']-perf_4hr['final_balance']:>19,.0f}원")

        # 결론
        print(f"\n{'='*120}")
        print("💡 결론")
        print(f"{'='*120}")

        # 수익률 비교
        if perf_4hr['total_return'] > perf_hybrid['total_return']:
            better_return = "4시간 레인지"
            diff_return = perf_4hr['total_return'] - perf_hybrid['total_return']
        else:
            better_return = "하이브리드"
            diff_return = perf_hybrid['total_return'] - perf_4hr['total_return']

        print(f"\n✅ 수익률 측면에서 {better_return}가 {diff_return:.2f}%p 더 우수합니다.")

        # 승률 비교
        if perf_4hr['win_rate'] > perf_hybrid['win_rate']:
            better_wr = "4시간 레인지"
            diff_wr = perf_4hr['win_rate'] - perf_hybrid['win_rate']
        else:
            better_wr = "하이브리드"
            diff_wr = perf_hybrid['win_rate'] - perf_4hr['win_rate']

        print(f"✅ 승률 측면에서 {better_wr}가 {diff_wr:.2f}%p 더 높습니다.")

        # Profit Factor 비교
        if perf_4hr['profit_factor'] > perf_hybrid['profit_factor']:
            better_pf = "4시간 레인지"
            diff_pf = perf_4hr['profit_factor'] - perf_hybrid['profit_factor']
        else:
            better_pf = "하이브리드"
            diff_pf = perf_hybrid['profit_factor'] - perf_4hr['profit_factor']

        print(f"✅ Profit Factor 측면에서 {better_pf}가 {diff_pf:.2f} 더 우수합니다.")

        # MDD 비교 (낮을수록 좋음)
        if perf_4hr['max_drawdown'] < perf_hybrid['max_drawdown']:
            better_mdd = "4시간 레인지"
            diff_mdd = perf_hybrid['max_drawdown'] - perf_4hr['max_drawdown']
        else:
            better_mdd = "하이브리드"
            diff_mdd = perf_4hr['max_drawdown'] - perf_hybrid['max_drawdown']

        print(f"✅ MDD 측면에서 {better_mdd}가 {abs(diff_mdd):.2f}%p 더 안정적입니다.")

        # 거래 빈도 비교
        print(f"\n📊 거래 빈도:")
        print(f"   - 4시간 레인지: 평균 {perf_4hr['total_trades']/(days/30):.1f}회/월")
        print(f"   - 하이브리드:   평균 {perf_hybrid['total_trades']/(days/30):.1f}회/월")

        # 종합 추천
        print(f"\n{'='*120}")
        print("🎯 종합 추천")
        print(f"{'='*120}")

        # 점수 계산
        score_4hr = 0
        score_hybrid = 0

        if perf_4hr['total_return'] > perf_hybrid['total_return']:
            score_4hr += 2
        else:
            score_hybrid += 2

        if perf_4hr['win_rate'] > perf_hybrid['win_rate']:
            score_4hr += 1
        else:
            score_hybrid += 1

        if perf_4hr['profit_factor'] > perf_hybrid['profit_factor']:
            score_4hr += 1
        else:
            score_hybrid += 1

        if perf_4hr['max_drawdown'] > perf_hybrid['max_drawdown']:
            score_hybrid += 1
        else:
            score_4hr += 1

        if score_4hr > score_hybrid:
            print(f"✨ 4시간 레인지 전략이 종합적으로 더 우수합니다. (점수: {score_4hr} vs {score_hybrid})")
            print(f"   → Oracle Cloud 봇에는 4시간 레인지 전략 적용을 추천합니다.")
        elif score_hybrid > score_4hr:
            print(f"✨ 하이브리드 전략이 종합적으로 더 우수합니다. (점수: {score_hybrid} vs {score_4hr})")
            print(f"   → Oracle Cloud 봇은 현재 전략(하이브리드) 유지를 추천합니다.")
        else:
            print(f"✨ 두 전략 모두 비슷한 성과를 보입니다. (점수: {score_4hr} vs {score_hybrid})")
            print(f"   → 리스크 허용도와 거래 빈도 선호에 따라 선택하세요.")

        # 전략별 특징
        print(f"\n{'='*120}")
        print("📋 전략별 특징")
        print(f"{'='*120}")
        print("\n[4시간 레인지 재진입 전략]")
        print("  장점: 명확한 진입/청산 규칙, 하루 1번 레인지 설정으로 관리 용이")
        print("  단점: 레인지가 형성되지 않으면 거래 불가, 트렌드 시장에서 불리")
        print("  적합: 횡보장이 많은 시장, 간단한 전략 선호")

        print("\n[하이브리드 전략 (BOX+TREND)]")
        print("  장점: 시장 상황에 따라 자동 전환, 다양한 시장 환경 대응")
        print("  단점: 복잡한 모드 전환 로직, 파라미터 조정 필요")
        print("  적합: 변동성 높은 시장, 다양한 전략 활용 선호")

        # 상세 거래 내역 비교
        print(f"\n{'='*120}")
        print("📋 최근 거래 내역 비교 (각 10개)")
        print(f"{'='*120}")

        if perf_4hr['total_trades'] > 0:
            print("\n[4시간 레인지 최근 거래]")
            trades_4hr = perf_4hr['trades']
            print(trades_4hr.tail(10).to_string(index=False))

        if perf_hybrid['total_trades'] > 0:
            print("\n[하이브리드 최근 거래]")
            trades_hybrid = perf_hybrid['trades']
            print(trades_hybrid.tail(10).to_string(index=False))


def print_performance(perf, strategy_name):
    """성과 출력"""
    print(f"\n{'─'*80}")
    print(f"전략: {strategy_name}")
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
    run_strategy_comparison()
