#!/usr/bin/env python3
"""
업비트 4시간 레인지 재진입 자동매매 봇

전략:
- 09:00~13:00 KST 4시간 캔들로 레인지 설정
- 레인지 이탈 후 재진입 시 역방향 진입 (Long/Short)
- 손익비 최소 1:2 유지
- 연속 2손절 또는 하루 3회 거래 제한

텔레그램 명령어:
- /status: 현재 상태 확인
- /stop: 봇 중지
- /help: 도움말
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import requests
from upbit_api import UpbitAPI


class TelegramNotifier:
    """텔레그램 알림"""

    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = self.token and self.chat_id
        self.update_id_file = 'telegram_last_update_id.txt'
        self.last_update_id = self._load_last_update_id()
        self.stop_requested = False  # 정지 요청 플래그

        if not self.enabled:
            print("⚠️ 텔레그램 설정 없음")

    def _load_last_update_id(self):
        """마지막 업데이트 ID 파일에서 로드"""
        try:
            if os.path.exists(self.update_id_file):
                with open(self.update_id_file, 'r') as f:
                    return int(f.read().strip())
        except:
            pass
        return 0

    def _save_last_update_id(self):
        """마지막 업데이트 ID 파일에 저장"""
        try:
            with open(self.update_id_file, 'w') as f:
                f.write(str(self.last_update_id))
        except:
            pass

    def send(self, message):
        """메시지 전송"""
        if not self.enabled:
            print(f"[TELEGRAM] {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, json=data, timeout=5)
            return response.ok
        except requests.exceptions.RequestException:
            pass

    def check_commands(self):
        """명령어 확인 및 처리"""
        if not self.enabled:
            return None

        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 1}
            response = requests.get(url, params=params, timeout=5)

            if response.ok:
                data = response.json()
                if data.get('result'):
                    for update in data['result']:
                        self.last_update_id = update['update_id']
                        self._save_last_update_id()  # 즉시 파일에 저장
                        if 'message' in update and 'text' in update['message']:
                            command = update['message']['text'].strip().lower()
                            if command == '/stop':
                                self.stop_requested = True
                                return 'stop'
                            elif command in ['/status', '/help']:
                                return command
        except requests.exceptions.RequestException:
            pass

        return None


class Upbit4HRangeBot:
    """업비트 4시간 레인지 재진입 봇"""

    def __init__(self, access_key, secret_key, market='KRW-BTC',
                 telegram_token=None, telegram_chat_id=None,
                 dry_run=True, initial_balance_krw=None):
        """
        초기화

        Args:
            market: 거래 마켓 (기본: KRW-BTC)
            dry_run: 시뮬레이션 모드 (True=가상거래, False=실거래)
            initial_balance_krw: 초기 자본
        """
        self.upbit = UpbitAPI(access_key, secret_key)
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        self.market = market
        self.dry_run = dry_run
        self.running = True

        # 자산 관리
        if not dry_run:
            # 실거래: 현재 보유 자산을 초기 자본으로 설정
            real_balance = self.get_account_balance()
            self.initial_balance = real_balance
            self.balance_krw = real_balance
            print(f"💰 실거래 모드: 현재 보유 자산 {real_balance:,.0f}원을 초기 자본으로 설정")
        else:
            # 시뮬레이션: 100만원으로 시작
            self.balance_krw = 1000000
            self.initial_balance = 1000000

        # 전략 상태
        self.position = None
        self.trades = []

        # 일일 제한
        self.current_date = None
        self.daily_losses = 0
        self.daily_trades = 0

        # 4시간 레인지
        self.range_high = None
        self.range_low = None
        self.has_broken_out = False
        self.breakout_direction = None  # 'up' or 'down'
        self.breakout_high = None
        self.breakout_low = None

        print(f"\n{'='*60}")
        print(f"업비트 4시간 레인지 재진입 봇 시작")
        print(f"{'='*60}")
        print(f"마켓: {market}")
        print(f"모드: {'🔴 실거래' if not dry_run else '🟢 시뮬레이션'}")
        print(f"초기 자본: {self.initial_balance:,.0f}원")
        print(f"{'='*60}\n")

        self.telegram.send(f"🤖 4시간 레인지 봇 시작\n마켓: {market}\n초기 자본: {self.initial_balance:,.0f}원")

        # 실거래 모드일 때 기존 보유 코인 확인
        if not dry_run:
            self.check_existing_position()

    def get_account_balance(self):
        """계좌 잔고 조회"""
        try:
            accounts = self.upbit.get_accounts()
            total_balance = 0

            for account in accounts:
                if account['currency'] == 'KRW':
                    total_balance += float(account['balance'])
                else:
                    # 보유 코인 평가금액
                    ticker = f"KRW-{account['currency']}"
                    try:
                        current_price = self.get_current_price(ticker)
                        if current_price:
                            coin_value = float(account['balance']) * current_price
                            total_balance += coin_value
                    except:
                        pass

            return total_balance
        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return 0

    def check_existing_position(self):
        """기존 보유 코인 확인"""
        try:
            accounts = self.upbit.get_accounts()
            currency = self.market.split('-')[1]

            for account in accounts:
                if account['currency'] == currency:
                    balance = float(account['balance'])
                    if balance > 0:
                        avg_buy_price = float(account['avg_buy_price'])
                        current_price = self.get_current_price(self.market)

                        print(f"\n⚠️ 기존 포지션 발견:")
                        print(f"   코인: {currency}")
                        print(f"   수량: {balance}")
                        print(f"   평균 매수가: {avg_buy_price:,.0f}원")
                        print(f"   현재가: {current_price:,.0f}원")

                        profit_pct = ((current_price - avg_buy_price) / avg_buy_price) * 100
                        print(f"   수익률: {profit_pct:.2f}%\n")

                        # 포지션 정보 저장 (손익 계산용)
                        self.position = {
                            'direction': 'long',  # 업비트는 롱만 가능
                            'entry_price': avg_buy_price,
                            'entry_time': datetime.now(),
                            'quantity': balance,
                            'stop_loss': None,  # 기존 포지션은 손절가 없음
                            'take_profit': None
                        }

                        self.telegram.send(
                            f"⚠️ 기존 포지션 발견\n"
                            f"코인: {currency}\n"
                            f"평균 매수가: {avg_buy_price:,.0f}원\n"
                            f"현재 수익률: {profit_pct:.2f}%"
                        )
        except Exception as e:
            print(f"❌ 기존 포지션 확인 실패: {e}")

    def get_current_price(self, market):
        """현재가 조회"""
        try:
            ticker = self.upbit.get_ticker(market)
            if ticker:
                return float(ticker['trade_price'])
        except:
            pass
        return None

    def fetch_candles(self, timeframe_minutes, count=200):
        """캔들 데이터 수집"""
        try:
            url = f"https://api.upbit.com/v1/candles/minutes/{timeframe_minutes}"
            params = {'market': self.market, 'count': count}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                candles = response.json()
                # 최신 데이터가 먼저 오므로 역순 정렬
                candles.reverse()

                df = pd.DataFrame({
                    'timestamp': pd.to_datetime([c['candle_date_time_kst'] for c in candles]),
                    'open': [c['opening_price'] for c in candles],
                    'high': [c['high_price'] for c in candles],
                    'low': [c['low_price'] for c in candles],
                    'close': [c['trade_price'] for c in candles],
                    'volume': [c['candle_acc_trade_volume'] for c in candles]
                })

                return df
        except Exception as e:
            print(f"❌ 캔들 데이터 수집 실패: {e}")

        return None

    def update_daily_range(self):
        """09:00~13:00 KST 4시간 레인지 업데이트"""
        now = datetime.now()
        current_date = now.date()

        # 날짜 변경 시 초기화
        if self.current_date != current_date:
            self.current_date = current_date
            self.daily_losses = 0
            self.daily_trades = 0
            self.range_high = None
            self.range_low = None
            self.has_broken_out = False
            self.breakout_direction = None
            self.breakout_high = None
            self.breakout_low = None

        # 13:00 이후에만 레인지 설정
        if now.hour < 13:
            return

        # 레인지가 이미 설정되었으면 리턴
        if self.range_high is not None and self.range_low is not None:
            return

        # 240분봉(4시간) 데이터 가져오기
        df_4h = self.fetch_candles(timeframe_minutes=240, count=10)
        if df_4h is None or len(df_4h) == 0:
            return

        # 오늘 09:00 시작하는 캔들 찾기
        target_candles = df_4h[
            (df_4h['timestamp'].dt.date == current_date) &
            (df_4h['timestamp'].dt.hour == 9)
        ]

        if len(target_candles) > 0:
            candle = target_candles.iloc[0]
            self.range_high = candle['high']
            self.range_low = candle['low']

            print(f"\n📊 4시간 레인지 설정 (09:00~13:00)")
            print(f"   고점: {self.range_high:,.0f}원")
            print(f"   저점: {self.range_low:,.0f}원")
            print(f"   범위: {((self.range_high - self.range_low) / self.range_low * 100):.2f}%\n")

            self.telegram.send(
                f"📊 4시간 레인지 설정\n"
                f"고점: {self.range_high:,.0f}원\n"
                f"저점: {self.range_low:,.0f}원"
            )

    def is_trading_hours(self):
        """거래 가능 시간인지 확인 (13:00 ~ 22:00 KST)"""
        hour = datetime.now().hour
        return 13 <= hour < 22

    def check_entry_signal(self, current_price):
        """진입 시그널 확인"""
        if self.range_high is None or self.range_low is None:
            return None

        # 이탈 확인
        if not self.has_broken_out:
            # 상단 이탈
            if current_price > self.range_high:
                self.has_broken_out = True
                self.breakout_direction = 'up'
                self.breakout_high = current_price
                print(f"🔼 상단 이탈: {current_price:,.0f}원 (레인지 고점: {self.range_high:,.0f}원)")
            # 하단 이탈
            elif current_price < self.range_low:
                self.has_broken_out = True
                self.breakout_direction = 'down'
                self.breakout_low = current_price
                print(f"🔽 하단 이탈: {current_price:,.0f}원 (레인지 저점: {self.range_low:,.0f}원)")
        else:
            # 이탈 중 극값 갱신
            if self.breakout_direction == 'up':
                self.breakout_high = max(self.breakout_high, current_price)
            else:
                self.breakout_low = min(self.breakout_low, current_price)

        # 재진입 확인
        if self.has_broken_out:
            # 상단 이탈 후 재진입 → Short (업비트는 Short 불가능하므로 매수 안 함)
            if self.breakout_direction == 'up' and self.range_low <= current_price <= self.range_high:
                print(f"⚠️ Short 시그널 (업비트는 Short 불가) - 패스")
                return None

            # 하단 이탈 후 재진입 → Long
            elif self.breakout_direction == 'down' and self.range_low <= current_price <= self.range_high:
                # 과도한 변동성 필터
                range_size = self.range_high - self.range_low
                breakout_body = abs(self.breakout_low - self.range_low)

                if breakout_body > range_size * 0.5:
                    print(f"⚠️ 과도한 변동성 - 진입 스킵")
                    return None

                print(f"✅ Long 재진입 시그널: {current_price:,.0f}원")
                return 'long'

        return None

    def calculate_position_params(self, direction, entry_price):
        """손절/익절가 계산"""
        if direction == 'long':
            stop_loss = self.breakout_low
        else:
            stop_loss = self.breakout_high

        # 손절폭 확인
        stop_loss_pct = abs((stop_loss - entry_price) / entry_price) * 100

        # 손절폭이 0.6% 이상이면 0.5%로 제한
        if stop_loss_pct >= 0.6:
            stop_loss = entry_price * 0.995  # -0.5%

        # 익절가 (2R)
        risk = abs(entry_price - stop_loss)
        take_profit = entry_price + (risk * 2)

        return stop_loss, take_profit

    def execute_buy(self, current_price):
        """매수 실행"""
        try:
            # 거래 가능한 잔고
            available_balance = self.balance_krw if self.dry_run else self.get_krw_balance()

            if available_balance < 5000:
                print("❌ 잔고 부족 (최소 5,000원 필요)")
                return False

            # 전액 매수
            buy_amount = available_balance * 0.995  # 수수료 고려

            if self.dry_run:
                # 시뮬레이션
                quantity = buy_amount / current_price
                self.balance_krw = 0

                print(f"\n💰 [시뮬] 매수 체결")
                print(f"   가격: {current_price:,.0f}원")
                print(f"   수량: {quantity:.8f}")
                print(f"   금액: {buy_amount:,.0f}원")
            else:
                # 실거래
                currency = self.market.split('-')[1]
                result = self.upbit.buy_market_order(self.market, buy_amount)

                if result and 'uuid' in result:
                    time.sleep(0.5)
                    order_info = self.upbit.get_order(result['uuid'])

                    if order_info and order_info['state'] == 'done':
                        quantity = float(order_info['executed_volume'])
                        avg_price = float(order_info['trades'][0]['price']) if order_info.get('trades') else current_price

                        print(f"\n💰 매수 체결")
                        print(f"   가격: {avg_price:,.0f}원")
                        print(f"   수량: {quantity:.8f}")
                        print(f"   금액: {buy_amount:,.0f}원")

                        current_price = avg_price
                    else:
                        print("❌ 매수 주문 체결 확인 실패")
                        return False
                else:
                    print("❌ 매수 주문 실패")
                    return False

                quantity = buy_amount / current_price

            # 손절/익절가 계산
            stop_loss, take_profit = self.calculate_position_params('long', current_price)

            # 포지션 저장
            self.position = {
                'direction': 'long',
                'entry_price': current_price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }

            self.daily_trades += 1

            msg = (
                f"✅ 매수 완료\n"
                f"가격: {current_price:,.0f}원\n"
                f"수량: {quantity:.8f}\n"
                f"손절: {stop_loss:,.0f}원\n"
                f"익절: {take_profit:,.0f}원"
            )
            self.telegram.send(msg)

            return True

        except Exception as e:
            print(f"❌ 매수 실행 실패: {e}")
            return False

    def execute_sell(self, current_price, reason):
        """매도 실행"""
        if self.position is None:
            return False

        try:
            quantity = self.position['quantity']

            if self.dry_run:
                # 시뮬레이션
                sell_amount = quantity * current_price
                self.balance_krw += sell_amount

                print(f"\n💵 [시뮬] 매도 체결 ({reason})")
                print(f"   가격: {current_price:,.0f}원")
                print(f"   수량: {quantity:.8f}")
                print(f"   금액: {sell_amount:,.0f}원")
            else:
                # 실거래
                result = self.upbit.sell_market_order(self.market, quantity)

                if result and 'uuid' in result:
                    time.sleep(0.5)
                    order_info = self.upbit.get_order(result['uuid'])

                    if order_info and order_info['state'] == 'done':
                        avg_price = float(order_info['trades'][0]['price']) if order_info.get('trades') else current_price

                        print(f"\n💵 매도 체결 ({reason})")
                        print(f"   가격: {avg_price:,.0f}원")
                        print(f"   수량: {quantity:.8f}")

                        current_price = avg_price
                    else:
                        print("❌ 매도 주문 체결 확인 실패")
                        return False
                else:
                    print("❌ 매도 주문 실패")
                    return False

            # 손익 계산
            entry_price = self.position['entry_price']
            profit = (current_price - entry_price) * quantity
            profit_pct = ((current_price - entry_price) / entry_price) * 100

            # 거래 기록
            self.trades.append({
                'entry_time': self.position['entry_time'],
                'exit_time': datetime.now(),
                'entry_price': entry_price,
                'exit_price': current_price,
                'profit': profit,
                'profit_pct': profit_pct,
                'reason': reason
            })

            # 손절 카운트
            if reason == '손절':
                self.daily_losses += 1

            # 포지션 초기화
            self.position = None

            msg = (
                f"✅ 매도 완료 ({reason})\n"
                f"진입: {entry_price:,.0f}원\n"
                f"청산: {current_price:,.0f}원\n"
                f"수익: {profit:,.0f}원 ({profit_pct:+.2f}%)\n"
                f"누적 거래: {len(self.trades)}회"
            )
            self.telegram.send(msg)

            return True

        except Exception as e:
            print(f"❌ 매도 실행 실패: {e}")
            return False

    def check_exit_signal(self, current_price):
        """청산 시그널 확인"""
        if self.position is None:
            return None

        direction = self.position['direction']
        stop_loss = self.position['stop_loss']
        take_profit = self.position['take_profit']

        if direction == 'long':
            if current_price <= stop_loss:
                return '손절'
            elif current_price >= take_profit:
                return '익절'

        return None

    def get_krw_balance(self):
        """KRW 잔고 조회"""
        try:
            accounts = self.upbit.get_accounts()
            for account in accounts:
                if account['currency'] == 'KRW':
                    return float(account['balance'])
        except:
            pass
        return 0

    def print_status(self):
        """현재 상태 출력"""
        current_balance = self.get_account_balance() if not self.dry_run else self.balance_krw
        profit = current_balance - self.initial_balance
        profit_pct = (profit / self.initial_balance) * 100

        status = f"\n{'='*60}\n"
        status += f"📊 현재 상태 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"
        status += f"{'='*60}\n"
        status += f"마켓: {self.market}\n"
        status += f"초기 자본: {self.initial_balance:,.0f}원\n"
        status += f"현재 자산: {current_balance:,.0f}원\n"
        status += f"수익: {profit:,.0f}원 ({profit_pct:+.2f}%)\n"
        status += f"총 거래: {len(self.trades)}회\n"
        status += f"오늘 거래: {self.daily_trades}/3회\n"
        status += f"오늘 손절: {self.daily_losses}/2회\n"

        if self.range_high and self.range_low:
            status += f"\n4시간 레인지:\n"
            status += f"  고점: {self.range_high:,.0f}원\n"
            status += f"  저점: {self.range_low:,.0f}원\n"

        if self.position:
            current_price = self.get_current_price(self.market)
            if current_price:
                profit = (current_price - self.position['entry_price']) * self.position['quantity']
                profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100

                status += f"\n포지션:\n"
                status += f"  방향: {self.position['direction'].upper()}\n"
                status += f"  진입가: {self.position['entry_price']:,.0f}원\n"
                status += f"  현재가: {current_price:,.0f}원\n"
                status += f"  수익: {profit:,.0f}원 ({profit_pct:+.2f}%)\n"
                status += f"  손절: {self.position['stop_loss']:,.0f}원\n"
                status += f"  익절: {self.position['take_profit']:,.0f}원\n"
        else:
            status += f"\n포지션: 없음\n"

        status += f"{'='*60}\n"
        print(status)
        self.telegram.send(status)

    def run(self):
        """봇 실행"""
        print("\n🤖 봇 시작...\n")

        # 봇 시작 시 stop_requested 플래그 초기화
        self.telegram.stop_requested = False

        try:
            while self.running and not self.telegram.stop_requested:
                # 텔레그램 명령어 확인
                command = self.telegram.check_commands()
                if command == 'stop':
                    print("\n🛑 정지 명령 수신")
                    self.telegram.send("🛑 봇을 정지합니다.")
                    break
                elif command == '/status':
                    self.print_status()
                elif command == '/help':
                    help_msg = (
                        "📖 명령어 도움말\n\n"
                        "/status - 현재 상태 확인\n"
                        "/stop - 봇 중지\n"
                        "/help - 도움말"
                    )
                    self.telegram.send(help_msg)

                # 4시간 레인지 업데이트
                self.update_daily_range()

                # 거래 가능 시간 확인
                if not self.is_trading_hours():
                    time.sleep(60)
                    continue

                # 연속 2손절 또는 하루 3회 거래 제한
                if self.daily_losses >= 2 or self.daily_trades >= 3:
                    time.sleep(60)
                    continue

                # 현재가 조회
                current_price = self.get_current_price(self.market)
                if current_price is None:
                    time.sleep(10)
                    continue

                # 포지션 없을 때 진입 확인
                if self.position is None:
                    entry_signal = self.check_entry_signal(current_price)

                    if entry_signal == 'long':
                        self.execute_buy(current_price)

                # 포지션 있을 때 청산 확인
                else:
                    exit_signal = self.check_exit_signal(current_price)

                    if exit_signal:
                        self.execute_sell(current_price, exit_signal)

                # 30초 대기
                time.sleep(30)

        except KeyboardInterrupt:
            print("\n\n🛑 사용자에 의해 중지됨")
            self.telegram.send("🛑 봇이 중지되었습니다.")
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            self.telegram.send(f"❌ 오류 발생: {e}")
        finally:
            self.print_status()
            print("\n✅ 봇 종료")


if __name__ == "__main__":
    # 환경 변수에서 API 키 읽기
    ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY')
    SECRET_KEY = os.getenv('UPBIT_SECRET_KEY')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    if not ACCESS_KEY or not SECRET_KEY:
        print("❌ 업비트 API 키가 설정되지 않았습니다.")
        print("export UPBIT_ACCESS_KEY='your_access_key'")
        print("export UPBIT_SECRET_KEY='your_secret_key'")
        sys.exit(1)

    # 봇 실행
    bot = Upbit4HRangeBot(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        market='KRW-SOL',  # 솔라나로 변경 (백테스트 결과 +116.76% vs BTC +3.24%)
        telegram_token=TELEGRAM_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        dry_run=False  # 실거래 모드
    )

    bot.run()
