#!/usr/bin/env python3
"""
바이낸스 20/200 SMA 자동매매 봇

핵심 흐름:
1. 코인 스캐너로 최적 코인 찾기
2. 20/200 SMA 전략으로 실시간 거래
3. 익절/손절 후 다시 스캔
4. 텔레그램으로 모든 거래 알림

전략:
- 20MA 명확한 상승 (기울기 0.2%+)
- 가격 > 200MA
- 20MA 근처 ±3% 이내
- 손절: -0.7%
- 부분 익절: +1.5% (50%), +3% (나머지)
"""
import os
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import requests
from coin_scanner_20_200 import CoinScanner_20_200


class TelegramNotifier:
    """텔레그램 알림"""

    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = self.token and self.chat_id

        if not self.enabled:
            print("⚠️ 텔레그램 설정 없음 - 알림 비활성화")

    def send(self, message):
        """메시지 전송"""
        if not self.enabled:
            print(f"[TELEGRAM] {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            if not response.ok:
                print(f"텔레그램 전송 실패: {response.text}")
        except Exception as e:
            print(f"텔레그램 오류: {e}")


class Binance20_200Bot:
    """바이낸스 20/200 SMA 자동매매 봇"""

    def __init__(self, api_key=None, api_secret=None, telegram_token=None, telegram_chat_id=None,
                 dry_run=True, initial_balance_usdt=100):
        """
        Args:
            api_key: 바이낸스 API 키
            api_secret: 바이낸스 API 시크릿
            telegram_token: 텔레그램 봇 토큰
            telegram_chat_id: 텔레그램 채팅 ID
            dry_run: 시뮬레이션 모드 (True=가상거래, False=실거래)
            initial_balance_usdt: 초기 자본 (USDT)
        """
        # 바이낸스 API
        self.exchange = ccxt.binance({
            'apiKey': api_key or os.getenv('BINANCE_API_KEY'),
            'secret': api_secret or os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}  # 선물 거래
        })

        # 텔레그램
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)

        # 코인 스캐너
        self.scanner = CoinScanner_20_200(
            min_volume_usdt=10_000_000,  # 1000만 USDT 이상
            timeframe='1m'
        )

        # 거래 모드
        self.dry_run = dry_run

        # 자본 관리 (시뮬레이션)
        self.balance_usdt = initial_balance_usdt
        self.initial_balance = initial_balance_usdt

        # 현재 포지션
        self.position = None  # {'symbol', 'entry_price', 'amount', 'entry_time', 'partial_sold'}

        # 거래 기록
        self.trades = []

        # 전략 파라미터
        self.stop_loss_pct = -0.7
        self.partial_profit_pct = 1.5
        self.final_profit_pct = 3.0

        # 상태
        self.running = False

        print(f"\n{'='*70}")
        print(f"🤖 바이낸스 20/200 SMA 자동매매 봇 초기화")
        print(f"{'='*70}")
        print(f"모드: {'🔴 실거래' if not dry_run else '🟢 시뮬레이션'}")
        print(f"초기 자본: ${self.balance_usdt:.2f} USDT")
        print(f"텔레그램: {'✅ 활성화' if self.telegram.enabled else '❌ 비활성화'}")
        print(f"{'='*70}\n")

    def get_current_price(self, symbol):
        """현재 가격 조회"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            print(f"❌ 가격 조회 실패 ({symbol}): {e}")
            return None

    def get_candles(self, symbol, limit=250):
        """캔들 데이터 조회"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"❌ 캔들 조회 실패 ({symbol}): {e}")
            return None

    def calculate_indicators(self, df):
        """지표 계산"""
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['sma200'] = df['close'].rolling(window=200).mean()

        df['sma20_prev'] = df['sma20'].shift(1)
        df['sma20_slope'] = (df['sma20'] - df['sma20_prev']) / df['sma20_prev']

        df['distance_to_20ma'] = (df['close'] - df['sma20']) / df['sma20'] * 100
        df['distance_to_200ma'] = (df['close'] - df['sma200']) / df['sma200'] * 100

        return df

    def check_buy_signal(self, df):
        """매수 신호 체크"""
        if len(df) < 200:
            return False

        latest = df.iloc[-1]

        if pd.isna(latest['sma20']) or pd.isna(latest['sma200']):
            return False

        # 1. 20MA 상승 (0.2%+)
        slope = latest['sma20_slope']
        if slope <= 0.002:
            return False

        # 2. 가격 > 200MA
        if latest['close'] <= latest['sma200']:
            return False

        # 3. 20MA 근처 (±3%)
        distance = abs(latest['distance_to_20ma'])
        if distance > 3.0:
            return False

        return True

    def check_sell_signal(self, current_price):
        """매도 신호 체크"""
        if not self.position:
            return False, None

        entry_price = self.position['entry_price']
        profit_pct = ((current_price - entry_price) / entry_price) * 100

        # 1. 손절 -0.7%
        if profit_pct <= self.stop_loss_pct:
            return True, f"손절 ({profit_pct:+.2f}%)"

        # 2. 부분 익절 +1.5% (50%)
        if profit_pct >= self.partial_profit_pct and not self.position.get('partial_sold', False):
            return True, f"부분익절 ({profit_pct:+.2f}%)"

        # 3. 최종 익절 +3% (나머지)
        if self.position.get('partial_sold', False) and profit_pct >= self.final_profit_pct:
            return True, f"최종익절 ({profit_pct:+.2f}%)"

        return False, None

    def execute_buy(self, symbol, price):
        """매수 실행"""
        if self.position:
            print("⚠️ 이미 포지션 보유 중")
            return False

        # 투자금액 (95%)
        invest_usdt = self.balance_usdt * 0.95
        amount = invest_usdt / price
        fee = invest_usdt * 0.001  # 0.1% 수수료

        if self.dry_run:
            # 시뮬레이션
            self.position = {
                'symbol': symbol,
                'entry_price': price,
                'amount': amount,
                'invest_usdt': invest_usdt,
                'entry_time': datetime.now(),
                'partial_sold': False
            }
            self.balance_usdt -= invest_usdt

            msg = f"""
🟢 <b>매수 체결</b> (시뮬레이션)
━━━━━━━━━━━━━━━━━
코인: {symbol}
가격: ${price:.6f}
수량: {amount:.4f}
투자: ${invest_usdt:.2f} USDT
수수료: ${fee:.2f}
잔고: ${self.balance_usdt:.2f}
"""
            print(msg)
            self.telegram.send(msg)
            return True

        else:
            # 실거래
            try:
                order = self.exchange.create_market_buy_order(symbol, amount)

                self.position = {
                    'symbol': symbol,
                    'entry_price': order['average'],
                    'amount': order['filled'],
                    'invest_usdt': invest_usdt,
                    'entry_time': datetime.now(),
                    'partial_sold': False,
                    'order_id': order['id']
                }

                msg = f"""
🟢 <b>매수 체결</b>
━━━━━━━━━━━━━━━━━
코인: {symbol}
가격: ${order['average']:.6f}
수량: {order['filled']:.4f}
주문ID: {order['id']}
"""
                print(msg)
                self.telegram.send(msg)
                return True

            except Exception as e:
                print(f"❌ 매수 실패: {e}")
                self.telegram.send(f"❌ 매수 실패: {symbol}\n{e}")
                return False

    def execute_sell(self, price, reason):
        """매도 실행"""
        if not self.position:
            return False

        symbol = self.position['symbol']
        entry_price = self.position['entry_price']

        # 부분 익절 여부
        is_partial = "부분익절" in reason
        sell_ratio = 0.5 if is_partial else 1.0

        sell_amount = self.position['amount'] * sell_ratio
        sell_value = sell_amount * price
        fee = sell_value * 0.001
        final_value = sell_value - fee

        profit = final_value - (self.position['invest_usdt'] * sell_ratio)
        profit_pct = (profit / (self.position['invest_usdt'] * sell_ratio)) * 100

        hold_time = datetime.now() - self.position['entry_time']
        hold_minutes = hold_time.total_seconds() / 60

        if self.dry_run:
            # 시뮬레이션
            self.balance_usdt += final_value

            # 거래 기록
            trade = {
                'symbol': symbol,
                'entry_price': entry_price,
                'exit_price': price,
                'profit': profit,
                'profit_pct': profit_pct,
                'hold_minutes': hold_minutes,
                'reason': reason,
                'timestamp': datetime.now()
            }
            self.trades.append(trade)

            msg = f"""
🔴 <b>매도 체결</b> (시뮬레이션)
━━━━━━━━━━━━━━━━━
코인: {symbol}
사유: {reason}
진입: ${entry_price:.6f}
청산: ${price:.6f}
수량: {sell_amount:.4f} ({sell_ratio*100:.0f}%)
수익: ${profit:+.2f} ({profit_pct:+.2f}%)
보유: {hold_minutes:.1f}분
잔고: ${self.balance_usdt:.2f}
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
누적 수익: ${self.balance_usdt - self.initial_balance:+.2f} ({(self.balance_usdt/self.initial_balance - 1)*100:+.2f}%)
"""
            print(msg)
            self.telegram.send(msg)

            # 포지션 업데이트
            if is_partial:
                self.position['amount'] *= 0.5
                self.position['invest_usdt'] *= 0.5
                self.position['partial_sold'] = True
            else:
                self.position = None

            return True

        else:
            # 실거래
            try:
                order = self.exchange.create_market_sell_order(symbol, sell_amount)

                trade = {
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'exit_price': order['average'],
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'hold_minutes': hold_minutes,
                    'reason': reason,
                    'timestamp': datetime.now(),
                    'order_id': order['id']
                }
                self.trades.append(trade)

                msg = f"""
🔴 <b>매도 체결</b>
━━━━━━━━━━━━━━━━━
코인: {symbol}
사유: {reason}
진입: ${entry_price:.6f}
청산: ${order['average']:.6f}
수량: {order['filled']:.4f}
수익: ${profit:+.2f} ({profit_pct:+.2f}%)
보유: {hold_minutes:.1f}분
주문ID: {order['id']}
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
"""
                print(msg)
                self.telegram.send(msg)

                # 포지션 업데이트
                if is_partial:
                    self.position['amount'] *= 0.5
                    self.position['invest_usdt'] *= 0.5
                    self.position['partial_sold'] = True
                else:
                    self.position = None

                return True

            except Exception as e:
                print(f"❌ 매도 실패: {e}")
                self.telegram.send(f"❌ 매도 실패: {symbol}\n{e}")
                return False

    def find_best_coin(self):
        """최적 코인 찾기"""
        print(f"\n{'='*70}")
        print(f"🔍 최적 코인 스캔 중...")
        print(f"{'='*70}")

        qualified_coins = self.scanner.scan_market(max_coins=50)

        if not qualified_coins:
            print("❌ 전략 조건 충족 코인 없음")
            return None

        # 최고 점수 코인
        best = qualified_coins[0]

        print(f"\n🏆 최적 코인 발견: {best['symbol']}")
        print(f"   점수: {best['score']:.1f}/100")
        print(f"   20MA 기울기: {best['details']['slope_pct']:.3f}%")
        print(f"   20MA 거리: {best['details']['distance_20ma']:+.2f}%")
        print(f"   거래대금: ${best['volume_usdt']/1e6:.1f}M")

        msg = f"""
🎯 <b>최적 코인 발견</b>
━━━━━━━━━━━━━━━━━
코인: {best['symbol']}
점수: {best['score']:.1f}/100
20MA 기울기: {best['details']['slope_pct']:.3f}%
20MA 거리: {best['details']['distance_20ma']:+.2f}%
거래대금: ${best['volume_usdt']/1e6:.1f}M
"""
        self.telegram.send(msg)

        return best['symbol']

    def run(self):
        """봇 실행"""
        self.running = True

        msg = f"""
🚀 <b>봇 시작</b>
━━━━━━━━━━━━━━━━━
모드: {'실거래' if not self.dry_run else '시뮬레이션'}
초기 자본: ${self.initial_balance:.2f} USDT
전략: 20/200 SMA
손절: {self.stop_loss_pct}%
부분익절: {self.partial_profit_pct}% (50%)
최종익절: {self.final_profit_pct}%
"""
        print(msg)
        self.telegram.send(msg)

        try:
            while self.running:
                # 포지션 없으면 코인 스캔
                if not self.position:
                    symbol = self.find_best_coin()

                    if not symbol:
                        print("⏳ 60초 후 재스캔...")
                        time.sleep(60)
                        continue

                    # 매수 신호 재확인
                    df = self.get_candles(symbol)
                    if df is None:
                        continue

                    df = self.calculate_indicators(df)

                    if self.check_buy_signal(df):
                        current_price = self.get_current_price(symbol)
                        if current_price:
                            self.execute_buy(symbol, current_price)

                    time.sleep(5)

                # 포지션 있으면 모니터링
                else:
                    symbol = self.position['symbol']
                    current_price = self.get_current_price(symbol)

                    if not current_price:
                        time.sleep(5)
                        continue

                    # 매도 신호 체크
                    should_sell, reason = self.check_sell_signal(current_price)

                    if should_sell:
                        self.execute_sell(current_price, reason)

                        # 포지션 완전히 청산되면 잠시 대기 후 재스캔
                        if not self.position:
                            print("\n✅ 포지션 청산 완료. 10초 후 재스캔...")
                            time.sleep(10)

                    else:
                        # 현재 수익률 표시
                        profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                        print(f"📊 {symbol} | 가격: ${current_price:.6f} | 수익: {profit_pct:+.2f}%", end='\r')
                        time.sleep(1)

        except KeyboardInterrupt:
            print("\n\n봇 종료 중...")
            self.stop()

        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            self.telegram.send(f"❌ 봇 오류\n{e}")
            self.stop()

    def stop(self):
        """봇 종료"""
        self.running = False

        # 포지션 있으면 강제 청산
        if self.position:
            print("\n⚠️ 포지션 강제 청산...")
            symbol = self.position['symbol']
            current_price = self.get_current_price(symbol)
            if current_price:
                self.execute_sell(current_price, "봇종료")

        # 최종 결과
        total_return = self.balance_usdt - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        win_trades = [t for t in self.trades if t['profit'] > 0]
        win_rate = (len(win_trades) / len(self.trades) * 100) if self.trades else 0

        msg = f"""
🛑 <b>봇 종료</b>
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
승률: {win_rate:.1f}%
초기 자본: ${self.initial_balance:.2f}
최종 자본: ${self.balance_usdt:.2f}
총 수익: ${total_return:+.2f} ({total_return_pct:+.2f}%)
"""
        print(msg)
        self.telegram.send(msg)


def main():
    """메인 함수"""
    import sys

    # 환경변수 체크
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

    # 모드 설정
    dry_run = True  # 기본값: 시뮬레이션
    if len(sys.argv) > 1 and sys.argv[1] == 'live':
        if not api_key or not api_secret:
            print("❌ BINANCE_API_KEY와 BINANCE_API_SECRET 환경변수 필요")
            sys.exit(1)
        dry_run = False
        print("⚠️ 실거래 모드로 시작합니다!")
        time.sleep(3)

    # 봇 생성 및 실행
    bot = Binance20_200Bot(
        api_key=api_key,
        api_secret=api_secret,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        dry_run=dry_run,
        initial_balance_usdt=100
    )

    bot.run()


if __name__ == "__main__":
    main()
