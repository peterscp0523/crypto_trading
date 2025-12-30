#!/usr/bin/env python3
"""
하이브리드 전략 (Hybrid Strategy)

시장 상황에 따라 자동 전환:
1. BOX MODE: 횡보장 → 박스권 전략
2. TREND MODE: 추세장 → 20/200 SMA 전략

박스 모드 진입 조건 (모두 충족):
- 20MA 기울기 ≈ 0 (-0.1% ~ +0.1%)
- 200MA 하락 또는 횡보 (기울기 < 0.2%)
- 최근 N봉 가격 변동폭 6~8%
- ATR 감소 (변동성 수축)
- 고점/저점 수렴 (박스 형성)

추세 모드 진입 조건 (하나라도 충족):
- 강한 거래량 + 박스 돌파
- 20MA 기울기 명확 (> 0.2% 또는 < -0.2%)
- 가격이 20MA 위/아래 연속 안착
- ATR 증가 (변동성 확장)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import requests
import ccxt


class HybridStrategy:
    """하이브리드 전략 (박스권 + 추세 추종)"""

    def __init__(self, initial_balance=1000000):
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.partial_sold = False
        self.mode_history = []  # 모드 전환 이력

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

        # 기울기
        df['slope_20ma'] = ((df['sma20'] - df['sma20'].shift(5)) / df['sma20'].shift(5)) * 100
        df['slope_200ma'] = ((df['sma200'] - df['sma200'].shift(20)) / df['sma200'].shift(20)) * 100

        # 박스권
        df['box_high'] = df['high'].rolling(window=box_period).max()
        df['box_low'] = df['low'].rolling(window=box_period).min()
        df['box_range'] = df['box_high'] - df['box_low']
        df['box_range_pct'] = (df['box_range'] / df['close']) * 100
        df['box_position'] = ((df['close'] - df['box_low']) / df['box_range']) * 100

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR (변동성)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100

        # ATR 변화율 (변동성 확장/수축)
        df['atr_change'] = df['atr'].pct_change(5) * 100

        # 거래량 급증
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 20MA와의 거리
        df['distance_to_20ma'] = ((df['close'] - df['sma20']) / df['sma20']) * 100

        return df

    def detect_market_mode(self, row, prev_mode='BOX'):
        """
        시장 모드 감지 (안정화 버전)

        Args:
            prev_mode: 이전 모드 (전환 저항 추가)

        Returns:
            str: 'BOX' 또는 'TREND'
        """
        if pd.isna(row['slope_20ma']) or pd.isna(row['slope_200ma']):
            return 'BOX'  # 기본값을 BOX로 변경 (현재 시장 반영)

        # === BOX MODE 조건 ===

        # 1. 20MA 기울기 평탄 (-0.15% ~ +0.15%) - 범위 확대
        ma20_flat = -0.15 <= row['slope_20ma'] <= 0.15

        # 2. 200MA 하락 또는 횡보 (< 0.15%) - 더 엄격
        ma200_not_rising = row['slope_200ma'] < 0.15

        # 3. 박스 범위 4~10% - 범위 확대
        box_range_ok = 4.0 <= row['box_range_pct'] <= 10.0 if not pd.isna(row['box_range_pct']) else False

        # 4. 변동성 낮음 (< 4%) - 완화
        low_volatility = row['atr_pct'] < 4.0 if not pd.isna(row['atr_pct']) else False

        # === TREND MODE 조건 (더 엄격하게) ===

        # 1. 20MA 기울기 명확 (> 0.3% 또는 < -0.3%) - 더 엄격
        ma20_strong_trend = abs(row['slope_20ma']) > 0.3

        # 2. 200MA도 같은 방향 (추세 확인)
        ma200_trending = abs(row['slope_200ma']) > 0.15

        # 3. 20MA와 200MA 같은 방향
        same_direction = (row['slope_20ma'] > 0 and row['slope_200ma'] > 0) or \
                        (row['slope_20ma'] < 0 and row['slope_200ma'] < 0)

        # 4. ATR 증가 (변동성 확장) - 더 엄격
        atr_increasing = row['atr_change'] > 15.0 if not pd.isna(row['atr_change']) else False

        # 5. 강한 거래량 (평균의 2배 이상) - 더 엄격
        strong_volume = row['volume_ratio'] > 2.0 if not pd.isna(row['volume_ratio']) else False

        # === 모드 결정 (히스테리시스 적용) ===

        # BOX → TREND 전환: 매우 명확한 추세 신호 필요
        if prev_mode == 'BOX':
            # 2개 이상 충족 시 TREND로 전환
            trend_signals = [ma20_strong_trend and same_direction,
                           atr_increasing,
                           strong_volume]
            if sum(trend_signals) >= 2:
                return 'TREND'
            else:
                return 'BOX'

        # TREND → BOX 전환: 명확한 횡보 신호 필요
        else:  # prev_mode == 'TREND'
            # 3개 이상 충족 시 BOX로 전환
            box_signals = [ma20_flat, ma200_not_rising, box_range_ok, low_volatility]
            if sum(box_signals) >= 3:
                return 'BOX'
            else:
                return 'TREND'

    def check_entry_trend(self, row):
        """추세 전략 진입 조건 (20/200 SMA)"""
        if pd.isna(row['sma20']) or pd.isna(row['sma200']):
            return False

        uptrend = row['slope_20ma'] > 0.2
        above_200ma = row['close'] > row['sma200']
        near_20ma = abs(row['distance_to_20ma']) <= 3.0

        return uptrend and above_200ma and near_20ma

    def check_entry_box(self, row):
        """박스권 전략 진입 조건"""
        if pd.isna(row['box_position']) or pd.isna(row['rsi']):
            return False

        at_bottom = 10 <= row['box_position'] <= 30
        rsi_oversold = row['rsi'] < 35

        return at_bottom and rsi_oversold

    def check_exit_trend(self, row, entry_price):
        """추세 전략 청산 조건"""
        current_profit_pct = ((row['close'] - entry_price) / entry_price) * 100

        # 손절: -0.7%
        if current_profit_pct <= -0.7:
            return True, "손절"

        # 부분 익절 후
        if self.partial_sold:
            if current_profit_pct >= 3.0:
                return True, "목표 익절"
            if row['close'] < row['sma20']:
                return True, "20MA 이탈"

        # 부분 익절 전
        if not self.partial_sold and current_profit_pct >= 1.5:
            return True, "부분 익절"

        return False, None

    def check_exit_box(self, row, entry_price):
        """박스권 전략 청산 조건"""
        current_profit_pct = ((row['close'] - entry_price) / entry_price) * 100

        # 손절: -1.0%
        if current_profit_pct <= -1.0:
            return True, "손절"

        # 박스 상단 익절
        if not pd.isna(row['box_position']):
            if row['box_position'] > 70 and current_profit_pct >= 1.5:
                return True, "박스 상단 익절"

        # RSI 과매수 익절
        if not pd.isna(row['rsi']):
            if row['rsi'] > 70 and current_profit_pct >= 1.0:
                return True, "RSI 과매수 익절"

        # 목표 익절
        if current_profit_pct >= 2.5:
            return True, "목표 익절"

        return False, None

    def backtest(self, df, box_period=100):
        """백테스팅 실행"""
        self.reset()
        df = self.calculate_indicators(df, box_period)

        current_mode = 'BOX'  # 초기 모드

        for i in range(len(df)):
            row = df.iloc[i]

            # 모드 감지 (이전 모드 전달)
            detected_mode = self.detect_market_mode(row, prev_mode=current_mode)

            # 모드 전환 기록
            if detected_mode != current_mode:
                self.mode_history.append({
                    'timestamp': row['timestamp'],
                    'from_mode': current_mode,
                    'to_mode': detected_mode
                })
                current_mode = detected_mode

            # 진입 로직
            if self.position is None:
                entry_signal = False

                if current_mode == 'TREND':
                    entry_signal = self.check_entry_trend(row)
                elif current_mode == 'BOX':
                    entry_signal = self.check_entry_box(row)

                if entry_signal:
                    self.position = {
                        'entry_price': row['close'],
                        'entry_time': row['timestamp'],
                        'quantity': self.balance / row['close'],
                        'entry_mode': current_mode
                    }
                    self.partial_sold = False

            # 청산 로직
            else:
                should_exit = False
                exit_reason = None

                # 진입했던 모드의 청산 조건 사용
                if self.position['entry_mode'] == 'TREND':
                    should_exit, exit_reason = self.check_exit_trend(row, self.position['entry_price'])
                elif self.position['entry_mode'] == 'BOX':
                    should_exit, exit_reason = self.check_exit_box(row, self.position['entry_price'])

                if should_exit:
                    entry_price = self.position['entry_price']
                    current_price = row['close']

                    # 부분 익절 (TREND 모드만)
                    if exit_reason == "부분 익절" and self.position['entry_mode'] == 'TREND':
                        sell_quantity = self.position['quantity'] * 0.5
                        profit = (current_price - entry_price) * sell_quantity
                        self.balance += profit
                        self.position['quantity'] -= sell_quantity
                        self.partial_sold = True

                        self.trades.append({
                            'entry_time': self.position['entry_time'],
                            'exit_time': row['timestamp'],
                            'entry_price': entry_price,
                            'exit_price': current_price,
                            'profit': profit,
                            'profit_pct': ((current_price - entry_price) / entry_price) * 100,
                            'reason': exit_reason,
                            'mode': self.position['entry_mode'],
                            'type': '부분(50%)'
                        })

                    # 전체 청산
                    else:
                        profit = (current_price - entry_price) * self.position['quantity']
                        self.balance += profit

                        self.trades.append({
                            'entry_time': self.position['entry_time'],
                            'exit_time': row['timestamp'],
                            'entry_price': entry_price,
                            'exit_price': current_price,
                            'profit': profit,
                            'profit_pct': ((current_price - entry_price) / entry_price) * 100,
                            'reason': exit_reason,
                            'mode': self.position['entry_mode'],
                            'type': '전체' if not self.partial_sold else '나머지(50%)'
                        })

                        self.position = None
                        self.partial_sold = False

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
                'trend_trades': 0,
                'box_trades': 0,
                'final_balance': self.initial_balance,
                'total_return': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'mode_changes': len(self.mode_history)
            }

        trades_df = pd.DataFrame(self.trades)

        # 모드별 거래 수
        trend_trades = len(trades_df[trades_df['mode'] == 'TREND'])
        box_trades = len(trades_df[trades_df['mode'] == 'BOX'])

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
            'trend_trades': trend_trades,
            'box_trades': box_trades,
            'final_balance': final_balance,
            'total_return': total_return,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'mode_changes': len(self.mode_history),
            'trades': trades_df
        }


def run_hybrid_test():
    """하이브리드 전략 테스트"""
    print("=" * 100)
    print("하이브리드 전략 (박스권 + 추세 추종) 테스트")
    print("=" * 100)

    # 바이낸스 테스트
    print("\n[바이낸스 테스트]")
    binance_coins = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
    binance_results = []

    for symbol in binance_coins:
        print(f"\n{'─'*100}")
        print(f"🪙 {symbol}")
        print(f"{'─'*100}")

        tester = HybridStrategy()
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

        tester = HybridStrategy()
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
    print(results_df[['exchange', 'symbol', 'total_trades', 'trend_trades', 'box_trades',
                      'total_return', 'win_rate', 'profit_factor', 'mode_changes']].to_string(index=False))

    print("\n\n거래소별 평균 성과:")
    avg_by_exchange = results_df.groupby('exchange').agg({
        'total_return': 'mean',
        'win_rate': 'mean',
        'profit_factor': 'mean',
        'max_drawdown': 'mean',
        'total_trades': 'mean',
        'trend_trades': 'mean',
        'box_trades': 'mean',
        'mode_changes': 'mean'
    }).round(2)
    print(avg_by_exchange.to_string())


def print_performance(perf, name):
    """성과 출력"""
    print(f"\n{name} 결과:")
    print(f"  총 거래: {perf['total_trades']}회 (추세: {perf['trend_trades']}회, 박스: {perf['box_trades']}회)")
    print(f"  모드 전환: {perf['mode_changes']}회")
    print(f"  최종 수익률: {perf['total_return']:.2f}%")
    print(f"  승률: {perf['win_rate']:.2f}%")
    print(f"  Profit Factor: {perf['profit_factor']:.2f}")
    print(f"  MDD: {perf['max_drawdown']:.2f}%")


if __name__ == "__main__":
    run_hybrid_test()
