"""
스캘핑 전략 파라미터 최적화
실제 업비트 데이터로 백테스팅하여 최적 파라미터 도출
"""
from datetime import datetime, timedelta
from upbit_api import UpbitAPI
from volatility_strategy import VolatilityScalpingStrategy
import itertools
import json


class ScalpingOptimizer:
    """스캘핑 전략 최적화"""

    def __init__(self, upbit_api):
        self.upbit = upbit_api

    def backtest_params(self, market, params, days=7):
        """
        파라미터 백테스팅

        Args:
            market: 마켓 (예: KRW-BTC)
            params: 테스트할 파라미터
            days: 테스트 기간 (일)

        Returns:
            성과 지표 (총 수익률, 승률, 샤프 비율, 최대 낙폭 등)
        """
        # 테스트용 전략 생성
        strategy = VolatilityScalpingStrategy()

        # 파라미터 적용
        strategy.spike_up_threshold = params['spike_up_threshold']
        strategy.spike_down_threshold = params['spike_down_threshold']
        strategy.strong_change_threshold = params['strong_change_threshold']
        strategy.avg_change_buy_threshold = params['avg_change_buy_threshold']
        strategy.change_5m_threshold = params['change_5m_threshold']

        # 1분봉 데이터 가져오기 (최대 200개)
        try:
            candles_1m = self.upbit.get_candles(market, "minutes", 1, 200)
            candles_5m = self.upbit.get_candles(market, "minutes", 5, 200)
        except Exception as e:
            print(f"  캔들 데이터 조회 실패: {e}")
            return None

        if not candles_1m or not candles_5m or not isinstance(candles_1m, list) or not isinstance(candles_5m, list):
            return None

        # 시뮬레이션 변수
        position = None
        trades = []
        capital = 1000000  # 100만원 시작

        # 캔들 역순으로 순회 (과거 → 현재)
        for i in range(len(candles_1m) - 30, -1, -1):
            # 1분봉 슬라이스 (최신 30개)
            end_1m = i + 30
            candles_1m_slice = list(reversed(candles_1m[i:end_1m]))

            # 5분봉 슬라이스 (1분봉 5개당 5분봉 1개)
            idx_5m = i // 5
            end_5m = min(idx_5m + 20, len(candles_5m))
            candles_5m_slice = list(reversed(candles_5m[idx_5m:end_5m]))

            if len(candles_1m_slice) < 5 or len(candles_5m_slice) < 2:
                continue

            current_price = candles_1m_slice[0]['trade_price']

            # 변동성 체크
            volatility = strategy.calculate_volatility(candles_1m_slice, 20)
            if not volatility:
                continue

            # 모멘텀 체크 (파라미터 적용)
            momentum = self._detect_momentum_with_params(
                candles_1m_slice, candles_5m_slice, params
            )
            if not momentum:
                continue

            # 포지션 없음 → 매수 체크
            if not position:
                buy_signal = self._check_buy_with_params(momentum, volatility, params)

                if buy_signal:
                    # 매수
                    position = {
                        'entry_price': current_price,
                        'entry_time': candles_1m_slice[0]['candle_date_time_kst'],
                        'target_profit': buy_signal['target_profit'],
                        'stop_loss': buy_signal['stop_loss']
                    }

            # 포지션 있음 → 매도 체크
            else:
                profit_rate = ((current_price - position['entry_price']) / position['entry_price']) * 100

                # 익절 or 손절
                if profit_rate >= position['target_profit']:
                    # 익절
                    profit = capital * (profit_rate / 100)
                    capital += profit

                    trades.append({
                        'type': 'PROFIT',
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'profit_rate': profit_rate,
                        'profit': profit
                    })
                    position = None

                elif profit_rate <= position['stop_loss']:
                    # 손절
                    loss = capital * (profit_rate / 100)
                    capital += loss

                    trades.append({
                        'type': 'LOSS',
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'profit_rate': profit_rate,
                        'profit': loss
                    })
                    position = None

        # 성과 계산
        if not trades:
            return None

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['type'] == 'PROFIT')
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_profit = sum(t['profit'] for t in trades)
        total_return = (capital - 1000000) / 1000000 * 100

        # 샤프 비율 (간단 버전)
        returns = [t['profit_rate'] for t in trades]
        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 1
        sharpe = avg_return / std_return if std_return > 0 else 0

        # 최대 낙폭
        peak = 1000000
        max_drawdown = 0
        running_capital = 1000000
        for trade in trades:
            running_capital += trade['profit']
            if running_capital > peak:
                peak = running_capital
            drawdown = (peak - running_capital) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'avg_profit_per_trade': total_profit / total_trades if total_trades > 0 else 0,
            'final_capital': capital
        }

    def _detect_momentum_with_params(self, candles_1m, candles_5m, params):
        """파라미터를 적용한 모멘텀 감지"""
        try:
            if len(candles_1m) < 5 or len(candles_5m) < 2:
                return None

            # 1분봉 변화율
            recent_changes = []
            for i in range(min(5, len(candles_1m)-1)):
                change = ((candles_1m[i]['trade_price'] - candles_1m[i+1]['trade_price'])
                         / candles_1m[i+1]['trade_price']) * 100
                recent_changes.append(change)

            # 5분봉 변화율
            change_5m = ((candles_5m[0]['trade_price'] - candles_5m[1]['trade_price'])
                        / candles_5m[1]['trade_price']) * 100

            # 파라미터 기반 판단
            consecutive_up = sum(1 for c in recent_changes if c > 0)
            strong_up = sum(1 for c in recent_changes if c > params['strong_change_threshold'])

            consecutive_down = sum(1 for c in recent_changes if c < 0)
            strong_down = sum(1 for c in recent_changes if c < -params['strong_change_threshold'])

            change_1m_avg = sum(recent_changes) / len(recent_changes)

            return {
                'spike_up': consecutive_up >= params['spike_up_threshold'] or strong_up >= params['spike_up_threshold'],
                'spike_down': consecutive_down >= params['spike_down_threshold'] or strong_down >= params['spike_down_threshold'],
                'change_1m_avg': change_1m_avg,
                'change_5m': change_5m,
                'strong_momentum': abs(change_5m) > params['change_5m_threshold']
            }
        except Exception as e:
            print(f"모멘텀 감지 실패: {e}")
            return None

    def _check_buy_with_params(self, momentum, volatility, params):
        """파라미터를 적용한 매수 조건 체크"""
        # 조건 1: 급락 후 반등
        if (momentum['spike_down'] and momentum['change_1m_avg'] > -0.5):
            return {
                'target_profit': params['target_profit_1'],
                'stop_loss': params['stop_loss']
            }

        # 조건 2: 상승 모멘텀
        if momentum['spike_up']:
            return {
                'target_profit': params['target_profit_2'],
                'stop_loss': params['stop_loss']
            }

        # 조건 3: 양봉 변동성
        if (momentum['change_1m_avg'] > params['avg_change_buy_threshold'] and
            momentum['change_5m'] > params['change_5m_threshold']):
            return {
                'target_profit': params['target_profit_3'],
                'stop_loss': params['stop_loss']
            }

        return None

    def optimize(self, markets=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'], days=7):
        """
        그리드 서치로 최적 파라미터 찾기
        """
        print("=" * 70)
        print("🔬 스캘핑 전략 최적화 시작")
        print("=" * 70)

        # 파라미터 그리드 (더 완화된 범위로 충분한 트레이드 발생 유도)
        param_grid = {
            'spike_up_threshold': [2, 3],  # 연속 상승 개수 (2-3이 현실적)
            'spike_down_threshold': [2, 3],  # 연속 하락 개수
            'strong_change_threshold': [0.2, 0.3, 0.4],  # 강한 변화율 (더 완화)
            'avg_change_buy_threshold': [0.1, 0.15, 0.2],  # 평균 변화율 (더 완화)
            'change_5m_threshold': [0.3, 0.5, 0.7],  # 5분봉 변화율 (더 완화)
            'target_profit_1': [0.4, 0.6, 0.8],  # 목표 수익 1 (더 현실적)
            'target_profit_2': [0.6, 0.8, 1.0],  # 목표 수익 2
            'target_profit_3': [0.4, 0.6, 0.8],  # 목표 수익 3
            'stop_loss': [-0.6, -0.8, -1.0],  # 손절
        }

        # 모든 조합 생성 (샘플링)
        keys = list(param_grid.keys())

        # 랜덤 샘플링 (전체 조합은 너무 많음)
        import random
        all_combinations = []
        for _ in range(100):  # 100개 랜덤 샘플
            params = {}
            for key in keys:
                params[key] = random.choice(param_grid[key])
            all_combinations.append(params)

        best_score = -float('inf')
        best_params = None
        best_results = {}

        total_tests = len(all_combinations) * len(markets)
        current_test = 0

        for params in all_combinations:
            market_results = {}

            for market in markets:
                current_test += 1
                print(f"\n[{current_test}/{total_tests}] {market} 테스트 중...")

                result = self.backtest_params(market, params, days)

                if result:
                    market_results[market] = result
                    print(f"  승률: {result['win_rate']:.1f}% | "
                          f"수익률: {result['total_return']:+.2f}% | "
                          f"샤프: {result['sharpe_ratio']:.2f}")

            if not market_results:
                continue

            # 최소 거래 횟수 체크 (너무 적은 거래는 의미 없음)
            avg_trades = sum(r['total_trades'] for r in market_results.values()) / len(market_results)
            if avg_trades < 3:  # 평균 3회 미만 거래는 제외
                continue

            # 종합 점수 계산 (승률 40% + 수익률 30% + 샤프 20% + 낙폭 10%)
            avg_win_rate = sum(r['win_rate'] for r in market_results.values()) / len(market_results)
            avg_return = sum(r['total_return'] for r in market_results.values()) / len(market_results)
            avg_sharpe = sum(r['sharpe_ratio'] for r in market_results.values()) / len(market_results)
            avg_drawdown = sum(r['max_drawdown'] for r in market_results.values()) / len(market_results)

            score = (avg_win_rate * 0.4 +
                    avg_return * 0.3 +
                    avg_sharpe * 10 * 0.2 -  # 샤프 비율 스케일링
                    avg_drawdown * 0.1)

            if score > best_score:
                best_score = score
                best_params = params
                best_results = market_results

        print("\n" + "=" * 70)
        print("✅ 최적화 완료!")
        print("=" * 70)

        if best_params:
            print("\n🏆 최적 파라미터:")
            for key, value in best_params.items():
                print(f"  {key}: {value}")

            print(f"\n📊 종합 점수: {best_score:.2f}")

            print("\n📈 마켓별 성과:")
            for market, result in best_results.items():
                print(f"\n{market}:")
                print(f"  총 거래: {result['total_trades']}회")
                print(f"  승률: {result['win_rate']:.1f}%")
                print(f"  총 수익률: {result['total_return']:+.2f}%")
                print(f"  샤프 비율: {result['sharpe_ratio']:.2f}")
                print(f"  최대 낙폭: {result['max_drawdown']:.2f}%")
                print(f"  거래당 평균 수익: {result['avg_profit_per_trade']:+,.0f}원")

            # 파라미터 저장
            output = {
                'optimized_at': datetime.now().isoformat(),
                'best_params': best_params,
                'score': best_score,
                'results': {k: {**v, 'market': k} for k, v in best_results.items()}
            }

            with open('optimized_scalping_params.json', 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            print("\n✅ 최적 파라미터가 'optimized_scalping_params.json'에 저장되었습니다.")

            return best_params, best_results
        else:
            print("\n❌ 최적화 실패: 유효한 결과가 없습니다.")
            return None, None


if __name__ == "__main__":
    from config import get_config

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    optimizer = ScalpingOptimizer(upbit)

    # 최적화 실행 (BTC, ETH, XRP 대상, 최근 7일 데이터)
    best_params, results = optimizer.optimize(
        markets=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'],
        days=7
    )

    if best_params:
        print("\n" + "=" * 70)
        print("📋 다음 단계: volatility_strategy.py에 최적 파라미터를 적용하세요!")
        print("=" * 70)
