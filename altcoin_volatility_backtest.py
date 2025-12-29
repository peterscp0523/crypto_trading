"""
알트코인 고변동성 전략 백테스팅

당신의 제로지 성공 사례 기반:
- 고변동성 코인 선택
- 빠른 익절 (5-10%)
- 엄격한 손절 (-3%)
- 모멘텀 진입

테스트 코인:
- ETH, SOL, XRP, ADA, DOGE, MATIC, LINK, UNI, AVAX, DOT
"""
import pandas as pd
from datetime import datetime, timedelta
import time


class AltcoinVolatilityBacktester:
    """알트코인 변동성 전략 백테스터"""

    def __init__(self, initial_balance=1000000):
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.position_peak = 0
        self.equity_curve = []

    def fetch_binance_data(self, symbol, days=365):
        """바이낸스 알트코인 데이터 수집 (1년)"""
        try:
            import ccxt
        except ImportError:
            print("❌ ccxt 필요")
            return None

        print(f"\n📊 {symbol} {days}일 데이터 수집...")

        exchange = ccxt.binance()
        timeframe = '1h'  # 1시간봉 (빠른 트레이딩)
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

        print(f"✅ {len(df)}개 캔들")

        # KRW 환산
        usdt_to_krw = 1300
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] * usdt_to_krw

        return df

    def calculate_indicators(self, df):
        """변동성 전략용 지표"""
        # 단기 EMA (빠른 진입/퇴출)
        df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()

        # RSI (모멘텀)
        df['rsi'] = self._calc_rsi(df['close'], 14)

        # 볼린저 밴드 (변동성)
        df['bb_middle'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_middle'] - (2 * df['bb_std'])

        # 거래량 증가
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_surge'] = df['volume'] / df['volume_ma']

        # ATR (변동성 측정)
        df['tr'] = df[['high', 'low', 'close']].apply(
            lambda x: max(x['high'] - x['low'],
                         abs(x['high'] - x['close']),
                         abs(x['low'] - x['close'])),
            axis=1
        )
        df['atr'] = df['tr'].rolling(14).mean()

        return df

    def _calc_rsi(self, prices, period=14):
        """RSI 계산"""
        deltas = prices.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = -deltas.where(deltas < 0, 0)
        avg_gain = gains.rolling(window=period).mean()
        avg_loss = losses.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def check_buy_signal(self, row, prev_row):
        """
        매수 신호 - 고변동성 모멘텀 전략

        제로지 성공 사례 기반:
        1. 급등 모멘텀 (EMA5 > EMA10 골든크로스)
        2. RSI 50-70 (상승 모멘텀, 과열 아님)
        3. 거래량 급증 (2배 이상)
        4. BB 중상단 (상승 시작)
        """
        if pd.isna(row['ema5']) or pd.isna(row['ema10']):
            return False
        if pd.isna(row['rsi']):
            return False

        # 1. EMA 골든크로스
        if prev_row is not None and pd.notna(prev_row['ema5']) and pd.notna(prev_row['ema10']):
            golden_cross = (prev_row['ema5'] <= prev_row['ema10'] and
                           row['ema5'] > row['ema10'])
        else:
            golden_cross = row['ema5'] > row['ema10']

        if not golden_cross:
            return False

        # 2. RSI 모멘텀 (50-70)
        if not (50 <= row['rsi'] <= 70):
            return False

        # 3. 거래량 급증 (1.5배 이상)
        if pd.notna(row['volume_surge']):
            if row['volume_surge'] < 1.5:
                return False

        return True

    def check_sell_signal(self, row, position):
        """
        매도 신호 - 빠른 익절/손절

        제로지처럼:
        1. 빠른 익절: 7-10%
        2. 엄격한 손절: -3%
        3. EMA 데드크로스
        """
        if not position:
            return False, None

        buy_price = position['buy_price']
        profit_pct = ((row['close'] - buy_price) / buy_price) * 100

        # 피크 추적
        if profit_pct > self.position_peak:
            self.position_peak = profit_pct

        # 1. 목표 익절 (10%)
        if profit_pct >= 10.0:
            return True, f"목표 ({profit_pct:+.2f}%)"

        # 2. 중간 익절 (7%)
        if profit_pct >= 7.0:
            return True, f"익절 ({profit_pct:+.2f}%)"

        # 3. 트레일링 스톱 (피크에서 3% 하락)
        if self.position_peak >= 5.0 and (self.position_peak - profit_pct) >= 3.0:
            return True, f"트레일링 ({self.position_peak:.2f}% → {profit_pct:+.2f}%)"

        # 4. 손절 (-3%)
        if profit_pct <= -3.0:
            return True, f"손절 ({profit_pct:+.2f}%)"

        # 5. EMA 데드크로스
        if row['ema5'] < row['ema10']:
            if profit_pct > 0:  # 수익 중이면 익절
                return True, f"데드크로스 익절 ({profit_pct:+.2f}%)"
            elif profit_pct <= -1.5:  # 손실 -1.5% 이상이면 손절
                return True, f"데드크로스 손절 ({profit_pct:+.2f}%)"

        return False, None

    def run(self, df, symbol):
        """백테스팅 실행"""
        print(f"\n🔄 {symbol} 백테스팅 시작")

        self.reset()

        prev_row = None
        for idx, row in df.iterrows():
            if idx < 50:  # 지표 계산 최소 데이터
                prev_row = row
                continue

            # 자본 기록
            current_equity = self.balance
            if self.position:
                current_equity += self.position['amount'] * row['close']
            self.equity_curve.append({
                'timestamp': row['timestamp'],
                'equity': current_equity
            })

            # 매수
            if self.position is None and self.balance >= 5000:
                if prev_row is not None and self.check_buy_signal(row, prev_row):
                    invest = int(self.balance * 0.95)
                    fee = invest * 0.001
                    buy_price = row['close']
                    amount = (invest - fee) / buy_price

                    self.position = {
                        'buy_index': idx,
                        'buy_time': row['timestamp'],
                        'buy_price': buy_price,
                        'amount': amount,
                        'invest': invest
                    }
                    self.balance -= invest
                    self.position_peak = 0

            # 매도
            elif self.position is not None:
                should_sell, reason = self.check_sell_signal(row, self.position)

                if should_sell:
                    sell_price = row['close']
                    sell_value = self.position['amount'] * sell_price
                    fee = sell_value * 0.001
                    final_value = sell_value - fee

                    profit = final_value - self.position['invest']
                    profit_pct = (profit / self.position['invest']) * 100
                    hold_hours = (row['timestamp'] - self.position['buy_time']).total_seconds() / 3600

                    self.balance += final_value

                    self.trades.append({
                        'symbol': symbol,
                        'buy_time': self.position['buy_time'],
                        'sell_time': row['timestamp'],
                        'buy_price': self.position['buy_price'],
                        'sell_price': sell_price,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'hold_hours': hold_hours,
                        'reason': reason
                    })

                    self.position = None

            prev_row = row

        # 미체결 청산
        if self.position:
            final_row = df.iloc[-1]
            final_value = self.position['amount'] * final_row['close']
            self.balance += final_value

        return self.analyze(df, symbol)

    def analyze(self, df, symbol):
        """결과 분석"""
        total_return = self.balance - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        # CAGR (1년 기준)
        years = (df['timestamp'].max() - df['timestamp'].min()).days / 365.25
        if years > 0 and self.balance > 0:
            cagr = ((self.balance / self.initial_balance) ** (1 / years) - 1) * 100
        else:
            cagr = 0

        # MDD
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0

        # Buy & Hold
        buy_hold_return = ((df.iloc[-1]['close'] - df.iloc[50]['close']) / df.iloc[50]['close']) * 100

        # 거래 통계
        total_trades = len(self.trades)
        if total_trades > 0:
            winning = sum(1 for t in self.trades if t['profit'] > 0)
            win_rate = (winning / total_trades) * 100
            avg_profit_pct = sum(t['profit_pct'] for t in self.trades) / total_trades
            avg_hold_hours = sum(t['hold_hours'] for t in self.trades) / total_trades
            max_profit = max(t['profit_pct'] for t in self.trades)
            max_loss = min(t['profit_pct'] for t in self.trades)
        else:
            winning = 0
            win_rate = 0
            avg_profit_pct = 0
            avg_hold_hours = 0
            max_profit = 0
            max_loss = 0

        return {
            'symbol': symbol,
            'total_trades': total_trades,
            'winning_trades': winning,
            'win_rate': win_rate,
            'final_balance': self.balance,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'cagr': cagr,
            'avg_profit_pct': avg_profit_pct,
            'avg_hold_hours': avg_hold_hours,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'max_drawdown': max_drawdown,
            'buy_hold_return': buy_hold_return
        }

    def print_results(self, results):
        """결과 출력"""
        print(f"\n{'='*70}")
        print(f"📊 {results['symbol']} 백테스팅 결과")
        print(f"{'='*70}")
        print(f"총 거래: {results['total_trades']}회")
        if results['total_trades'] > 0:
            print(f"승률: {results['win_rate']:.1f}% ({results['winning_trades']}승)")
            print(f"평균 거래: {results['avg_profit_pct']:+.2f}%")
            print(f"평균 보유: {results['avg_hold_hours']:.1f}시간")
            print(f"최대 수익: {results['max_profit']:+.2f}%")
            print(f"최대 손실: {results['max_loss']:+.2f}%")
        print()
        print(f"최종 자본: {results['final_balance']:,.0f}원")
        print(f"총 수익: {results['total_return']:+,.0f}원 ({results['total_return_pct']:+.2f}%)")
        print(f"CAGR: {results['cagr']:.2f}%")
        print(f"MDD: {results['max_drawdown']:.2f}%")
        print()
        print(f"📊 vs Buy & Hold:")
        print(f"   전략: {results['total_return_pct']:+.2f}%")
        print(f"   보유: {results['buy_hold_return']:+.2f}%")
        diff = results['total_return_pct'] - results['buy_hold_return']
        if diff > 0:
            print(f"   ✅ 전략 승리 (+{diff:.2f}%p)")
        else:
            print(f"   ❌ 보유 승리 ({abs(diff):.2f}%p)")
        print(f"{'='*70}")


def run_multi_coin_backtest():
    """여러 알트코인 백테스팅"""

    # 테스트할 코인들 (고변동성 알트코인)
    coins = [
        'ETH/USDT',
        'SOL/USDT',
        'XRP/USDT',
        'ADA/USDT',
        'DOGE/USDT',
        'MATIC/USDT',
        'LINK/USDT',
        'UNI/USDT',
        'AVAX/USDT',
        'DOT/USDT'
    ]

    all_results = []
    all_trades = []

    for coin in coins:
        try:
            backtester = AltcoinVolatilityBacktester(initial_balance=1_000_000)

            # 데이터 수집 (1년)
            df = backtester.fetch_binance_data(coin, days=365)

            if df is None or len(df) < 100:
                print(f"⚠️ {coin} 데이터 부족")
                continue

            # 지표 계산
            df = backtester.calculate_indicators(df)

            # 백테스팅 실행
            results = backtester.run(df, coin)

            # 결과 출력
            backtester.print_results(results)

            all_results.append(results)
            all_trades.extend(backtester.trades)

        except Exception as e:
            print(f"❌ {coin} 실패: {e}")
            continue

    # 전체 결과 요약
    if all_results:
        print(f"\n{'='*70}")
        print("📊 전체 결과 요약")
        print(f"{'='*70}")

        # 정렬 (수익률 높은 순)
        all_results.sort(key=lambda x: x['total_return_pct'], reverse=True)

        print(f"\n{'코인':<12} {'수익률':<10} {'거래':<6} {'승률':<8} {'평균수익':<10} {'vs보유'}")
        print("-" * 70)

        for r in all_results:
            vs_hold = "✅" if r['total_return_pct'] > r['buy_hold_return'] else "❌"
            print(f"{r['symbol']:<12} {r['total_return_pct']:>6.2f}%   "
                  f"{r['total_trades']:>4}회  {r['win_rate']:>5.1f}%  "
                  f"{r['avg_profit_pct']:>6.2f}%   {vs_hold}")

        # 전체 통계
        total_trades = sum(r['total_trades'] for r in all_results)
        avg_return = sum(r['total_return_pct'] for r in all_results) / len(all_results)
        winning_coins = sum(1 for r in all_results if r['total_return_pct'] > 0)

        print(f"\n총 {len(all_results)}개 코인 테스트")
        print(f"총 거래: {total_trades}회")
        print(f"평균 수익률: {avg_return:+.2f}%")
        print(f"수익 코인: {winning_coins}/{len(all_results)}")

        # CSV 저장
        if all_trades:
            trades_df = pd.DataFrame(all_trades)
            trades_df.to_csv('altcoin_volatility_results.csv', index=False, encoding='utf-8-sig')
            print(f"\n💾 저장: altcoin_volatility_results.csv")


if __name__ == "__main__":
    print("=" * 70)
    print("📊 알트코인 고변동성 전략 백테스팅 (1년)")
    print("   제로지 성공 사례 기반")
    print("=" * 70)

    run_multi_coin_backtest()
