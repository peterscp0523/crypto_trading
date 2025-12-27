"""
자동 파라미터 최적화 스케줄러
데이터베이스에 저장된 캔들 데이터로 주기적 최적화 수행
"""
import time
from datetime import datetime, timedelta
from database_manager import DatabaseManager
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators


class AutoOptimizer:
    """자동 파라미터 최적화"""

    def __init__(self, db, market="KRW-ETH"):
        self.db = db
        self.market = market

    def backtest_from_db(self, params, days=30):
        """
        데이터베이스의 캔들로 백테스팅

        Args:
            params: 파라미터 세트
            days: 백테스트 기간 (일)
        """
        # DB에서 캔들 조회
        candles = self.db.get_candles(self.market, '15m', days=days)

        if len(candles) < 100:
            print(f"⚠️ {self.market} 데이터 부족 (현재: {len(candles)}개)")
            return None

        # 백테스팅 로직 (parameter_optimizer.py와 동일)
        prices = [c['trade_price'] for c in candles]
        volumes = [c['candle_acc_trade_volume'] for c in candles]

        capital = 1000000
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

                if profit_rate > peak_profit:
                    peak_profit = profit_rate

                sell = False
                reason = ""

                # 퀵 익절
                if i - position['buy_index'] <= 10 and profit_rate >= params['quick_profit']:
                    sell = True
                    reason = "quick"
                elif profit_rate >= params['take_profit_1']:
                    sell = True
                    reason = "tp1"
                elif profit_rate <= params['stop_loss']:
                    sell = True
                    reason = "sl"
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

            # 포지션 없음 - 매수
            else:
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

        # 샤프 비율
        if len(trades) > 1:
            returns = [t['profit_rate'] for t in trades]
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            sharpe = avg_return / std_dev if std_dev > 0 else 0
        else:
            sharpe = 0

        return {
            'total_return': total_return,
            'num_trades': len(trades),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'sharpe_ratio': sharpe,
            'score': total_return * 0.4 + win_rate * 0.3 + sharpe * 100 * 0.3
        }

    def optimize(self, days=30):
        """
        그리드 서치 최적화

        Args:
            days: 백테스트 기간 (일)
        """
        print(f"\n{'='*60}")
        print(f"🔍 자동 최적화 시작 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(f"마켓: {self.market}")
        print(f"기간: {days}일")
        print(f"{'='*60}\n")

        # 파라미터 그리드
        param_grid = {
            'quick_profit': [0.005, 0.008, 0.010, 0.012],
            'take_profit_1': [0.012, 0.015, 0.020, 0.025],
            'stop_loss': [-0.010, -0.015, -0.020, -0.025],
            'trailing_stop_tight': [0.002, 0.003, 0.005]
        }

        results = []
        total_combinations = (len(param_grid['quick_profit']) *
                            len(param_grid['take_profit_1']) *
                            len(param_grid['stop_loss']) *
                            len(param_grid['trailing_stop_tight']))

        print(f"🔄 총 {total_combinations}개 조합 테스트...\n")

        count = 0
        for qp in param_grid['quick_profit']:
            for tp1 in param_grid['take_profit_1']:
                for sl in param_grid['stop_loss']:
                    for ts in param_grid['trailing_stop_tight']:
                        count += 1

                        # 논리적 검증
                        if qp >= tp1 or abs(sl) > tp1:
                            continue

                        params = {
                            'quick_profit': qp,
                            'take_profit_1': tp1,
                            'take_profit_2': 0.025,  # 고정
                            'stop_loss': sl,
                            'trailing_stop_tight': ts,
                            'trailing_stop_medium': 0.005,  # 고정
                            'trailing_stop_wide': 0.008  # 고정
                        }

                        result = self.backtest_from_db(params, days)

                        if result and result['num_trades'] >= 3:
                            result['params'] = params
                            results.append(result)

                            if count % 20 == 0:
                                print(f"  진행: {count}/{total_combinations} | 유효: {len(results)}개")

        if not results:
            print("❌ 유효한 결과 없음")
            return None

        # 점수 기준 정렬
        results.sort(key=lambda x: x['score'], reverse=True)
        best = results[0]

        print(f"\n{'='*60}")
        print(f"🏆 최적 파라미터 발견!")
        print(f"{'='*60}\n")

        p = best['params']
        print(f"종합점수: {best['score']:.2f}")
        print(f"\n파라미터:")
        print(f"  • 퀵익절: {p['quick_profit']*100:.1f}%")
        print(f"  • 1차익절: {p['take_profit_1']*100:.1f}%")
        print(f"  • 2차익절: {p['take_profit_2']*100:.1f}%")
        print(f"  • 손절: {p['stop_loss']*100:.1f}%")
        print(f"  • 트레일링(타이트): {p['trailing_stop_tight']*100:.1f}%")
        print(f"  • 트레일링(중간): {p['trailing_stop_medium']*100:.1f}%")
        print(f"  • 트레일링(넓음): {p['trailing_stop_wide']*100:.1f}%")
        print(f"\n백테스트 성과:")
        print(f"  • 총수익률: {best['total_return']:+.2f}%")
        print(f"  • 거래횟수: {best['num_trades']}회")
        print(f"  • 승률: {best['win_rate']:.1f}%")
        print(f"  • 샤프비율: {best['sharpe_ratio']:.3f}")
        print(f"{'='*60}\n")

        # 데이터베이스에 저장
        self.db.save_optimization_result(self.market, p, best)
        print("✅ 최적 파라미터 DB 저장 완료\n")

        return p

    def run_weekly_optimization(self, target_markets=None):
        """
        주간 자동 최적화 실행

        Args:
            target_markets: 최적화할 마켓 리스트 (None이면 현재 마켓만)
        """
        markets = target_markets or [self.market]

        print(f"\n{'='*60}")
        print(f"📅 주간 자동 최적화")
        print(f"{'='*60}")
        print(f"일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"대상: {markets}")
        print(f"{'='*60}\n")

        for market in markets:
            self.market = market
            try:
                self.optimize(days=30)
                time.sleep(2)  # 마켓 간 대기
            except Exception as e:
                print(f"❌ {market} 최적화 실패: {e}\n")

        print(f"{'='*60}")
        print("✅ 주간 최적화 완료")
        print(f"{'='*60}\n")

    def run_scheduler(self, interval_days=7):
        """
        주기적 최적화 스케줄러

        Args:
            interval_days: 최적화 주기 (일)
        """
        print(f"🔄 자동 최적화 스케줄러 시작 (주기: {interval_days}일)")

        while True:
            try:
                self.run_weekly_optimization()

                # 다음 최적화 시간
                next_time = datetime.now() + timedelta(days=interval_days)
                print(f"⏰ 다음 최적화: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

                time.sleep(interval_days * 24 * 60 * 60)

            except KeyboardInterrupt:
                print("\n최적화 스케줄러 중지")
                break
            except Exception as e:
                print(f"❌ 최적화 오류: {e}")
                print(f"⏰ 1시간 후 재시도...")
                time.sleep(3600)


if __name__ == "__main__":
    """테스트 및 실행"""
    import os

    # 데이터베이스 초기화
    use_oracle = os.environ.get('USE_ORACLE_DB', 'false').lower() == 'true'
    db = DatabaseManager(use_oracle=use_oracle)

    # 최적화기 생성
    market = os.environ.get('MARKET', 'KRW-ETH')
    optimizer = AutoOptimizer(db, market=market)

    # 1회 최적화 테스트
    print("=== 1회 최적화 테스트 ===")
    best_params = optimizer.optimize(days=30)

    # 스케줄러 실행 여부
    run_scheduler = os.environ.get('RUN_AUTO_OPTIMIZER', 'false').lower() == 'true'

    if run_scheduler:
        # 주기적 최적화 시작 (7일마다)
        optimizer.run_scheduler(interval_days=7)
    else:
        print("\n💡 스케줄러를 실행하려면 RUN_AUTO_OPTIMIZER=true 환경변수 설정")
        db.close()
