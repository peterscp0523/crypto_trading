#!/usr/bin/env python3
"""
박스권 전략 (Range Trading Strategy)

하락/횡보장에서 사용하는 전략:
- 지지선 근처에서 매수, 저항선 근처에서 매도
- 볼린저 밴드 활용
- RSI 과매수/과매도 확인

전략 로직:
1. 횡보 감지: 20MA 기울기가 평탄 (-0.1% ~ +0.1%)
2. 박스권 설정: 최근 N일 고가/저가
3. 매수: 가격이 박스 하단 근처 (10~20% 구간) + RSI < 30
4. 매도:
   - 익절: 박스 상단 근처 (+1.5% ~ +2.5%)
   - 손절: -1.0%
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import requests
import ccxt


class RangeTradingStrategy:
    """박스권 전략"""

    def __init__(self, initial_balance=1000000):
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.equity_curve = []

    def fetch_binance_data(self, symbol, days=180, timeframe='5m'):
        """바이낸스 데이터 수집"""
        print(f"\n📊 바이낸스 {symbol} {days}일 데이터 수집 ({timeframe})...")

        exchange = ccxt.binance()
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

        print(f"✅ {len(df)}개 캔들 수집 완료")

        # USDT → KRW 환산
        usdt_to_krw = 1300
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] * usdt_to_krw

        return df

    def fetch_upbit_data(self, market, days=90, timeframe=5):
        """업비트 데이터 수집"""
        print(f"\n📊 업비트 {market} {days}일 데이터 수집 ({timeframe}분봉)...")

        candles_per_request = 200
        total_candles_needed = min((days * 24 * 60) // timeframe, 10000)

        all_candles = []
        to_time = None

        while len(all_candles) < total_candles_needed:
            try:
                url = f"https://api.upbit.com/v1/candles/minutes/{timeframe}"
                params = {'market': market, 'count': candles_per_request}
                if to_time:
                    params['to'] = to_time

                response = requests.get(url, params=params)
                if response.status_code != 200:
                    break

                candles = response.json()
                if not candles:
                    break

                all_candles.extend(candles)
                to_time = candles[-1]['candle_date_time_kst']
                time.sleep(0.1)

                if len(candles) < candles_per_request:
                    break
            except Exception as e:
                break

        if not all_candles:
            return None

        df = pd.DataFrame(all_candles)
        df = df.iloc[::-1].reset_index(drop=True)

        df_clean = pd.DataFrame({
            'timestamp': pd.to_datetime(df['candle_date_time_kst']),
            'open': df['opening_price'],
            'high': df['high_price'],
            'low': df['low_price'],
            'close': df['trade_price'],
            'volume': df['candle_acc_trade_volume']
        })

        print(f"✅ {len(df_clean)}개 캔들 수집 완료 ({df_clean['timestamp'].min().date()} ~ {df_clean['timestamp'].max().date()})")
        return df_clean

    def calculate_indicators(self, df, box_period=100):
        """지표 계산"""
        # 이동평균
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['sma200'] = df['close'].rolling(window=200).mean()

        # 20MA 기울기
        df['slope'] = ((df['sma20'] - df['sma20'].shift(5)) / df['sma20'].shift(5)) * 100

        # 박스권 (최근 N개 봉의 고가/저가)
        df['box_high'] = df['high'].rolling(window=box_period).max()
        df['box_low'] = df['low'].rolling(window=box_period).min()
        df['box_range'] = df['box_high'] - df['box_low']

        # 박스 내 위치 (0% = 박스 하단, 100% = 박스 상단)
        df['box_position'] = ((df['close'] - df['box_low']) / df['box_range']) * 100

        # RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 볼린저 밴드
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)
        df['bb_position'] = ((df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])) * 100

        # 변동성 (ATR)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()

        # 변동성 비율 (ATR / 가격)
        df['volatility'] = (df['atr'] / df['close']) * 100

        return df

    def is_ranging_market(self, row):
        """횡보장 여부 판단"""
        if pd.isna(row['slope']) or pd.isna(row['box_range']):
            return False

        # 1. 20MA 기울기가 평탄 (-0.1% ~ +0.1%)
        is_flat = -0.1 <= row['slope'] <= 0.1

        # 2. 변동성이 적당 (너무 높지 않음)
        # 변동성이 5% 이하
        low_volatility = row['volatility'] < 5.0 if not pd.isna(row['volatility']) else False

        # 3. 박스 범위가 너무 넓지 않음 (10% 이하)
        box_range_pct = (row['box_range'] / row['close']) * 100
        reasonable_range = box_range_pct < 10.0

        return is_flat and low_volatility and reasonable_range

    def check_entry(self, row):
        """매수 조건"""
        if pd.isna(row['box_position']) or pd.isna(row['rsi']):
            return False, {}

        # 1. 횡보장이어야 함
        is_ranging = self.is_ranging_market(row)

        # 2. 박스 하단 근처 (10~30% 위치)
        at_bottom = 10 <= row['box_position'] <= 30

        # 3. RSI 과매도 (< 35)
        rsi_oversold = row['rsi'] < 35

        # 4. 볼린저 밴드 하단 근처 (< 30%)
        bb_bottom = row['bb_position'] < 30 if not pd.isna(row['bb_position']) else False

        # 최소 조건: 횡보장 + 박스 하단 + RSI 과매도
        qualified = is_ranging and at_bottom and rsi_oversold

        details = {
            'is_ranging': is_ranging,
            'box_position': row['box_position'],
            'rsi': row['rsi'],
            'bb_position': row['bb_position'],
            'slope': row['slope']
        }

        return qualified, details

    def check_exit(self, row, entry_price):
        """매도 조건"""
        current_profit_pct = ((row['close'] - entry_price) / entry_price) * 100

        # 손절: -1.0%
        if current_profit_pct <= -1.0:
            return True, "손절"

        # 익절 1: 박스 상단 근처 (박스 위치 > 70%) + 수익 > 1.5%
        if not pd.isna(row['box_position']):
            if row['box_position'] > 70 and current_profit_pct >= 1.5:
                return True, "박스 상단 익절"

        # 익절 2: RSI 과매수 (> 70) + 수익 > 1.0%
        if not pd.isna(row['rsi']):
            if row['rsi'] > 70 and current_profit_pct >= 1.0:
                return True, "RSI 과매수 익절"

        # 익절 3: 목표 수익률 (+2.5%)
        if current_profit_pct >= 2.5:
            return True, "목표 익절"

        # 긴급 청산: 횡보 깨짐 (기울기 > 0.3% 또는 < -0.3%)
        if not pd.isna(row['slope']):
            if abs(row['slope']) > 0.3:
                return True, "추세 전환"

        return False, None

    def backtest(self, df, box_period=100):
        """백테스팅 실행"""
        self.reset()
        df = self.calculate_indicators(df, box_period)

        for i in range(len(df)):
            row = df.iloc[i]

            # 진입
            if self.position is None:
                is_qualified, details = self.check_entry(row)
                if is_qualified:
                    self.position = {
                        'entry_price': row['close'],
                        'entry_time': row['timestamp'],
                        'quantity': self.balance / row['close']
                    }

            # 청산
            else:
                should_exit, exit_reason = self.check_exit(row, self.position['entry_price'])

                if should_exit:
                    entry_price = self.position['entry_price']
                    current_price = row['close']
                    profit = (current_price - entry_price) * self.position['quantity']
                    self.balance += profit

                    self.trades.append({
                        'entry_time': self.position['entry_time'],
                        'exit_time': row['timestamp'],
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'profit': profit,
                        'profit_pct': ((current_price - entry_price) / entry_price) * 100,
                        'reason': exit_reason
                    })

                    self.position = None

            # 자산 곡선
            current_value = self.balance
            if self.position:
                current_value += self.position['quantity'] * row['close']
            self.equity_curve.append(current_value)

        return self.get_performance()

    def get_performance(self):
        """성과 계산"""
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
        wins = trades_df[trades_df['profit'] > 0]
        losses = trades_df[trades_df['profit'] <= 0]
        win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        avg_profit = wins['profit_pct'].mean() if len(wins) > 0 else 0
        avg_loss = losses['profit_pct'].mean() if len(losses) > 0 else 0
        total_profit = wins['profit'].sum() if len(wins) > 0 else 0
        total_loss = abs(losses['profit'].sum()) if len(losses) > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        equity_series = pd.Series(self.equity_curve)
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax * 100
        max_drawdown = drawdown.min()

        final_balance = self.equity_curve[-1] if self.equity_curve else self.initial_balance
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100

        return {
            'total_trades': len(trades_df),
            'final_balance': final_balance,
            'total_return': total_return,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'trades': trades_df
        }


def run_range_strategy_test():
    """박스권 전략 테스트"""
    print("=" * 100)
    print("박스권 전략 (Range Trading) 테스트")
    print("=" * 100)

    # 바이낸스 테스트
    print("\n[바이낸스 테스트]")
    binance_coins = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
    binance_results = []

    for symbol in binance_coins:
        print(f"\n{'─'*100}")
        print(f"🪙 {symbol}")
        print(f"{'─'*100}")

        tester = RangeTradingStrategy()
        df = tester.fetch_binance_data(symbol, days=180, timeframe='5m')

        if df is not None:
            perf = tester.backtest(df, box_period=100)
            print_performance(perf, symbol)

            binance_results.append({
                'exchange': '바이낸스',
                'symbol': symbol,
                **{k: v for k, v in perf.items() if k != 'trades'}
            })

    # 업비트 테스트
    print("\n\n[업비트 테스트]")
    upbit_coins = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-SOL']
    upbit_results = []

    for market in upbit_coins:
        print(f"\n{'─'*100}")
        print(f"🪙 {market}")
        print(f"{'─'*100}")

        tester = RangeTradingStrategy()
        df = tester.fetch_upbit_data(market, days=90, timeframe=5)

        if df is not None:
            perf = tester.backtest(df, box_period=100)
            print_performance(perf, market)

            upbit_results.append({
                'exchange': '업비트',
                'symbol': market,
                **{k: v for k, v in perf.items() if k != 'trades'}
            })

    # 전체 요약
    print("\n\n" + "=" * 100)
    print("📊 전체 결과 요약")
    print("=" * 100)

    all_results = binance_results + upbit_results
    results_df = pd.DataFrame(all_results)

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.float_format', lambda x: f'{x:.2f}')

    print("\n전체 성과:")
    print(results_df[['exchange', 'symbol', 'total_trades', 'total_return', 'win_rate', 'profit_factor', 'max_drawdown']].to_string(index=False))

    print("\n\n거래소별 평균 성과:")
    avg_by_exchange = results_df.groupby('exchange').agg({
        'total_return': 'mean',
        'win_rate': 'mean',
        'profit_factor': 'mean',
        'max_drawdown': 'mean',
        'total_trades': 'mean'
    }).round(2)
    print(avg_by_exchange.to_string())


def print_performance(perf, name):
    """성과 출력"""
    print(f"\n{name} 결과:")
    print(f"  총 거래: {perf['total_trades']}회")
    print(f"  최종 수익률: {perf['total_return']:.2f}%")
    print(f"  승률: {perf['win_rate']:.2f}%")
    print(f"  평균 수익: {perf['avg_profit']:.2f}%")
    print(f"  평균 손실: {perf['avg_loss']:.2f}%")
    print(f"  Profit Factor: {perf['profit_factor']:.2f}")
    print(f"  MDD: {perf['max_drawdown']:.2f}%")


if __name__ == "__main__":
    run_range_strategy_test()
