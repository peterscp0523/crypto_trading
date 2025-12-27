"""
자동 파라미터 최적화
백테스팅을 통해 최적의 전략 파라미터를 자동으로 찾습니다
"""
import time
from datetime import datetime, timedelta
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators


class ParameterOptimizer:
    """파라미터 최적화 엔진"""

    def __init__(self, upbit, market="KRW-ETH"):
        self.upbit = upbit
        self.market = market

    def backtest_strategy(self, candles, params):
        """
        단일 파라미터 세트로 백테스팅

        Args:
            candles: 캔들 데이터
            params: {
                'quick_profit': 0.008,
                'take_profit_1': 0.015,
                'stop_loss': -0.015,
                'trailing_stop_tight': 0.003,
                ...
            }
        """
        if len(candles) < 100:
            return None

        prices = [c['trade_price'] for c in candles]
        volumes = [c['candle_acc_trade_volume'] for c in candles]

        # 시뮬레이션 변수
        capital = 1000000  # 초기 자본 100만원
        position = None
        trades = []
        peak_profit = 0

        for i in range(50, len(candles)):
            current_price = prices[i]

            # 지표 계산
            recent_prices = prices[i-50:i]
            rsi = TechnicalIndicators.calculate_rsi(recent_prices, 14)
            upper, middle, lower = AdvancedIndicators.calculate_bollinger_bands(recent_prices, 20, 2)

            if not rsi or not upper:
                continue

            # 포지션 있음
            if position:
                profit_rate = (current_price - position['buy_price']) / position['buy_price']

                # 최고점 업데이트
                if profit_rate > peak_profit:
                    peak_profit = profit_rate

                # 익절 조건들
                sell = False
                reason = ""

                # 퀵 익절 (단순화: 10개봉 = 약 30분)
                if i - position['buy_index'] <= 10 and profit_rate >= params['quick_profit']:
                    sell = True
                    reason = "quick"
                elif profit_rate >= params['take_profit_1']:
                    sell = True
                    reason = "tp1"
                elif profit_rate <= params['stop_loss']:
                    sell = True
                    reason = "sl"
                # 트레일링 스톱
                elif peak_profit >= 0.003 and profit_rate < peak_profit - params['trailing_stop_tight']:
                    sell = True
                    reason = "trailing"

                if sell:
                    sell_value = capital * (1 + profit_rate)
                    profit = sell_value - capital

                    trades.append({
                        'profit': profit,
                        'profit_rate': profit_rate,
                        'reason': reason,
                        'hold_periods': i - position['buy_index']
                    })

                    capital = sell_value
                    position = None
                    peak_profit = 0

            # 포지션 없음 - 매수 신호
            else:
                # 간단한 매수 조건
                if rsi < 40 and current_price <= lower * 1.05:
                    position = {
                        'buy_price': current_price,
                        'buy_index': i
                    }

        # 결과 계산
        if not trades:
            return None

        total_return = (capital - 1000000) / 1000000 * 100
        win_trades = [t for t in trades if t['profit'] > 0]
        win_rate = len(win_trades) / len(trades) * 100 if trades else 0
        avg_profit = sum(t['profit'] for t in trades) / len(trades)
        avg_hold = sum(t['hold_periods'] for t in trades) / len(trades)

        # 샤프 비율 간이 계산 (수익률 / 변동성)
        if len(trades) > 1:
            returns = [t['profit_rate'] for t in trades]
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            sharpe = avg_return / std_dev if std_dev > 0 else 0
        else:
            sharpe = 0

        return {
            'params': params,
            'total_return': total_return,
            'num_trades': len(trades),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_hold_periods': avg_hold,
            'sharpe_ratio': sharpe,
            'score': total_return * 0.4 + win_rate * 0.3 + sharpe * 100 * 0.3  # 종합 점수
        }

    def optimize(self, days=30, top_n=3):
        """
        그리드 서치로 최적 파라미터 찾기

        Args:
            days: 백테스트 기간 (일)
            top_n: 상위 N개 결과 반환
        """
        print(f"\n{'='*60}")
        print(f"🔍 파라미터 최적화 시작 ({self.market}, {days}일)")
        print(f"{'='*60}\n")

        # 과거 데이터 가져오기 (15분봉)
        total_candles = days * 24 * 4  # 하루 96개 (15분봉)
        candles = self.upbit.get_candles(self.market, "minutes", 15, total_candles)

        if len(candles) < 100:
            print("❌ 데이터 부족")
            return []

        print(f"✅ 데이터 로드 완료: {len(candles)}개 캔들")

        # 파라미터 그리드
        param_grid = {
            'quick_profit': [0.005, 0.008, 0.010, 0.012],      # 0.5%, 0.8%, 1.0%, 1.2%
            'take_profit_1': [0.012, 0.015, 0.020, 0.025],     # 1.2%, 1.5%, 2.0%, 2.5%
            'stop_loss': [-0.010, -0.015, -0.020, -0.025],     # -1.0%, -1.5%, -2.0%, -2.5%
            'trailing_stop_tight': [0.002, 0.003, 0.005]       # 0.2%, 0.3%, 0.5%
        }

        results = []
        total_combinations = (len(param_grid['quick_profit']) *
                            len(param_grid['take_profit_1']) *
                            len(param_grid['stop_loss']) *
                            len(param_grid['trailing_stop_tight']))

        print(f"🔄 총 {total_combinations}개 조합 테스트 시작...\n")

        count = 0
        for qp in param_grid['quick_profit']:
            for tp1 in param_grid['take_profit_1']:
                for sl in param_grid['stop_loss']:
                    for ts in param_grid['trailing_stop_tight']:
                        count += 1

                        # 논리적 검증: 퀵익절 < 1차익절, 손절 절대값 < 익절
                        if qp >= tp1 or abs(sl) > tp1:
                            continue

                        params = {
                            'quick_profit': qp,
                            'take_profit_1': tp1,
                            'stop_loss': sl,
                            'trailing_stop_tight': ts
                        }

                        result = self.backtest_strategy(candles, params)

                        if result and result['num_trades'] >= 3:  # 최소 3회 거래
                            results.append(result)

                            if count % 10 == 0:
                                print(f"  진행: {count}/{total_combinations} "
                                      f"| 유효 결과: {len(results)}개")

        if not results:
            print("❌ 유효한 결과 없음")
            return []

        # 점수 기준 정렬
        results.sort(key=lambda x: x['score'], reverse=True)

        print(f"\n{'='*60}")
        print(f"🏆 최적화 완료! 상위 {min(top_n, len(results))}개 결과:")
        print(f"{'='*60}\n")

        for i, r in enumerate(results[:top_n], 1):
            p = r['params']
            print(f"#{i} 종합점수: {r['score']:.2f}")
            print(f"   파라미터:")
            print(f"     • 퀵익절: {p['quick_profit']*100:.1f}%")
            print(f"     • 1차익절: {p['take_profit_1']*100:.1f}%")
            print(f"     • 손절: {p['stop_loss']*100:.1f}%")
            print(f"     • 트레일링: {p['trailing_stop_tight']*100:.1f}%")
            print(f"   성과:")
            print(f"     • 총수익률: {r['total_return']:+.2f}%")
            print(f"     • 거래횟수: {r['num_trades']}회")
            print(f"     • 승률: {r['win_rate']:.1f}%")
            print(f"     • 평균보유: {r['avg_hold_periods']:.1f}봉")
            print(f"     • 샤프비율: {r['sharpe_ratio']:.3f}")
            print()

        return results[:top_n]

    def get_best_params(self, days=30):
        """최적 파라미터 반환"""
        results = self.optimize(days)
        if results:
            return results[0]['params']
        return None


if __name__ == "__main__":
    """테스트"""
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 최적화 실행
    optimizer = ParameterOptimizer(upbit, market="KRW-ETH")
    best_params = optimizer.get_best_params(days=30)

    if best_params:
        print("=" * 60)
        print("✅ 최적 파라미터 (자동 적용 권장):")
        print("=" * 60)
        for key, value in best_params.items():
            print(f"{key}: {value}")
