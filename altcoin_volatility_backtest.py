"""
20/200 SMA 전문가 추세 추종 전략

핵심 원칙:
1. 추세 구간에서만 거래 (20MA 평탄 시 거래 금지)
2. 작게 지고, 크게 먹는다 (손절 -0.7%, 손익비 2:1)
3. 과도한 확장 구간 진입 금지 (20MA에서 ±3% 이내만)
4. 200MA는 방향성 기준 (위=롱만, 아래=거래금지)
5. 부분 익절 + 추적 손절로 수익 극대화

매수 조건 (모두 충족 필요):
1. 20MA 명확한 상승 중 (기울기 0.2% 이상)
2. 가격 > 200MA (구조적 상승 바이어스)
3. 가격이 20MA 근처 (±3% 이내, 과확장 회피)

매도 조건:
1. 손절: -0.7% (빠른 손절)
2. 부분 익절: +1.5%에서 50% 청산
3. 나머지: 20MA 이탈 또는 +3% 도달
4. 긴급: 추세 전환 (20MA 하락 전환)

손익비: 1 : 2+ (작게 지고, 크게 먹는다)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time


class SMA_20_200_Backtester:
    """20/200 SMA 단순 추세 전략"""

    def __init__(self, initial_balance=1000000):
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.prev_sma20 = None
        self.partial_sold = False  # 부분 익절 플래그

    def fetch_binance_data(self, symbol, days=365, timeframe='5m'):
        """바이낸스 데이터 수집 (1년)"""
        try:
            import ccxt
        except ImportError:
            print("❌ ccxt 필요: pip install ccxt")
            return None

        print(f"\n📊 {symbol} {days}일 데이터 수집 ({timeframe})...")

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

        print(f"✅ {len(df)}개 캔들 ({df['timestamp'].min().date()} ~ {df['timestamp'].max().date()}) - {timeframe}")

        # KRW 환산 (1 USDT = 1300 KRW)
        usdt_to_krw = 1300
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] * usdt_to_krw

        return df

    def calculate_indicators(self, df):
        """
        오직 SMA 20과 SMA 200만 계산

        - SMA 20: 단기 추세 및 진입 타이밍
        - SMA 200: 장기 구조선 (지지/저항)
        """
        # 단순 이동평균 (Simple Moving Average)
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['sma200'] = df['close'].rolling(window=200).mean()

        # 20MA 기울기 계산 (추세 방향)
        df['sma20_prev'] = df['sma20'].shift(1)
        df['sma20_slope'] = (df['sma20'] - df['sma20_prev']) / df['sma20_prev']

        # 가격과 MA 간 거리 (%)
        df['distance_to_20ma'] = (df['close'] - df['sma20']) / df['sma20'] * 100
        df['distance_to_200ma'] = (df['close'] - df['sma200']) / df['sma200'] * 100

        # MA 간 갭 (스퀴즈 감지용)
        df['ma_gap'] = abs(df['sma20'] - df['sma200']) / df['sma200'] * 100

        return df

    def get_trend_state(self, row):
        """
        20MA 기울기로 추세 판단 (엄격한 기준)

        Returns:
            'uptrend': 명확한 상승 추세
            'downtrend': 명확한 하락 추세
            'sideways': 횡보 (거래 금지!)
        """
        if pd.isna(row['sma20_slope']):
            return 'unknown'

        slope = row['sma20_slope']

        # 엄격한 추세 기준: 0.2% 이상 기울기 필요
        if slope > 0.002:  # 0.2% 이상 상승
            return 'uptrend'
        elif slope < -0.002:  # 0.2% 이상 하락
            return 'downtrend'
        else:
            return 'sideways'  # 횡보장 - 거래 금지!

    def check_buy_signal(self, row, prev_row):
        """
        매수 신호 - 전문가 추세 추종 원칙

        핵심: 추세 구간에서만 거래, 횡보장 완전 배제

        조건 (모두 충족 필요):
        1. 20MA 명확한 상승 중 (기울기 0.2%+, 횡보 필터)
        2. 가격 > 200MA (구조적 상승 바이어스)
        3. 20MA 근처 진입 (±3% 이내, 과확장 회피)
        """
        # 데이터 검증
        if pd.isna(row['sma20']) or pd.isna(row['sma200']):
            return False

        # 1. 20MA 명확한 상승 확인 (횡보장 필터!)
        trend = self.get_trend_state(row)
        if trend != 'uptrend':
            return False  # 횡보 또는 하락 시 거래 금지

        # 2. 구조적 바이어스: 가격 > 200MA (방향성)
        if row['close'] < row['sma200']:
            return False

        # 3. 과도한 확장 구간 회피: 20MA에서 ±3% 이내만 진입
        distance = row['distance_to_20ma']
        if abs(distance) > 3.0:
            return False  # 20MA에서 너무 멀면 진입 금지

        return True

    def check_sell_signal(self, row, position):
        """
        매도 신호 - 짧은 손절 + 부분 익절

        핵심: 작게 지고, 크게 먹는다

        조건:
        1. 손절: -0.7% (빠른 손절, 진입 논리 깨짐)
        2. 부분 익절: +1.5%에서 50% 청산
        3. 나머지: 20MA 이탈 또는 +3% 도달
        4. 긴급: 추세 전환 시 즉시 청산
        """
        if not position:
            return False, None, None

        buy_price = position['buy_price']
        profit_pct = ((row['close'] - buy_price) / buy_price) * 100

        # 1. 손절 -0.7% (짧고 빠르게)
        if profit_pct <= -0.7:
            return True, "full", f"손절 ({profit_pct:+.2f}%)"

        # 2. 부분 익절: +1.5%에서 50% 청산
        if profit_pct >= 1.5 and not self.partial_sold:
            return True, "partial", f"부분익절 50% ({profit_pct:+.2f}%)"

        # 부분 익절 후 나머지 처리
        if self.partial_sold:
            # 3-1. 나머지 익절: +3% 도달
            if profit_pct >= 3.0:
                return True, "full", f"최종익절 ({profit_pct:+.2f}%)"

            # 3-2. 20MA 이탈 시 나머지 청산
            if row['close'] < row['sma20']:
                return True, "full", f"20MA이탈 ({profit_pct:+.2f}%)"

        # 4. 긴급: 추세 전환 시 즉시 전량 청산
        trend = self.get_trend_state(row)
        if trend == 'downtrend':
            return True, "full", f"추세전환 ({profit_pct:+.2f}%)"

        # 5. 추가 안전장치: 20MA 이탈 + 손실 중
        if row['close'] < row['sma20'] and profit_pct < 0:
            return True, "full", f"20MA이탈손절 ({profit_pct:+.2f}%)"

        return False, None, None

    def run(self, df, symbol, timeframe='5m'):
        """백테스팅 실행"""
        print(f"\n🔄 {symbol} 백테스팅 시작")
        print(f"   전략: 20/200 SMA 단순 추세 추종 ({timeframe})")
        print(f"   초기 자본: {self.initial_balance:,}원")

        self.reset()

        prev_row = None
        for idx, row in df.iterrows():
            # 지표 계산을 위한 최소 데이터 (200개 필요)
            if idx < 200:
                prev_row = row
                continue

            # 자본 추적
            current_equity = self.balance
            if self.position:
                current_equity += self.position['amount'] * row['close']
            self.equity_curve.append({
                'timestamp': row['timestamp'],
                'equity': current_equity
            })

            # 매수 로직
            if self.position is None and self.balance >= 5000:
                if prev_row is not None and self.check_buy_signal(row, prev_row):
                    invest = int(self.balance * 0.95)  # 95% 투자
                    fee = invest * 0.001  # 0.1% 수수료
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

            # 매도 로직
            elif self.position is not None:
                should_sell, sell_type, reason = self.check_sell_signal(row, self.position)

                if should_sell:
                    sell_price = row['close']

                    # 부분 익절 처리
                    if sell_type == "partial":
                        # 50% 청산
                        sell_amount = self.position['amount'] * 0.5
                        sell_value = sell_amount * sell_price
                        fee = sell_value * 0.001
                        final_value = sell_value - fee

                        profit = final_value - (self.position['invest'] * 0.5)
                        profit_pct = (profit / (self.position['invest'] * 0.5)) * 100
                        hold_minutes = (row['timestamp'] - self.position['buy_time']).total_seconds() / 60

                        self.balance += final_value

                        self.trades.append({
                            'symbol': symbol,
                            'buy_time': self.position['buy_time'],
                            'sell_time': row['timestamp'],
                            'buy_price': self.position['buy_price'],
                            'sell_price': sell_price,
                            'profit': profit,
                            'profit_pct': profit_pct,
                            'hold_minutes': hold_minutes,
                            'reason': reason
                        })

                        # 포지션 절반 유지
                        self.position['amount'] *= 0.5
                        self.position['invest'] *= 0.5
                        self.partial_sold = True

                    # 전량 청산
                    else:
                        sell_value = self.position['amount'] * sell_price
                        fee = sell_value * 0.001
                        final_value = sell_value - fee

                        # 부분 익절 후 나머지 청산인 경우
                        if self.partial_sold:
                            profit = final_value - self.position['invest']
                            profit_pct = (profit / self.position['invest']) * 100
                        else:
                            profit = final_value - self.position['invest']
                            profit_pct = (profit / self.position['invest']) * 100

                        hold_minutes = (row['timestamp'] - self.position['buy_time']).total_seconds() / 60

                        self.balance += final_value

                        self.trades.append({
                            'symbol': symbol,
                            'buy_time': self.position['buy_time'],
                            'sell_time': row['timestamp'],
                            'buy_price': self.position['buy_price'],
                            'sell_price': sell_price,
                            'profit': profit,
                            'profit_pct': profit_pct,
                            'hold_minutes': hold_minutes,
                            'reason': reason
                        })

                        self.position = None
                        self.partial_sold = False

            prev_row = row

        # 미체결 포지션 청산
        if self.position:
            final_row = df.iloc[-1]
            final_value = self.position['amount'] * final_row['close']
            self.balance += final_value

        return self.analyze(df, symbol)

    def analyze(self, df, symbol):
        """결과 분석"""
        total_return = self.balance - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        # CAGR (연복리 수익률)
        years = (df['timestamp'].max() - df['timestamp'].min()).days / 365.25
        if years > 0 and self.balance > 0:
            cagr = ((self.balance / self.initial_balance) ** (1 / years) - 1) * 100
        else:
            cagr = 0

        # MDD (최대 낙폭)
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0

        # Buy & Hold 비교
        buy_hold_return = ((df.iloc[-1]['close'] - df.iloc[200]['close']) / df.iloc[200]['close']) * 100

        # 거래 통계
        total_trades = len(self.trades)
        if total_trades > 0:
            winning = sum(1 for t in self.trades if t['profit'] > 0)
            win_rate = (winning / total_trades) * 100
            avg_profit_pct = sum(t['profit_pct'] for t in self.trades) / total_trades
            avg_hold_minutes = sum(t['hold_minutes'] for t in self.trades) / total_trades
            max_profit = max(t['profit_pct'] for t in self.trades)
            max_loss = min(t['profit_pct'] for t in self.trades)

            # 승리/패배 평균
            wins = [t['profit_pct'] for t in self.trades if t['profit'] > 0]
            losses = [t['profit_pct'] for t in self.trades if t['profit'] <= 0]
            avg_win = np.mean(wins) if wins else 0
            avg_loss = np.mean(losses) if losses else 0

            # 손익비
            risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        else:
            winning = 0
            win_rate = 0
            avg_profit_pct = 0
            avg_hold_minutes = 0
            max_profit = 0
            max_loss = 0
            avg_win = 0
            avg_loss = 0
            risk_reward = 0

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
            'avg_hold_minutes': avg_hold_minutes,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'risk_reward': risk_reward,
            'max_drawdown': max_drawdown,
            'buy_hold_return': buy_hold_return
        }

    def print_results(self, results):
        """결과 출력"""
        print(f"\n{'='*70}")
        print(f"📊 {results['symbol']} - 20/200 SMA 전략 결과")
        print(f"{'='*70}")
        print(f"총 거래: {results['total_trades']}회")
        if results['total_trades'] > 0:
            print(f"승률: {results['win_rate']:.1f}% ({results['winning_trades']}승)")
            print(f"평균 거래: {results['avg_profit_pct']:+.2f}%")
            print(f"평균 보유: {results['avg_hold_minutes']:.1f}분 ({results['avg_hold_minutes']/60:.1f}시간)")
            print(f"평균 승리: {results['avg_win']:+.2f}%")
            print(f"평균 손실: {results['avg_loss']:+.2f}%")
            print(f"손익비: {results['risk_reward']:.2f}")
            print(f"최대 수익: {results['max_profit']:+.2f}%")
            print(f"최대 손실: {results['max_loss']:+.2f}%")
        print()
        print(f"초기 자본: {self.initial_balance:,}원")
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


def run_multi_coin_backtest(timeframe='1m', days=60):
    """여러 알트코인 백테스팅"""

    # 테스트할 코인들
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
            backtester = SMA_20_200_Backtester(initial_balance=1_000_000)

            # 데이터 수집
            df = backtester.fetch_binance_data(coin, days=days, timeframe=timeframe)

            if df is None or len(df) < 250:
                print(f"⚠️ {coin} 데이터 부족")
                continue

            # 지표 계산
            df = backtester.calculate_indicators(df)

            # 백테스팅 실행
            results = backtester.run(df, coin, timeframe)

            # 결과 출력
            backtester.print_results(results)

            all_results.append(results)
            all_trades.extend(backtester.trades)

        except Exception as e:
            print(f"❌ {coin} 실패: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 전체 결과 요약
    if all_results:
        print(f"\n{'='*70}")
        print("📊 전체 결과 요약 - 20/200 SMA 전략")
        print(f"{'='*70}")

        # 정렬 (수익률 높은 순)
        all_results.sort(key=lambda x: x['total_return_pct'], reverse=True)

        print(f"\n{'코인':<12} {'수익률':<10} {'거래':<6} {'승률':<8} {'손익비':<8} {'vs보유'}")
        print("-" * 70)

        for r in all_results:
            vs_hold = "✅" if r['total_return_pct'] > r['buy_hold_return'] else "❌"
            print(f"{r['symbol']:<12} {r['total_return_pct']:>6.2f}%   "
                  f"{r['total_trades']:>4}회  {r['win_rate']:>5.1f}%  "
                  f"{r['risk_reward']:>5.2f}   {vs_hold}")

        # 전체 통계
        total_trades = sum(r['total_trades'] for r in all_results)
        avg_return = sum(r['total_return_pct'] for r in all_results) / len(all_results)
        avg_win_rate = sum(r['win_rate'] for r in all_results) / len(all_results)
        winning_coins = sum(1 for r in all_results if r['total_return_pct'] > 0)
        beat_hold = sum(1 for r in all_results if r['total_return_pct'] > r['buy_hold_return'])

        print(f"\n총 {len(all_results)}개 코인 테스트")
        print(f"총 거래: {total_trades}회")
        print(f"평균 수익률: {avg_return:+.2f}%")
        print(f"평균 승률: {avg_win_rate:.1f}%")
        print(f"수익 코인: {winning_coins}/{len(all_results)}")
        print(f"Buy & Hold 이긴 코인: {beat_hold}/{len(all_results)}")

        # CSV 저장
        if all_trades:
            trades_df = pd.DataFrame(all_trades)
            trades_df.to_csv('sma_20_200_results.csv', index=False, encoding='utf-8-sig')
            print(f"\n💾 저장: sma_20_200_results.csv")


if __name__ == "__main__":
    import sys

    # 타임프레임 설정 (기본값: 1m)
    timeframe = sys.argv[1] if len(sys.argv) > 1 else '1m'
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    print("=" * 70)
    print(f"📊 20/200 SMA 전문가 추세 추종 전략 백테스팅 ({timeframe})")
    print("   - 원칙: 추세 구간에서만 거래 (횡보장 완전 배제)")
    print("   - 손절: -0.7% (짧고 빠르게)")
    print("   - 손익비: 1:2+ (작게 지고, 크게 먹는다)")
    print("   - 부분 익절: +1.5%에서 50%, 나머지는 추적")
    print(f"   - 기간: 최근 {days}일")
    print("=" * 70)

    run_multi_coin_backtest(timeframe, days)
