#!/usr/bin/env python3
"""
4시간 레인지 재진입 스캘핑 전략 - 바이낸스 백테스팅 (뉴욕 시간 기준)

전략 개요:
- 00:00~04:00 EST 4시간 캔들로 레인지 설정
- 레인지 이탈 후 재진입 시 역방향 진입
- 손익비 최소 1:2 유지
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import ccxt
import pytz


class FourHourRangeBacktest:
    """4시간 레인지 재진입 전략 백테스터 (바이낸스)"""

    def __init__(self, initial_balance=1000000):
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.daily_losses = 0  # 당일 연속 손절 카운트
        self.daily_trades = 0  # 당일 총 거래 횟수
        self.current_date = None
        self.range_high = None
        self.range_low = None
        self.breakout_high = None  # 이탈 시 고점
        self.breakout_low = None   # 이탈 시 저점
        self.has_broken_out = False
        self.breakout_direction = None  # 'up' or 'down'

    def fetch_binance_data(self, symbol='BTC/USDT', days=180):
        """바이낸스 데이터 수집 (5분봉 + 4시간봉)"""
        print(f"\n📊 바이낸스 {symbol} {days}일 데이터 수집...")

        exchange = ccxt.binance()

        # 5분봉 데이터 수집
        print("5분봉 데이터 수집 중...")
        df_5m = self._fetch_timeframe(exchange, symbol, '5m', days)

        # 4시간봉 데이터 수집
        print("4시간봉 데이터 수집 중...")
        df_4h = self._fetch_timeframe(exchange, symbol, '4h', days)

        if df_5m is None or df_4h is None:
            return None, None

        # USDT → KRW 환산
        usdt_to_krw = 1300
        for col in ['open', 'high', 'low', 'close']:
            df_5m[col] = df_5m[col] * usdt_to_krw
            df_4h[col] = df_4h[col] * usdt_to_krw

        # 뉴욕 시간대로 변환
        est = pytz.timezone('America/New_York')
        df_5m['timestamp_est'] = df_5m['timestamp'].dt.tz_localize('UTC').dt.tz_convert(est)
        df_4h['timestamp_est'] = df_4h['timestamp'].dt.tz_localize('UTC').dt.tz_convert(est)

        print(f"✅ 5분봉: {len(df_5m)}개, 4시간봉: {len(df_4h)}개")

        return df_5m, df_4h

    def _fetch_timeframe(self, exchange, symbol, timeframe, days):
        """특정 타임프레임 데이터 수집"""
        limit = 1000
        since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
        all_ohlcv = []

        while True:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1
                if len(ohlcv) < limit:
                    break
                time.sleep(exchange.rateLimit / 1000)
            except Exception as e:
                print(f"❌ {e}")
                break

        if not all_ohlcv:
            return None

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    def get_daily_range(self, df_4h, target_date):
        """해당 날짜의 00:00~04:00 EST 4시간 레인지 찾기"""
        # 00:00~04:00 EST 캔들 찾기 (4시간봉이므로 00:00 시작하는 캔들)
        target_candles = df_4h[
            (df_4h['timestamp_est'].dt.date == target_date) &
            (df_4h['timestamp_est'].dt.hour == 0)
        ]

        if len(target_candles) == 0:
            return None, None

        candle = target_candles.iloc[0]
        return candle['high'], candle['low']

    def is_trading_hours(self, timestamp_est):
        """거래 가능 시간인지 확인 (04:00 ~ 23:59 EST)"""
        hour = timestamp_est.hour
        return hour >= 4

    def check_breakout(self, row):
        """레인지 이탈 확인 (5분봉 종가 기준)"""
        if self.range_high is None or self.range_low is None:
            return False

        close = row['close']

        # 상단 이탈
        if close > self.range_high:
            if not self.has_broken_out or self.breakout_direction != 'up':
                self.has_broken_out = True
                self.breakout_direction = 'up'
                self.breakout_high = row['high']
            else:
                # 이미 이탈 중이면 최고가 갱신
                self.breakout_high = max(self.breakout_high, row['high'])
            return True

        # 하단 이탈
        elif close < self.range_low:
            if not self.has_broken_out or self.breakout_direction != 'down':
                self.has_broken_out = True
                self.breakout_direction = 'down'
                self.breakout_low = row['low']
            else:
                # 이미 이탈 중이면 최저가 갱신
                self.breakout_low = min(self.breakout_low, row['low'])
            return True

        return False

    def check_reentry(self, row):
        """레인지 재진입 확인 (5분봉 종가 기준)"""
        if not self.has_broken_out:
            return False

        close = row['close']

        # 상단 이탈 후 재진입 → Short
        if self.breakout_direction == 'up' and self.range_low <= close <= self.range_high:
            return 'short'

        # 하단 이탈 후 재진입 → Long
        elif self.breakout_direction == 'down' and self.range_low <= close <= self.range_high:
            return 'long'

        return False

    def calculate_stop_loss(self, direction, entry_price):
        """손절가 계산"""
        if direction == 'long':
            # Long: 이탈 당시 최저가
            stop_loss = self.breakout_low
        else:
            # Short: 이탈 당시 최고가
            stop_loss = self.breakout_high

        # 손절폭 확인
        stop_loss_pct = abs((stop_loss - entry_price) / entry_price) * 100

        # 손절폭이 0.6% 이상이면 보정 (0.5%로 제한)
        if stop_loss_pct >= 0.6:
            if direction == 'long':
                stop_loss = entry_price * 0.995  # -0.5%
            else:
                stop_loss = entry_price * 1.005  # +0.5%

        return stop_loss

    def calculate_take_profit(self, direction, entry_price, stop_loss):
        """익절가 계산 (2R)"""
        risk = abs(entry_price - stop_loss)

        if direction == 'long':
            take_profit = entry_price + (risk * 2)
        else:
            take_profit = entry_price - (risk * 2)

        return take_profit

    def check_exit(self, row):
        """청산 조건 확인"""
        if self.position is None:
            return False, None

        direction = self.position['direction']
        entry_price = self.position['entry_price']
        stop_loss = self.position['stop_loss']
        take_profit = self.position['take_profit']
        current_price = row['close']

        # Long 청산
        if direction == 'long':
            if current_price <= stop_loss:
                return True, '손절'
            elif current_price >= take_profit:
                return True, '익절'

        # Short 청산
        else:
            if current_price >= stop_loss:
                return True, '손절'
            elif current_price <= take_profit:
                return True, '익절'

        return False, None

    def backtest(self, df_5m, df_4h):
        """백테스팅 실행"""
        self.reset()

        for i in range(len(df_5m)):
            row = df_5m.iloc[i]
            current_date = row['timestamp_est'].date()

            # 날짜 변경 시 초기화
            if self.current_date != current_date:
                self.current_date = current_date
                self.daily_losses = 0
                self.daily_trades = 0
                self.range_high, self.range_low = self.get_daily_range(df_4h, current_date)
                self.has_broken_out = False
                self.breakout_direction = None
                self.breakout_high = None
                self.breakout_low = None

            # 레인지가 설정되지 않았으면 스킵
            if self.range_high is None or self.range_low is None:
                continue

            # 거래 가능 시간이 아니면 스킵
            if not self.is_trading_hours(row['timestamp_est']):
                continue

            # 연속 2손절 또는 하루 3회 거래 제한
            if self.daily_losses >= 2 or self.daily_trades >= 3:
                continue

            # 포지션이 없을 때
            if self.position is None:
                # 이탈 확인
                self.check_breakout(row)

                # 재진입 확인
                entry_signal = self.check_reentry(row)

                if entry_signal:
                    direction = entry_signal
                    entry_price = row['close']
                    stop_loss = self.calculate_stop_loss(direction, entry_price)
                    take_profit = self.calculate_take_profit(direction, entry_price, stop_loss)

                    # 과도한 변동성 필터 (브레이크아웃 캔들이 레인지의 50% 이상)
                    range_size = self.range_high - self.range_low
                    if direction == 'long':
                        breakout_body = abs(self.breakout_low - self.range_low)
                    else:
                        breakout_body = abs(self.breakout_high - self.range_high)

                    if breakout_body > range_size * 0.5:
                        continue  # 변동성이 너무 크면 스킵

                    # 진입
                    self.position = {
                        'direction': direction,
                        'entry_price': entry_price,
                        'entry_time': row['timestamp_est'],
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'quantity': self.balance / entry_price
                    }
                    self.daily_trades += 1

            # 포지션이 있을 때
            else:
                should_exit, exit_reason = self.check_exit(row)

                if should_exit:
                    exit_price = row['close']
                    direction = self.position['direction']
                    entry_price = self.position['entry_price']

                    # 손익 계산
                    if direction == 'long':
                        profit = (exit_price - entry_price) * self.position['quantity']
                    else:
                        profit = (entry_price - exit_price) * self.position['quantity']

                    profit_pct = (profit / self.balance) * 100

                    # 손절 카운트
                    if exit_reason == '손절':
                        self.daily_losses += 1

                    self.balance += profit

                    self.trades.append({
                        'entry_time': self.position['entry_time'],
                        'exit_time': row['timestamp_est'],
                        'direction': direction,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'stop_loss': self.position['stop_loss'],
                        'take_profit': self.position['take_profit'],
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'reason': exit_reason
                    })

                    self.position = None

            # 자산 곡선
            current_value = self.balance
            if self.position:
                if self.position['direction'] == 'long':
                    current_value += self.position['quantity'] * row['close']
                else:
                    current_value += self.position['quantity'] * (2 * self.position['entry_price'] - row['close'])

            self.equity_curve.append(current_value)

        return self.get_performance()

    def get_performance(self):
        """성과 지표 계산"""
        if not self.trades:
            return {
                'total_trades': 0,
                'final_balance': self.initial_balance,
                'total_return': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_drawdown': 0
            }

        trades_df = pd.DataFrame(self.trades)

        # 승률
        wins = trades_df[trades_df['profit'] > 0]
        losses = trades_df[trades_df['profit'] <= 0]
        win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) > 0 else 0

        # 평균 수익/손실
        avg_profit = wins['profit_pct'].mean() if len(wins) > 0 else 0
        avg_loss = losses['profit_pct'].mean() if len(losses) > 0 else 0

        # Profit Factor
        total_profit = wins['profit'].sum() if len(wins) > 0 else 0
        total_loss = abs(losses['profit'].sum()) if len(losses) > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # MDD
        equity_series = pd.Series(self.equity_curve)
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax * 100
        max_drawdown = drawdown.min()

        final_balance = self.equity_curve[-1] if self.equity_curve else self.initial_balance
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100

        return {
            'total_trades': len(trades_df),
            'win_trades': len(wins),
            'loss_trades': len(losses),
            'final_balance': final_balance,
            'total_return': total_return,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'trades': trades_df
        }


def run_binance_backtest():
    """바이낸스 백테스팅 실행"""
    print("=" * 100)
    print("4시간 레인지 재진입 스캘핑 전략 - 바이낸스 백테스팅 (00:00 EST 기준)")
    print("=" * 100)

    tester = FourHourRangeBacktest(initial_balance=1000000)

    # 데이터 수집
    df_5m, df_4h = tester.fetch_binance_data(symbol='BTC/USDT', days=180)

    if df_5m is None or df_4h is None:
        print("❌ 데이터 수집 실패")
        return

    # 백테스팅 실행
    print("\n백테스팅 실행 중...")
    perf = tester.backtest(df_5m, df_4h)

    # 결과 출력
    print(f"\n{'='*100}")
    print("📊 바이낸스 백테스팅 결과")
    print(f"{'='*100}")
    print(f"총 거래:        {perf['total_trades']}회 (승: {perf['win_trades']}회, 패: {perf['loss_trades']}회)")
    print(f"최종 수익률:    {perf['total_return']:.2f}%")
    print(f"승률:           {perf['win_rate']:.2f}%")
    print(f"평균 수익:      {perf['avg_profit']:.2f}%")
    print(f"평균 손실:      {perf['avg_loss']:.2f}%")
    print(f"Profit Factor:  {perf['profit_factor']:.2f}")
    print(f"MDD:            {perf['max_drawdown']:.2f}%")
    print(f"최종 자산:      {perf['final_balance']:,.0f}원")

    # 거래 상세 내역
    if perf['total_trades'] > 0:
        print(f"\n{'='*100}")
        print("거래 상세 내역 (최근 20개)")
        print(f"{'='*100}")
        trades_df = perf['trades']
        print(trades_df.tail(20).to_string(index=False))


if __name__ == "__main__":
    run_binance_backtest()
