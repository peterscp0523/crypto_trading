#!/usr/bin/env python3
"""
궁극의 다층 전략 V3: 멀티 코인 + 동적 리밸런싱

새로운 기능:
1. 다중 코인 포트폴리오 (BTC, ETH, SOL 등)
2. 동적 리밸런싱 (월별 자동 조정)
3. 코인별 독립적 전략 실행
4. 상관관계 기반 리스크 분산
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class MultiCoinStrategy:
    """멀티 코인 + 동적 리밸런싱 전략"""

    def __init__(self, initial_balance=10000000, coins=None):
        self.initial_balance = initial_balance
        self.balance = initial_balance

        # 코인 목록 (기본: BTC만, 나중에 확장)
        self.coins = coins or ['BTC']

        # 코인별 자본 배분 (균등 시작)
        self.coin_allocation = {coin: 1.0 / len(self.coins) for coin in self.coins}

        # 각 코인별 Layer 배분
        self.layer_allocation = {
            'buy_hold': 0.60,
            'momentum_trend': 0.25,
            'momentum_swing': 0.10,
            'volatility': 0.05
        }

        # 코인별 자본 및 포지션
        self.capital = {}
        self.positions = {}
        self.trades = {}

        for coin in self.coins:
            coin_capital = initial_balance * self.coin_allocation[coin]
            self.capital[coin] = {
                'buy_hold': coin_capital * self.layer_allocation['buy_hold'],
                'momentum_trend': coin_capital * self.layer_allocation['momentum_trend'],
                'momentum_swing': coin_capital * self.layer_allocation['momentum_swing'],
                'volatility': coin_capital * self.layer_allocation['volatility']
            }

            self.positions[coin] = {
                'buy_hold': None,
                'momentum_trend': None,
                'momentum_swing': None,
                'volatility': None
            }

            self.trades[coin] = {
                'buy_hold': [],
                'momentum_trend': [],
                'momentum_swing': [],
                'volatility': []
            }

        # 자산 곡선
        self.equity_curve = []

        # 리밸런싱 기록
        self.rebalancing_log = []


    def calculate_momentum_score(self, df, idx):
        """모멘텀 스코어 계산"""
        if idx < 200:
            return 0

        current = df.iloc[idx]
        score = 0

        # 1. 다중 이동평균 배열 (40점)
        ma10 = df.iloc[idx-9:idx+1]['close'].mean()
        ma20 = df.iloc[idx-19:idx+1]['close'].mean()
        ma50 = df.iloc[idx-49:idx+1]['close'].mean()
        ma100 = df.iloc[idx-99:idx+1]['close'].mean()
        ma200 = df.iloc[idx-199:idx+1]['close'].mean()

        if current['close'] > ma10 > ma20 > ma50 > ma100 > ma200:
            score += 40
        elif current['close'] > ma20 > ma50 > ma100:
            score += 30
        elif current['close'] > ma20 > ma50:
            score += 20
        elif current['close'] > ma20:
            score += 10

        # 2. 가격 모멘텀 (30점)
        returns = {
            '5d': (current['close'] - df.iloc[idx-5]['close']) / df.iloc[idx-5]['close'],
            '20d': (current['close'] - df.iloc[idx-20]['close']) / df.iloc[idx-20]['close'],
            '60d': (current['close'] - df.iloc[idx-60]['close']) / df.iloc[idx-60]['close']
        }

        if all(r > 0 for r in returns.values()):
            score += 15
            if returns['5d'] > returns['20d'] > returns['60d']:
                score += 15

        # 3. 볼륨 트렌드 (15점)
        vol_ma20 = df.iloc[idx-19:idx+1]['volume'].mean()
        vol_ma50 = df.iloc[idx-49:idx+1]['volume'].mean()

        if current['volume'] > vol_ma20 > vol_ma50:
            score += 15
        elif current['volume'] > vol_ma20:
            score += 10

        # 4. RSI (15점)
        rsi = self.calculate_rsi(df, idx)
        if 55 < rsi < 70:
            score += 15
        elif 50 < rsi < 75:
            score += 10
        elif rsi < 40:
            score -= 20

        return score


    def execute_buy_hold(self, coin, df, idx):
        """Buy & Hold"""
        if idx == 0 and not self.positions[coin]['buy_hold']:
            price = df.iloc[idx]['close']
            quantity = self.capital[coin]['buy_hold'] / price

            self.positions[coin]['buy_hold'] = {
                'entry_price': price,
                'entry_time': df.iloc[idx]['timestamp'],
                'quantity': quantity,
                'coin': coin
            }

        elif idx == len(df) - 1 and self.positions[coin]['buy_hold']:
            pos = self.positions[coin]['buy_hold']
            exit_price = df.iloc[idx]['close']

            profit = (exit_price - pos['entry_price']) * pos['quantity']
            profit_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100

            self.trades[coin]['buy_hold'].append({
                'entry_time': pos['entry_time'],
                'exit_time': df.iloc[idx]['timestamp'],
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'quantity': pos['quantity'],
                'profit': profit,
                'profit_pct': profit_pct,
                'coin': coin
            })

            self.capital[coin]['buy_hold'] += profit
            self.positions[coin]['buy_hold'] = None


    def execute_momentum_trend(self, coin, df, idx):
        """Momentum Trend"""
        if idx < 200:
            return

        score = self.calculate_momentum_score(df, idx)
        price = df.iloc[idx]['close']

        if not self.positions[coin]['momentum_trend'] and score >= 80:
            quantity = (self.capital[coin]['momentum_trend'] * 0.98) / price
            stop_loss = df.iloc[idx-19:idx+1]['low'].min() * 0.98

            self.positions[coin]['momentum_trend'] = {
                'entry_price': price,
                'entry_time': df.iloc[idx]['timestamp'],
                'quantity': quantity,
                'entry_score': score,
                'stop_loss': stop_loss,
                'coin': coin
            }

        elif self.positions[coin]['momentum_trend']:
            pos = self.positions[coin]['momentum_trend']
            should_exit = (score <= 50) or (price <= pos['stop_loss'])

            if should_exit:
                exit_price = price
                profit = (exit_price - pos['entry_price']) * pos['quantity']
                profit_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100

                fee = (pos['entry_price'] * pos['quantity'] + exit_price * pos['quantity']) * 0.0005
                profit -= fee

                self.trades[coin]['momentum_trend'].append({
                    'entry_time': pos['entry_time'],
                    'exit_time': df.iloc[idx]['timestamp'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'quantity': pos['quantity'],
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'coin': coin
                })

                self.capital[coin]['momentum_trend'] += profit
                self.positions[coin]['momentum_trend'] = None

            else:
                if price > pos['entry_price'] * 1.05:
                    new_stop = max(pos['stop_loss'], pos['entry_price'] * 1.02)
                    self.positions[coin]['momentum_trend']['stop_loss'] = new_stop


    def execute_momentum_swing(self, coin, df, idx):
        """Momentum Swing"""
        if idx < 200:
            return

        score = self.calculate_momentum_score(df, idx)
        price = df.iloc[idx]['close']

        if not self.positions[coin]['momentum_swing'] and 60 <= score < 80:
            quantity = (self.capital[coin]['momentum_swing'] * 0.98) / price
            stop_loss = df.iloc[idx-9:idx+1]['low'].min() * 0.97

            self.positions[coin]['momentum_swing'] = {
                'entry_price': price,
                'entry_time': df.iloc[idx]['timestamp'],
                'quantity': quantity,
                'entry_score': score,
                'stop_loss': stop_loss,
                'coin': coin
            }

        elif self.positions[coin]['momentum_swing']:
            pos = self.positions[coin]['momentum_swing']
            should_exit = (score <= 45) or (price <= pos['stop_loss'])
            profit_target = price >= pos['entry_price'] * 1.15

            if should_exit or profit_target:
                exit_price = price
                profit = (exit_price - pos['entry_price']) * pos['quantity']
                profit_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100

                fee = (pos['entry_price'] * pos['quantity'] + exit_price * pos['quantity']) * 0.0005
                profit -= fee

                self.trades[coin]['momentum_swing'].append({
                    'entry_time': pos['entry_time'],
                    'exit_time': df.iloc[idx]['timestamp'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'quantity': pos['quantity'],
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'coin': coin
                })

                self.capital[coin]['momentum_swing'] += profit
                self.positions[coin]['momentum_swing'] = None


    def execute_volatility_breakout(self, coin, df, idx):
        """Volatility Breakout"""
        if idx < 30:
            return

        price = df.iloc[idx]['close']
        atr = self.calculate_atr(df, idx)

        if not self.positions[coin]['volatility']:
            high_14 = df.iloc[idx-13:idx]['high'].max()
            vol_ma20 = df.iloc[idx-19:idx+1]['volume'].mean()
            volume_surge = df.iloc[idx]['volume'] > vol_ma20 * 1.3

            if price > high_14 and volume_surge:
                quantity = (self.capital[coin]['volatility'] * 0.98) / price

                self.positions[coin]['volatility'] = {
                    'entry_price': price,
                    'entry_time': df.iloc[idx]['timestamp'],
                    'quantity': quantity,
                    'stop_loss': price - atr * 1.5,
                    'target': price + atr * 3,
                    'coin': coin
                }

        elif self.positions[coin]['volatility']:
            pos = self.positions[coin]['volatility']

            if price >= pos['target'] or price <= pos['stop_loss']:
                exit_price = price
                profit = (exit_price - pos['entry_price']) * pos['quantity']
                profit_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100

                fee = (pos['entry_price'] * pos['quantity'] + exit_price * pos['quantity']) * 0.0005
                profit -= fee

                self.trades[coin]['volatility'].append({
                    'entry_time': pos['entry_time'],
                    'exit_time': df.iloc[idx]['timestamp'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'quantity': pos['quantity'],
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'coin': coin
                })

                self.capital[coin]['volatility'] += profit
                self.positions[coin]['volatility'] = None


    def rebalance(self, current_time):
        """
        동적 리밸런싱
        - 월별 1회 실행
        - 각 코인의 성과 평가
        - 우수 코인에 더 많은 자본 배분
        """
        # 각 코인의 현재 자산 계산
        coin_equity = {}
        total_equity = 0

        for coin in self.coins:
            coin_total = sum(self.capital[coin].values())
            coin_equity[coin] = coin_total
            total_equity += coin_total

        # 현재 비중 계산
        current_weights = {coin: equity / total_equity for coin, equity in coin_equity.items()}

        # 성과 기반 목표 비중 계산 (최근 3개월 수익률)
        # 간단한 예: 균등 배분 유지 (확장 시 성과 기반으로 변경)
        target_weights = {coin: 1.0 / len(self.coins) for coin in self.coins}

        # 리밸런싱 실행 (현재 비중 → 목표 비중)
        rebalance_info = {
            'timestamp': current_time,
            'before': current_weights.copy(),
            'after': target_weights.copy(),
            'total_equity': total_equity
        }

        for coin in self.coins:
            target_capital = total_equity * target_weights[coin]

            # Layer별 재배분
            for layer in ['buy_hold', 'momentum_trend', 'momentum_swing', 'volatility']:
                target_layer_capital = target_capital * self.layer_allocation[layer]
                self.capital[coin][layer] = target_layer_capital

        self.rebalancing_log.append(rebalance_info)

        return rebalance_info


    def calculate_rsi(self, df, idx, period=14):
        """RSI 계산"""
        if idx < period:
            return 50

        prices = df.iloc[idx-period:idx+1]['close'].values
        deltas = np.diff(prices)

        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi


    def calculate_atr(self, df, idx, period=14):
        """ATR 계산"""
        if idx < period:
            return df.iloc[idx]['high'] - df.iloc[idx]['low']

        tr_list = []
        for i in range(idx-period+1, idx+1):
            high = df.iloc[i]['high']
            low = df.iloc[i]['low']
            prev_close = df.iloc[i-1]['close'] if i > 0 else low

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)

        return np.mean(tr_list)


    def run_backtest(self, data_dict):
        """
        멀티 코인 백테스트

        Args:
            data_dict: {
                'BTC': DataFrame,
                'ETH': DataFrame,
                ...
            }
        """
        print("=" * 100)
        print("멀티 코인 동적 리밸런싱 전략 백테스트")
        print("=" * 100)
        print(f"\n코인: {', '.join(self.coins)}")
        print(f"초기 자본: {self.initial_balance:,.0f}원")
        print(f"\n코인별 초기 배분:")
        for coin in self.coins:
            print(f"  - {coin}: {self.coin_allocation[coin]*100:.1f}%")
        print()

        # 가장 긴 데이터 기준으로 반복
        max_length = max(len(data_dict[coin]) for coin in self.coins)

        last_rebalance_month = None

        for idx in range(max_length):
            # 각 코인별로 전략 실행
            for coin in self.coins:
                df = data_dict[coin]

                if idx >= len(df):
                    continue

                current_time = df.iloc[idx]['timestamp']

                # 모든 전략 실행
                self.execute_buy_hold(coin, df, idx)
                self.execute_momentum_trend(coin, df, idx)
                self.execute_momentum_swing(coin, df, idx)
                self.execute_volatility_breakout(coin, df, idx)

            # 동적 리밸런싱 (월별)
            current_month = current_time.to_period('M')
            if last_rebalance_month != current_month and idx > 200:
                rebalance_info = self.rebalance(current_time)
                last_rebalance_month = current_month

                if len(self.rebalancing_log) <= 5:  # 처음 5회만 출력
                    print(f"\n📊 리밸런싱 실행: {current_time.strftime('%Y-%m')}")
                    print(f"   총 자산: {rebalance_info['total_equity']:,.0f}원")

            # 자산 곡선 기록 (일별)
            if idx % 6 == 0:
                total_equity = sum(
                    sum(self.capital[coin].values())
                    for coin in self.coins
                )
                self.equity_curve.append({
                    'timestamp': current_time,
                    'equity': total_equity
                })

        return self.analyze_results()


    def analyze_results(self):
        """결과 분석"""
        print("\n" + "=" * 100)
        print("📊 코인별 전략별 상세 결과")
        print("=" * 100)

        total_final = 0
        coin_totals = {}

        for coin in self.coins:
            print(f"\n{'='*100}")
            print(f"🪙 {coin}")
            print(f"{'='*100}")

            coin_final = 0

            for layer in ['buy_hold', 'momentum_trend', 'momentum_swing', 'volatility']:
                trades = self.trades[coin][layer]
                initial = self.initial_balance * self.coin_allocation[coin] * self.layer_allocation[layer]
                final = self.capital[coin][layer]

                print(f"\n{layer.upper().replace('_', ' ')}:")
                print(f"  초기: {initial:,.0f}원 → 최종: {final:,.0f}원")
                print(f"  수익률: {(final - initial) / initial * 100:+.2f}%")
                print(f"  거래: {len(trades)}회")

                if len(trades) > 0:
                    df_trades = pd.DataFrame(trades)
                    wins = len(df_trades[df_trades['profit'] > 0])
                    win_rate = wins / len(trades) * 100

                    total_profit = df_trades[df_trades['profit'] > 0]['profit'].sum()
                    total_loss = abs(df_trades[df_trades['profit'] < 0]['profit'].sum())
                    pf = total_profit / total_loss if total_loss > 0 else float('inf')

                    print(f"  승률: {win_rate:.1f}% | PF: {pf:.2f}")

                coin_final += final

            coin_totals[coin] = coin_final
            total_final += coin_final

        # 전체 결과
        total_return = (total_final - self.initial_balance) / self.initial_balance * 100

        print("\n" + "=" * 100)
        print("📊 전체 포트폴리오 결과")
        print("=" * 100)
        print(f"\n초기 자본: {self.initial_balance:,.0f}원")
        print(f"최종 자본: {total_final:,.0f}원")
        print(f"순손익: {total_final - self.initial_balance:+,.0f}원")
        print(f"총 수익률: {total_return:+.2f}%")

        # 코인별 기여도
        print(f"\n코인별 최종 자산:")
        for coin, final in coin_totals.items():
            pct = (final / total_final) * 100
            profit = final - (self.initial_balance * self.coin_allocation[coin])
            print(f"  - {coin}: {final:,.0f}원 ({pct:.1f}%, 수익 {profit:+,.0f}원)")

        # MDD
        if len(self.equity_curve) > 0:
            df_equity = pd.DataFrame(self.equity_curve)
            df_equity['peak'] = df_equity['equity'].cummax()
            df_equity['drawdown'] = (df_equity['equity'] - df_equity['peak']) / df_equity['peak'] * 100
            mdd = df_equity['drawdown'].min()
            print(f"\n최대 낙폭(MDD): {mdd:.2f}%")

        # 리밸런싱 요약
        if len(self.rebalancing_log) > 0:
            print(f"\n리밸런싱 횟수: {len(self.rebalancing_log)}회")

        print("\n" + "=" * 100)

        return {
            'total_return': total_return,
            'final_balance': total_final,
            'coin_totals': coin_totals,
            'mdd': mdd if len(self.equity_curve) > 0 else 0
        }


def main():
    """메인 함수"""
    try:
        # 여러 코인 데이터 로드
        coins_to_load = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA']
        data_dict = {}

        print("데이터 로드 중...")
        for coin in coins_to_load:
            try:
                df = pd.read_csv(f'upbit_{coin.lower()}_4h.csv')
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                data_dict[coin] = df
                print(f"  ✅ {coin}: {len(df)}개 캔들")
            except FileNotFoundError:
                print(f"  ⚠️ {coin}: 파일 없음 (스킵)")

        if not data_dict:
            print("\n❌ 로드된 데이터가 없습니다.")
            return

        print(f"\n로드된 코인: {', '.join(data_dict.keys())}")
        print(f"기간: {list(data_dict.values())[0]['timestamp'].min()} ~ {list(data_dict.values())[0]['timestamp'].max()}")
        print()

        # 전략 실행
        strategy = MultiCoinStrategy(
            initial_balance=10000000,
            coins=list(data_dict.keys())
        )

        results = strategy.run_backtest(data_dict)

        print("\n✅ 백테스트 완료!")
        print(f"\n최종 성과:")
        print(f"  - 총 수익률: {results['total_return']:+.2f}%")
        print(f"  - 최종 자본: {results['final_balance']:,.0f}원")
        print(f"  - 최대 낙폭: {results['mdd']:.2f}%")

        # 코인별 성과 비교
        print(f"\n코인별 수익률:")
        for coin, final in results['coin_totals'].items():
            initial = strategy.initial_balance * strategy.coin_allocation[coin]
            coin_return = (final - initial) / initial * 100
            print(f"  - {coin}: {coin_return:+.2f}%")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
