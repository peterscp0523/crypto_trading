#!/usr/bin/env python3
"""
업비트 20/200 SMA 자동매매 봇

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
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import requests
from upbit_api import UpbitAPI
from upbit_coin_scanner_20_200 import UpbitCoinScanner_20_200


class TelegramNotifier:
    """텔레그램 알림 및 명령어 처리"""

    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = self.token and self.chat_id
        self.last_update_id = None

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

    def get_updates(self):
        """새 메시지 가져오기"""
        if not self.enabled:
            return []

        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {
                "timeout": 1,
                "offset": self.last_update_id + 1 if self.last_update_id else None
            }
            response = requests.get(url, params=params, timeout=5)
            if response.ok:
                data = response.json()
                if data.get('result'):
                    messages = []
                    for update in data['result']:
                        self.last_update_id = update['update_id']
                        if 'message' in update and 'text' in update['message']:
                            # 본인 채팅방에서 온 메시지만 처리
                            if str(update['message']['chat']['id']) == str(self.chat_id):
                                messages.append(update['message']['text'])
                    return messages
        except requests.exceptions.RequestException as e:
            # 네트워크 에러는 조용히 무시 (다음 루프에서 재시도)
            pass
        except Exception as e:
            # 기타 에러만 로그
            print(f"텔레그램 업데이트 체크 실패: {e}")
        return []


class Upbit20_200Bot:
    """업비트 20/200 SMA 자동매매 봇"""

    def __init__(self, access_key=None, secret_key=None, telegram_token=None, telegram_chat_id=None,
                 dry_run=True, initial_balance_krw=None, timeframe=1):
        """
        Args:
            access_key: 업비트 API Access Key
            secret_key: 업비트 API Secret Key
            telegram_token: 텔레그램 봇 토큰
            telegram_chat_id: 텔레그램 채팅 ID
            dry_run: 시뮬레이션 모드 (True=가상거래, False=실거래)
            initial_balance_krw: 초기 자본 (KRW) - None이면 실제 잔고 조회
            timeframe: 타임프레임 (분) - 1, 3, 5, 10, 15, 30, 60
        """
        # 업비트 API
        self.upbit = UpbitAPI(
            access_key or os.getenv('UPBIT_ACCESS_KEY'),
            secret_key or os.getenv('UPBIT_SECRET_KEY')
        )

        # 텔레그램
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)

        # 코인 스캐너
        self.scanner = UpbitCoinScanner_20_200(
            min_volume_krw=10_000_000_000,  # 100억원 이상
            timeframe=timeframe
        )

        # 거래 모드
        self.dry_run = dry_run
        self.timeframe = timeframe

        # 자본 관리
        if initial_balance_krw is None:
            # 실제 잔고 조회
            if not dry_run:
                real_balance = self.get_account_balance()
                self.balance_krw = real_balance
                self.initial_balance = real_balance
            else:
                # 시뮬레이션이면 기본값 100만원
                self.balance_krw = 1_000_000
                self.initial_balance = 1_000_000
        else:
            self.balance_krw = initial_balance_krw
            self.initial_balance = initial_balance_krw

        # 현재 포지션
        self.position = None  # {'market', 'entry_price', 'amount', 'entry_time', 'partial_sold', 'invest_krw'}

        # 거래 기록
        self.trades = []

        # 전략 파라미터
        self.stop_loss_pct = -0.7
        self.partial_profit_pct = 1.5
        self.final_profit_pct = 3.0

        # 상태
        self.running = False

        print(f"\n{'='*70}")
        print(f"🤖 업비트 20/200 SMA 자동매매 봇 초기화")
        print(f"{'='*70}")
        print(f"모드: {'🔴 실거래' if not dry_run else '🟢 시뮬레이션'}")
        print(f"초기 자본: ₩{self.balance_krw:,.0f}")
        print(f"타임프레임: {timeframe}분")
        print(f"텔레그램: {'✅ 활성화' if self.telegram.enabled else '❌ 비활성화'}")
        print(f"{'='*70}\n")

    def get_current_price(self, market):
        """현재 가격 조회"""
        try:
            ticker = self.upbit.get_current_price(market)
            return ticker['trade_price']
        except Exception as e:
            print(f"❌ 가격 조회 실패 ({market}): {e}")
            return None

    def get_candles(self, market, count=250):
        """캔들 데이터 조회"""
        try:
            candles = self.upbit.get_candles(
                market=market,
                interval="minutes",
                unit=self.timeframe,
                count=count
            )

            if not candles:
                return None

            df = pd.DataFrame(candles)
            # 업비트는 최신 데이터가 먼저 오므로 역순 정렬
            df = df.iloc[::-1].reset_index(drop=True)

            df = df.rename(columns={
                'candle_date_time_kst': 'timestamp',
                'opening_price': 'open',
                'high_price': 'high',
                'low_price': 'low',
                'trade_price': 'close',
                'candle_acc_trade_volume': 'volume'
            })

            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            return df

        except Exception as e:
            print(f"❌ 캔들 조회 실패 ({market}): {e}")
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

    def check_sell_signal(self, current_price, df=None):
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

        # 4. 20MA 이탈 체크 (부분 익절 후)
        if self.position.get('partial_sold', False) and df is not None:
            latest = df.iloc[-1]
            if pd.notna(latest['sma20']) and current_price < latest['sma20']:
                return True, f"20MA이탈 ({profit_pct:+.2f}%)"

        return False, None

    def get_account_balance(self):
        """잔고 조회"""
        try:
            if self.dry_run:
                return self.balance_krw

            accounts = self.upbit.get_accounts()
            for account in accounts:
                if account['currency'] == 'KRW':
                    return float(account['balance'])
            return 0
        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return 0

    def execute_buy(self, market, price):
        """매수 실행"""
        if self.position:
            print("⚠️ 이미 포지션 보유 중")
            return False

        # 투자금액 (95%)
        invest_krw = self.balance_krw * 0.95
        amount = invest_krw / price
        fee = invest_krw * 0.0005  # 0.05% 수수료

        if self.dry_run:
            # 시뮬레이션
            self.position = {
                'market': market,
                'entry_price': price,
                'amount': amount,
                'invest_krw': invest_krw,
                'entry_time': datetime.now(),
                'partial_sold': False
            }
            self.balance_krw -= invest_krw

            msg = f"""
🟢 <b>매수 체결</b> (시뮬레이션)
━━━━━━━━━━━━━━━━━
코인: {market}
가격: ₩{price:,.0f}
수량: {amount:.6f}
투자: ₩{invest_krw:,.0f}
수수료: ₩{fee:,.0f}
잔고: ₩{self.balance_krw:,.0f}
"""
            print(msg)
            self.telegram.send(msg)
            return True

        else:
            # 실거래
            try:
                # 시장가 매수
                order = self.upbit.order_market_buy(market, invest_krw)

                if 'error' in order:
                    print(f"❌ 매수 실패: {order['error']['message']}")
                    self.telegram.send(f"❌ 매수 실패: {market}\n{order['error']['message']}")
                    return False

                # 체결 확인 대기 (최대 10초)
                for _ in range(10):
                    time.sleep(1)
                    ticker = self.upbit.get_current_price(market)
                    if ticker:
                        break

                self.position = {
                    'market': market,
                    'entry_price': ticker['trade_price'],
                    'amount': amount,  # 실제로는 주문 체결 정보에서 가져와야 함
                    'invest_krw': invest_krw,
                    'entry_time': datetime.now(),
                    'partial_sold': False,
                    'order_id': order.get('uuid', '')
                }

                msg = f"""
🟢 <b>매수 체결</b>
━━━━━━━━━━━━━━━━━
코인: {market}
가격: ₩{ticker['trade_price']:,.0f}
투자: ₩{invest_krw:,.0f}
주문ID: {order.get('uuid', '')[:8]}...
"""
                print(msg)
                self.telegram.send(msg)
                return True

            except Exception as e:
                print(f"❌ 매수 실패: {e}")
                self.telegram.send(f"❌ 매수 실패: {market}\n{e}")
                return False

    def execute_sell(self, price, reason):
        """매도 실행"""
        if not self.position:
            return False

        market = self.position['market']
        entry_price = self.position['entry_price']

        # 부분 익절 여부
        is_partial = "부분익절" in reason
        sell_ratio = 0.5 if is_partial else 1.0

        sell_amount = self.position['amount'] * sell_ratio
        sell_value = sell_amount * price
        fee = sell_value * 0.0005
        final_value = sell_value - fee

        profit = final_value - (self.position['invest_krw'] * sell_ratio)
        profit_pct = (profit / (self.position['invest_krw'] * sell_ratio)) * 100

        hold_time = datetime.now() - self.position['entry_time']
        hold_minutes = hold_time.total_seconds() / 60

        if self.dry_run:
            # 시뮬레이션
            self.balance_krw += final_value

            # 거래 기록
            trade = {
                'market': market,
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
코인: {market}
사유: {reason}
진입: ₩{entry_price:,.0f}
청산: ₩{price:,.0f}
수량: {sell_amount:.6f} ({sell_ratio*100:.0f}%)
수익: ₩{profit:+,.0f} ({profit_pct:+.2f}%)
보유: {hold_minutes:.1f}분
잔고: ₩{self.balance_krw:,.0f}
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
누적 수익: ₩{self.balance_krw - self.initial_balance:+,.0f} ({(self.balance_krw/self.initial_balance - 1)*100:+.2f}%)
"""
            print(msg)
            self.telegram.send(msg)

            # 포지션 업데이트
            if is_partial:
                self.position['amount'] *= 0.5
                self.position['invest_krw'] *= 0.5
                self.position['partial_sold'] = True
            else:
                self.position = None

            return True

        else:
            # 실거래
            try:
                # 시장가 매도
                order = self.upbit.order_market_sell(market, sell_amount)

                if 'error' in order:
                    print(f"❌ 매도 실패: {order['error']['message']}")
                    self.telegram.send(f"❌ 매도 실패: {market}\n{order['error']['message']}")
                    return False

                trade = {
                    'market': market,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'hold_minutes': hold_minutes,
                    'reason': reason,
                    'timestamp': datetime.now(),
                    'order_id': order.get('uuid', '')
                }
                self.trades.append(trade)

                msg = f"""
🔴 <b>매도 체결</b>
━━━━━━━━━━━━━━━━━
코인: {market}
사유: {reason}
진입: ₩{entry_price:,.0f}
청산: ₩{price:,.0f}
수익: ₩{profit:+,.0f} ({profit_pct:+.2f}%)
보유: {hold_minutes:.1f}분
주문ID: {order.get('uuid', '')[:8]}...
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
"""
                print(msg)
                self.telegram.send(msg)

                # 포지션 업데이트
                if is_partial:
                    self.position['amount'] *= 0.5
                    self.position['invest_krw'] *= 0.5
                    self.position['partial_sold'] = True
                else:
                    self.position = None

                return True

            except Exception as e:
                print(f"❌ 매도 실패: {e}")
                self.telegram.send(f"❌ 매도 실패: {market}\n{e}")
                return False

    def send_status(self):
        """현재 상태 전송"""
        # 기본 정보
        total_return = self.balance_krw - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        win_trades = [t for t in self.trades if t['profit'] > 0]
        win_rate = (len(win_trades) / len(self.trades) * 100) if self.trades else 0

        msg = f"""
📊 <b>봇 현재 상태</b>
━━━━━━━━━━━━━━━━━
모드: {'실거래' if not self.dry_run else '시뮬레이션'}
타임프레임: {self.timeframe}분

💰 <b>자본</b>
초기: ₩{self.initial_balance:,.0f}
현재: ₩{self.balance_krw:,.0f}
수익: ₩{total_return:+,.0f} ({total_return_pct:+.2f}%)

📈 <b>거래 통계</b>
총 거래: {len(self.trades)}회
승률: {win_rate:.1f}%
"""

        # 포지션 정보
        if self.position:
            market = self.position['market']
            entry_price = self.position['entry_price']
            current_price = self.get_current_price(market)

            if current_price:
                profit_pct = ((current_price - entry_price) / entry_price) * 100
                hold_time = datetime.now() - self.position['entry_time']
                hold_minutes = hold_time.total_seconds() / 60

                msg += f"""
🔵 <b>포지션 보유 중</b>
코인: {market}
진입가: ₩{entry_price:,.0f}
현재가: ₩{current_price:,.0f}
수익률: {profit_pct:+.2f}%
보유시간: {hold_minutes:.1f}분
부분익절: {'완료' if self.position.get('partial_sold') else '대기'}
"""
        else:
            msg += "\n⚪ 포지션 없음 (스캔 대기 중)\n"

        self.telegram.send(msg)

    def find_best_coin(self):
        """최적 코인 찾기"""
        print(f"\n{'='*70}")
        print(f"🔍 최적 코인 스캔 중...")
        print(f"{'='*70}")

        qualified_coins = self.scanner.scan_market(max_coins=30)

        if not qualified_coins:
            print("❌ 전략 조건 충족 코인 없음")
            return None

        # 최고 점수 코인
        best = qualified_coins[0]

        print(f"\n🏆 최적 코인 발견: {best['market']}")
        print(f"   점수: {best['score']:.1f}/100")
        print(f"   20MA 기울기: {best['details']['slope_pct']:.3f}%")
        print(f"   20MA 거리: {best['details']['distance_20ma']:+.2f}%")
        print(f"   거래대금: ₩{best['volume_krw']/1e8:.0f}억")

        msg = f"""
🎯 <b>최적 코인 발견</b>
━━━━━━━━━━━━━━━━━
코인: {best['market']}
점수: {best['score']:.1f}/100
20MA 기울기: {best['details']['slope_pct']:.3f}%
20MA 거리: {best['details']['distance_20ma']:+.2f}%
거래대금: ₩{best['volume_krw']/1e8:.0f}억
"""
        self.telegram.send(msg)

        return best['market']

    def run(self):
        """봇 실행"""
        self.running = True

        msg = f"""
🚀 <b>봇 시작</b>
━━━━━━━━━━━━━━━━━
모드: {'실거래' if not self.dry_run else '시뮬레이션'}
초기 자본: ₩{self.initial_balance:,.0f}
타임프레임: {self.timeframe}분
전략: 20/200 SMA
손절: {self.stop_loss_pct}%
부분익절: {self.partial_profit_pct}% (50%)
최종익절: {self.final_profit_pct}%
"""
        print(msg)
        self.telegram.send(msg)

        last_scan_time = None
        scan_interval = 300  # 5분마다 스캔
        no_coin_wait = 1800  # 조건 충족 코인 없을 때 30분 대기

        try:
            while self.running:
                # 텔레그램 명령어 체크
                messages = self.telegram.get_updates()
                for msg in messages:
                    msg_lower = msg.lower().strip()

                    if msg_lower in ['/stop', '중지', 'stop']:
                        self.telegram.send("🛑 봇 중지 명령 수신. 종료합니다...")
                        self.stop()
                        return

                    elif msg_lower in ['/status', '상태', 'status']:
                        self.send_status()

                    elif msg_lower in ['/help', '도움말', 'help']:
                        help_msg = """
📖 <b>명령어 도움말</b>
━━━━━━━━━━━━━━━━━
/stop - 봇 중지
/status - 현재 상태 확인
/help - 도움말 표시
"""
                        self.telegram.send(help_msg)

                # 포지션 없으면 코인 스캔
                if not self.position:
                    current_time = time.time()

                    # 스캔 간격 체크
                    if last_scan_time is None or (current_time - last_scan_time) >= scan_interval:
                        market = self.find_best_coin()
                        last_scan_time = current_time

                        if not market:
                            # 조건 충족 코인이 없을 때는 30분 대기
                            wait_minutes = no_coin_wait // 60
                            print(f"⏳ 조건 충족 코인 없음. {wait_minutes}분 후 재스캔...")
                            self.telegram.send(f"⚪ 조건 충족 코인이 없습니다.\n{wait_minutes}분 후 다시 스캔합니다.")

                            # 30분 대기를 1초씩 쪼개서 명령어 응답 빠르게
                            for _ in range(no_coin_wait):
                                time.sleep(1)
                                if not self.running:
                                    return
                            continue

                        # 매수 신호 재확인
                        df = self.get_candles(market)
                        if df is None:
                            time.sleep(1)
                            continue

                        df = self.calculate_indicators(df)

                        if self.check_buy_signal(df):
                            current_price = self.get_current_price(market)
                            if current_price:
                                self.execute_buy(market, current_price)
                        else:
                            print(f"⚠️ {market} 매수 조건 미충족")

                    time.sleep(1)  # 10초 → 1초로 변경

                # 포지션 있으면 모니터링
                else:
                    market = self.position['market']
                    current_price = self.get_current_price(market)

                    if not current_price:
                        time.sleep(1)
                        continue

                    # 캔들 데이터 조회 (20MA 이탈 체크용)
                    df = self.get_candles(market)
                    if df is not None:
                        df = self.calculate_indicators(df)

                    # 매도 신호 체크
                    should_sell, reason = self.check_sell_signal(current_price, df)

                    if should_sell:
                        self.execute_sell(current_price, reason)

                        # 포지션 완전히 청산되면 잠시 대기 후 재스캔
                        if not self.position:
                            print("\n✅ 포지션 청산 완료. 10초 후 재스캔 가능...")
                            last_scan_time = None  # 스캔 시간 리셋
                            # 10초 대기를 1초씩 쪼개기
                            for _ in range(10):
                                time.sleep(1)
                                if not self.running:
                                    return

                    else:
                        # 현재 수익률 표시
                        profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                        print(f"📊 {market} | 가격: ₩{current_price:,.0f} | 수익: {profit_pct:+.2f}%", end='\r')
                        time.sleep(1)  # 3초 → 1초로 변경

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
            market = self.position['market']
            current_price = self.get_current_price(market)
            if current_price:
                self.execute_sell(current_price, "봇종료")

        # 최종 결과
        total_return = self.balance_krw - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        win_trades = [t for t in self.trades if t['profit'] > 0]
        win_rate = (len(win_trades) / len(self.trades) * 100) if self.trades else 0

        msg = f"""
🛑 <b>봇 종료</b>
━━━━━━━━━━━━━━━━━
총 거래: {len(self.trades)}회
승률: {win_rate:.1f}%
초기 자본: ₩{self.initial_balance:,.0f}
최종 자본: ₩{self.balance_krw:,.0f}
총 수익: ₩{total_return:+,.0f} ({total_return_pct:+.2f}%)
"""
        print(msg)
        self.telegram.send(msg)


def main():
    """메인 함수"""
    import sys

    # 환경변수 체크
    access_key = os.getenv('UPBIT_ACCESS_KEY')
    secret_key = os.getenv('UPBIT_SECRET_KEY')
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

    # 모드 설정
    dry_run = True  # 기본값: 시뮬레이션
    timeframe = 1  # 기본값: 1분봉

    if len(sys.argv) > 1:
        if sys.argv[1] == 'live':
            if not access_key or not secret_key:
                print("❌ UPBIT_ACCESS_KEY와 UPBIT_SECRET_KEY 환경변수 필요")
                sys.exit(1)
            dry_run = False
            print("⚠️ 실거래 모드로 시작합니다!")
            time.sleep(3)
        else:
            try:
                timeframe = int(sys.argv[1])
            except:
                pass

    if len(sys.argv) > 2:
        try:
            timeframe = int(sys.argv[2])
        except:
            pass

    # 봇 생성 및 실행
    bot = Upbit20_200Bot(
        access_key=access_key,
        secret_key=secret_key,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        dry_run=dry_run,
        initial_balance_krw=None,  # 실거래는 실제 잔고, 시뮬레이션은 100만원
        timeframe=timeframe
    )

    bot.run()


if __name__ == "__main__":
    main()
