#!/usr/bin/env python3
"""
업비트 하이브리드 자동매매 봇

시장 상황에 따라 자동 전환:
- BOX MODE: 횡보장 → 박스권 전략
- TREND MODE: 추세장 → 20/200 SMA 전략

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
        self.last_update_id = 0

        if not self.enabled:
            print("⚠️ 텔레그램 설정 없음")

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

    def get_updates(self):
        """명령어 확인"""
        if not self.enabled:
            return []

        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 1}
            response = requests.get(url, params=params, timeout=5)

            if response.ok:
                data = response.json()
                if data.get('result'):
                    self.last_update_id = data['result'][-1]['update_id']
                    return [u['message']['text'] for u in data['result'] if 'message' in u and 'text' in u['message']]
        except requests.exceptions.RequestException:
            pass

        return []


class UpbitHybridBot:
    """업비트 하이브리드 봇"""

    def __init__(self, access_key, secret_key, telegram_token=None, telegram_chat_id=None,
                 dry_run=True, initial_balance_krw=None, timeframe=5):
        """
        초기화

        Args:
            dry_run: 시뮬레이션 모드 (True=가상거래, False=실거래)
            initial_balance_krw: 초기 자본 (None이면 실거래는 실제 잔고, 시뮬레이션은 100만원)
            timeframe: 분봉 (5=5분봉)
        """
        self.upbit = UpbitAPI(access_key, secret_key)
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        self.dry_run = dry_run
        self.timeframe = timeframe
        self.running = True

        # 자산 관리
        if initial_balance_krw is None:
            if not dry_run:
                # 실거래: 초기 자본을 파일에서 읽기 (없으면 현재 잔고로 생성)
                import os.path
                initial_balance_file = 'initial_balance.txt'

                if os.path.exists(initial_balance_file):
                    with open(initial_balance_file, 'r') as f:
                        self.initial_balance = float(f.read().strip())
                    print(f"📂 초기 자본 로드: {self.initial_balance:,.0f}원")
                else:
                    real_balance = self.get_account_balance()
                    self.initial_balance = real_balance
                    with open(initial_balance_file, 'w') as f:
                        f.write(str(self.initial_balance))
                    print(f"📂 초기 자본 저장: {self.initial_balance:,.0f}원")

                self.balance_krw = self.get_account_balance()
            else:
                self.balance_krw = 1000000
                self.initial_balance = 1000000
        else:
            self.balance_krw = initial_balance_krw
            self.initial_balance = initial_balance_krw

        # 포지션
        self.position = None
        self.partial_sold = False
        self.trades = []

        # 모드
        self.current_mode = 'BOX'
        self.mode_history = []

        print(f"\n{'='*60}")
        print(f"업비트 하이브리드 봇 시작")
        print(f"{'='*60}")
        print(f"모드: {'🔴 실거래' if not dry_run else '🟢 시뮬레이션'}")
        print(f"초기 자본: {self.initial_balance:,.0f}원")
        print(f"타임프레임: {timeframe}분봉")
        print(f"초기 모드: {self.current_mode}")
        print(f"{'='*60}\n")

        # 실거래 모드일 때 기존 보유 코인 확인
        if not dry_run:
            self.check_existing_position()

    def get_account_balance(self):
        """계좌 잔고 조회 (KRW + 보유 코인 평가금액)"""
        try:
            accounts = self.upbit.get_accounts()
            total_balance = 0
            krw_balance = 0

            for account in accounts:
                if account['currency'] == 'KRW':
                    krw_balance = float(account['balance'])
                    total_balance += krw_balance
                else:
                    # 보유 코인 평가금액
                    avg_buy_price = float(account.get('avg_buy_price', 0))
                    balance = float(account.get('balance', 0))
                    coin_value = avg_buy_price * balance
                    if coin_value > 0:
                        total_balance += coin_value
                        print(f"💰 보유 코인: {account['currency']} ({balance:.8f}개) = {coin_value:,.0f}원")

            print(f"✅ KRW 잔고: {krw_balance:,.0f}원")
            print(f"✅ 총 자산: {total_balance:,.0f}원")
            return total_balance
        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return 0

    def check_existing_position(self):
        """기존 보유 코인 확인 (가장 가치 높은 코인을 포지션으로)"""
        try:
            accounts = self.upbit.get_accounts()
            max_value = 0
            max_coin = None

            # 모든 코인 중 가장 가치 높은 것 찾기
            for account in accounts:
                if account['currency'] != 'KRW':
                    balance = float(account.get('balance', 0))
                    avg_buy_price = float(account.get('avg_buy_price', 0))
                    coin_value = balance * avg_buy_price

                    if coin_value > max_value:
                        max_value = coin_value
                        max_coin = {
                            'currency': account['currency'],
                            'balance': balance,
                            'avg_buy_price': avg_buy_price,
                            'value': coin_value
                        }

            # 가치가 1000원 이상인 코인만 포지션으로 설정
            if max_coin and max_value > 1000:
                market = f"KRW-{max_coin['currency']}"

                # 현재가 조회
                df = self.fetch_candles(market, count=1)
                current_price = df.iloc[-1]['close'] if df is not None and len(df) > 0 else max_coin['avg_buy_price']
                profit_pct = ((current_price - max_coin['avg_buy_price']) / max_coin['avg_buy_price']) * 100

                print(f"\n🔍 기존 포지션 발견!")
                print(f"코인: {market}")
                print(f"수량: {max_coin['balance']:.8f}개")
                print(f"진입가: {max_coin['avg_buy_price']:,.0f}원")
                print(f"현재가: {current_price:,.0f}원")
                print(f"수익률: {profit_pct:+.2f}%")
                print(f"평가금액: {max_value:,.0f}원")

                # 포지션 설정 (기존 포지션임을 표시)
                self.position = {
                    'market': market,
                    'entry_price': max_coin['avg_buy_price'],
                    'quantity': max_coin['balance'],
                    'entry_mode': 'BOX',  # 기본값
                    'entry_time': datetime.now(),
                    'is_existing': True  # 기존 포지션 플래그
                }

                self.telegram.send(f"📌 기존 포지션 인식\n코인: {market}\n진입가: {max_coin['avg_buy_price']:,.0f}원\n현재가: {current_price:,.0f}원\n수익률: {profit_pct:+.2f}%\n평가금액: {max_value:,.0f}원")
        except Exception as e:
            print(f"❌ 기존 포지션 확인 실패: {e}")

    def fetch_candles(self, market, count=200):
        """캔들 데이터 수집"""
        try:
            url = f"https://api.upbit.com/v1/candles/minutes/{self.timeframe}"
            params = {"market": market, "count": count}
            response = requests.get(url, params=params)
            candles = response.json()

            if not candles or not isinstance(candles, list):
                return None

            df = pd.DataFrame(candles)
            # 업비트는 최신 데이터가 먼저 오므로 역순 정렬
            df = df.iloc[::-1].reset_index(drop=True)

            # 필요한 컬럼만 선택하고 새 DataFrame 생성 (중복 키 방지)
            df_clean = pd.DataFrame({
                'timestamp': pd.to_datetime(df['candle_date_time_kst'], format='ISO8601'),
                'open': df['opening_price'],
                'high': df['high_price'],
                'low': df['low_price'],
                'close': df['trade_price'],
                'volume': df['candle_acc_trade_volume']
            })

            return df_clean
        except Exception as e:
            print(f"❌ 캔들 조회 실패 ({market}): {e}")
            return None

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

        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        df['atr_change'] = df['atr'].pct_change(5) * 100

        # 거래량
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 20MA 거리
        df['distance_to_20ma'] = ((df['close'] - df['sma20']) / df['sma20']) * 100

        return df

    def detect_market_mode(self, row, prev_mode=None):
        """시장 모드 감지 (히스테리시스 적용)

        Args:
            row: 분석할 데이터 행
            prev_mode: 이전 모드 (None이면 독립 감지, 지정하면 히스테리시스 적용)
        """
        if pd.isna(row['slope_20ma']) or pd.isna(row['slope_200ma']):
            return 'BOX'

        # BOX MODE 조건
        ma20_flat = -0.15 <= row['slope_20ma'] <= 0.15
        ma200_not_rising = row['slope_200ma'] < 0.15
        box_range_ok = 4.0 <= row['box_range_pct'] <= 10.0 if not pd.isna(row['box_range_pct']) else False
        low_volatility = row['atr_pct'] < 4.0 if not pd.isna(row['atr_pct']) else False

        # TREND MODE 조건
        ma20_strong_trend = abs(row['slope_20ma']) > 0.3
        same_direction = (row['slope_20ma'] > 0 and row['slope_200ma'] > 0) or \
                        (row['slope_20ma'] < 0 and row['slope_200ma'] < 0)
        atr_increasing = row['atr_change'] > 15.0 if not pd.isna(row['atr_change']) else False
        strong_volume = row['volume_ratio'] > 2.0 if not pd.isna(row['volume_ratio']) else False

        # 독립 감지 (스캔용 - prev_mode가 None일 때)
        if prev_mode is None:
            trend_signals = [ma20_strong_trend and same_direction, atr_increasing, strong_volume]
            return 'TREND' if sum(trend_signals) >= 2 else 'BOX'

        # 히스테리시스 적용 (포지션 모니터링용)
        if prev_mode == 'BOX':
            trend_signals = [ma20_strong_trend and same_direction, atr_increasing, strong_volume]
            return 'TREND' if sum(trend_signals) >= 2 else 'BOX'
        else:
            box_signals = [ma20_flat, ma200_not_rising, box_range_ok, low_volatility]
            return 'BOX' if sum(box_signals) >= 3 else 'TREND'

    def check_entry_trend(self, row):
        """추세 전략 진입"""
        if pd.isna(row['sma20']) or pd.isna(row['sma200']):
            return False

        uptrend = row['slope_20ma'] > 0.2
        above_200ma = row['close'] > row['sma200']
        near_20ma = abs(row['distance_to_20ma']) <= 3.0

        return uptrend and above_200ma and near_20ma

    def check_entry_box(self, row):
        """박스권 전략 진입 (반등 확인 추가)"""
        if pd.isna(row['box_position']) or pd.isna(row['rsi']):
            return False

        # 1. 박스 하단 (10-25%로 범위 축소)
        at_bottom = 10 <= row['box_position'] <= 25

        # 2. RSI 과매도 (< 35)
        rsi_oversold = row['rsi'] < 35

        # 3. 반등 확인: 현재가가 저가보다 높음 (바닥에서 올라오는 중)
        bouncing = row['close'] > row['low']

        # 4. 거래량 감소 (매도 압력 소진, 선택적)
        volume_ok = True
        if not pd.isna(row.get('volume_ratio')):
            # 거래량이 평균보다 너무 많지 않음 (패닉 매도 아님)
            volume_ok = row['volume_ratio'] < 2.0

        # 5. 20MA 기울기 체크: 급격한 하락 중이 아님 (추가 조건)
        not_falling = True
        if not pd.isna(row.get('slope_20ma')):
            # 20MA 기울기가 -0.5% 이상 (너무 가파른 하락 중이 아님)
            not_falling = row['slope_20ma'] > -0.5

        return at_bottom and rsi_oversold and bouncing and volume_ok and not_falling

    def check_exit_trend(self, row, entry_price):
        """추세 전략 청산"""
        profit_pct = ((row['close'] - entry_price) / entry_price) * 100

        if profit_pct <= -0.7:
            details = f"손절 (수익률: {profit_pct:.2f}% ≤ -0.7%)"
            return True, "손절", details

        if self.partial_sold:
            if profit_pct >= 3.0:
                details = f"목표 익절 (수익률: {profit_pct:.2f}% ≥ 3.0%, 부분매도 후)"
                return True, "목표 익절", details
            if row['close'] < row['sma20']:
                details = f"20MA 이탈 (현재가: {row['close']:,.0f}원 < 20MA: {row['sma20']:,.0f}원, 부분매도 후)"
                return True, "20MA 이탈", details
        elif profit_pct >= 1.5:
            details = f"부분 익절 (수익률: {profit_pct:.2f}% ≥ 1.5%)"
            return True, "부분 익절", details

        return False, None, None

    def check_exit_box(self, row, entry_price):
        """박스권 전략 청산"""
        profit_pct = ((row['close'] - entry_price) / entry_price) * 100

        if profit_pct <= -1.0:
            details = f"손절 (수익률: {profit_pct:.2f}% ≤ -1.0%)"
            return True, "손절", details

        if not pd.isna(row['box_position']) and row['box_position'] > 70 and profit_pct >= 1.5:
            details = f"박스 상단 익절 (박스 위치: {row['box_position']:.1f}% > 70%, 수익률: {profit_pct:.2f}% ≥ 1.5%)"
            return True, "박스 상단 익절", details

        if not pd.isna(row['rsi']) and row['rsi'] > 70 and profit_pct >= 1.0:
            details = f"RSI 과매수 익절 (RSI: {row['rsi']:.1f} > 70, 수익률: {profit_pct:.2f}% ≥ 1.0%)"
            return True, "RSI 과매수 익절", details

        if profit_pct >= 2.5:
            details = f"목표 익절 (수익률: {profit_pct:.2f}% ≥ 2.5%)"
            return True, "목표 익절", details

        return False, None, None

    def scan_markets(self):
        """코인 스캔"""
        try:
            # 모든 KRW 마켓 가져오기
            url = "https://api.upbit.com/v1/market/all"
            response = requests.get(url)
            all_markets = response.json()
            markets = [m['market'] for m in all_markets if m['market'].startswith('KRW-')]

            # 1차: 모든 코인의 거래대금 수집
            volume_data = []
            print(f"\n🔍 거래량 분석 중...")

            for market in markets:
                df = self.fetch_candles(market, count=1)
                if df is None or len(df) < 1:
                    continue

                latest = df.iloc[-1]
                volume_krw = latest['volume'] * latest['close']  # 거래대금 (KRW)
                volume_data.append({
                    'market': market,
                    'volume_krw': volume_krw
                })
                time.sleep(0.05)

            # 거래대금 기준 정렬
            volume_data.sort(key=lambda x: x['volume_krw'], reverse=True)

            # 상위 50개 코인만 스캔 (거래량 상위권)
            top_volume_markets = [v['market'] for v in volume_data[:50]]
            print(f"📊 거래량 상위 50개 코인 선정 완료\n")

            # 2차: 선정된 코인만 상세 분석
            qualified = []
            print(f"🔍 스캔 시작: {len(top_volume_markets)}개 코인")

            for market in top_volume_markets:
                df = self.fetch_candles(market, count=200)
                if df is None or len(df) < 200:
                    continue

                df = self.calculate_indicators(df)
                latest = df.iloc[-1]

                # 모드 감지 (독립 감지 - prev_mode=None)
                mode = self.detect_market_mode(latest, prev_mode=None)

                # 진입 조건 체크
                entry_signal = False
                if mode == 'TREND':
                    entry_signal = self.check_entry_trend(latest)
                elif mode == 'BOX':
                    entry_signal = self.check_entry_box(latest)

                # 메트릭 로그 출력
                box_pos = latest.get('box_position', 0)
                rsi = latest.get('rsi', 0)
                volume_ratio = latest.get('volume_ratio', 0)
                slope = latest.get('slope_20ma', 0)
                volume_krw = latest['volume'] * latest['close']

                log_msg = f"{market}: 가격={latest['close']:,.0f}, RSI={rsi:.1f}, 박스={box_pos:.1f}%, 거래량비={volume_ratio:.2f}, 거래대금={volume_krw/1e8:.1f}억, 기울기={slope:.4f}, 모드={mode}"

                if entry_signal:
                    print(f"✅ {log_msg} -> 진입신호")
                    qualified.append({
                        'market': market,
                        'price': latest['close'],
                        'mode': mode,
                        'slope': latest['slope_20ma'],
                        'rsi': latest['rsi'],
                        'volume_ratio': latest['volume_ratio']
                    })
                else:
                    print(f"   {log_msg}")

                time.sleep(0.1)

            print(f"📊 스캔 완료: {len(top_volume_markets)}개 중 {len(qualified)}개 진입신호\n")

            if qualified:
                # slope와 volume_ratio를 혼합해서 정렬 (거래량도 고려)
                qualified.sort(key=lambda x: abs(x['slope']) * (1 + x['volume_ratio']), reverse=True)

            return qualified
        except Exception as e:
            print(f"❌ 스캔 실패: {e}")
            return []

    def execute_buy(self, market, price):
        """매수 실행"""
        if self.dry_run:
            quantity = self.balance_krw / price
            self.position = {
                'market': market,
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'entry_mode': self.current_mode
            }
            self.balance_krw = 0
            return True
        else:
            # 실거래 매수
            try:
                # 실시간 잔고 조회
                real_balance = self.get_account_balance()
                krw_only = 0

                # KRW 잔고만 추출
                accounts = self.upbit.get_accounts()
                for account in accounts:
                    if account['currency'] == 'KRW':
                        krw_only = float(account['balance'])
                        break

                buy_amount = krw_only * 0.9995
                print(f"💳 매수 시도: {market}, KRW 잔고: {krw_only:,.0f}원, 매수 금액: {buy_amount:,.0f}원")

                result = self.upbit.buy_market_order(market, buy_amount)

                print(f"📋 매수 결과: {result}")

                if result and isinstance(result, dict) and 'uuid' in result:
                    # 주문 생성 성공
                    order_uuid = result['uuid']
                    print(f"⏳ 주문 생성 완료 (UUID: {order_uuid}), 체결 대기 중...")

                    # 최대 10초간 체결 대기
                    for i in range(10):
                        time.sleep(1)
                        order_info = self.upbit.get_order(order_uuid)
                        print(f"📊 체결 확인 ({i+1}/10): state={order_info.get('state')}, executed_volume={order_info.get('executed_volume')}")

                        if order_info and order_info.get('state') in ['done', 'cancel']:
                            executed_volume = float(order_info.get('executed_volume', 0))

                            # 체결된 수량이 있으면 성공 (부분 체결 후 취소도 포함)
                            if executed_volume > 0:
                                paid_fee = float(order_info.get('paid_fee', 0))
                                avg_price = float(order_info.get('trades', [{}])[0].get('price', price)) if order_info.get('trades') else price

                                self.position = {
                                    'market': market,
                                    'entry_price': avg_price,
                                    'entry_time': datetime.now(),
                                    'quantity': executed_volume,
                                    'entry_mode': self.current_mode
                                }
                                self.balance_krw = 0
                                print(f"✅ 매수 완료: {executed_volume:.8f}개, 평균가: {avg_price:,.0f}원, 수수료: {paid_fee:,.0f}원 (상태: {order_info.get('state')})")
                                return True
                            else:
                                print(f"❌ 매수 실패: 주문 취소됨 (executed_volume=0)")
                                return False

                    print(f"❌ 매수 실패: 체결 시간 초과")
                else:
                    print(f"❌ 매수 실패: 잘못된 응답 형식")
            except Exception as e:
                print(f"❌ 매수 실패 (예외): {e}")
                import traceback
                traceback.print_exc()
        return False

    def execute_sell(self, price, ratio=1.0):
        """매도 실행"""
        if self.dry_run:
            sell_quantity = self.position['quantity'] * ratio
            profit = (price - self.position['entry_price']) * sell_quantity
            self.balance_krw += self.position['entry_price'] * sell_quantity + profit

            if ratio >= 1.0:
                self.position = None
                self.partial_sold = False
            else:
                self.position['quantity'] -= sell_quantity
                self.partial_sold = True

            return True, profit
        else:
            # 실거래 매도
            try:
                sell_quantity = self.position['quantity'] * ratio
                print(f"💳 매도 시도: {self.position['market']}, 수량: {sell_quantity:.8f}개")

                result = self.upbit.sell_market_order(self.position['market'], sell_quantity)

                print(f"📋 매도 결과: {result}")

                if result and isinstance(result, dict) and 'uuid' in result:
                    # 주문 생성 성공
                    order_uuid = result['uuid']
                    print(f"⏳ 주문 생성 완료 (UUID: {order_uuid}), 체결 대기 중...")

                    # 최대 10초간 체결 대기
                    for i in range(10):
                        time.sleep(1)
                        order_info = self.upbit.get_order(order_uuid)
                        print(f"📊 체결 확인 ({i+1}/10): state={order_info.get('state')}, executed_volume={order_info.get('executed_volume')}")

                        if order_info and order_info.get('state') in ['done', 'cancel']:
                            executed_volume = float(order_info.get('executed_volume', 0))

                            # 체결된 수량이 있으면 성공 (부분 체결 후 취소도 포함)
                            if executed_volume > 0:
                                paid_fee = float(order_info.get('paid_fee', 0))
                                trades = order_info.get('trades', [])
                                avg_price = float(trades[0].get('price', price)) if trades else price

                                profit = (avg_price - self.position['entry_price']) * executed_volume - paid_fee
                                self.balance_krw += avg_price * executed_volume - paid_fee

                                if ratio >= 1.0:
                                    self.position = None
                                    self.partial_sold = False
                                else:
                                    self.position['quantity'] -= executed_volume
                                    self.partial_sold = True

                                print(f"✅ 매도 완료: {executed_volume:.8f}개, 평균가: {avg_price:,.0f}원, 수수료: {paid_fee:,.0f}원, 수익: {profit:,.0f}원 (상태: {order_info.get('state')})")
                                return True, profit
                            else:
                                print(f"❌ 매도 실패: 주문 취소됨 (executed_volume=0)")
                                return False, 0

                    print(f"❌ 매도 실패: 체결 시간 초과")
            except Exception as e:
                print(f"❌ 매도 실패 (예외): {e}")
                import traceback
                traceback.print_exc()

        return False, 0

    def run(self):
        """봇 실행"""
        self.telegram.send(f"🚀 하이브리드 봇 시작\n초기자본: {self.initial_balance:,.0f}원\n모드: {self.current_mode}")

        scan_interval = 300  # 5분

        while self.running:
            try:
                # 텔레그램 명령어 체크
                commands = self.telegram.get_updates()
                for cmd in commands:
                    if cmd == '/stop':
                        self.running = False
                        self.telegram.send("🛑 봇 중지")
                        break
                    elif cmd == '/status':
                        status = self.get_status()
                        self.telegram.send(status)
                    elif cmd == '/help':
                        self.telegram.send("명령어:\n/status - 상태 확인\n/stop - 봇 중지\n/help - 도움말")

                if not self.running:
                    break

                # 포지션 없으면 스캔
                if self.position is None:
                    print(f"\n🔍 코인 스캔 중... (모드: {self.current_mode})")
                    qualified = self.scan_markets()

                    if qualified:
                        best = qualified[0]
                        print(f"✅ 진입 신호: {best['market']} ({best['mode']} 모드)")

                        if self.execute_buy(best['market'], best['price']):
                            self.current_mode = best['mode']
                            self.telegram.send(f"📈 매수 성공\n코인: {best['market']}\n모드: {best['mode']}\n가격: {best['price']:,.0f}원")
                        else:
                            print(f"❌ 매수 실행 실패, 계속 스캔합니다")
                            self.telegram.send(f"❌ 매수 실패\n코인: {best['market']}\n사유: API 오류")

                # 포지션 있으면 모니터링
                else:
                    df = self.fetch_candles(self.position['market'], count=200)
                    if df is not None:
                        df = self.calculate_indicators(df)
                        latest = df.iloc[-1]

                        # 현재가
                        current_price = latest['close']

                        # 실거래일 때는 업비트 avg_buy_price 기준 수익률 계산
                        if not self.dry_run:
                            try:
                                accounts = self.upbit.get_accounts()
                                upbit_avg_price = self.position['entry_price']  # 기본값

                                for account in accounts:
                                    if f"KRW-{account['currency']}" == self.position['market']:
                                        upbit_avg_price = float(account.get('avg_buy_price', self.position['entry_price']))
                                        break

                                profit_pct = ((current_price - upbit_avg_price) / upbit_avg_price) * 100
                            except:
                                # API 오류 시 기존 진입가 사용
                                profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                        else:
                            # 시뮬레이션은 기존 진입가 사용
                            profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100

                        # 1분마다 상태 출력 (60초 = 60번 루프)
                        current_second = int(time.time()) % 60
                        if current_second == 0:
                            print(f"\n📊 {self.position['market']} 모니터링")
                            print(f"현재가: {current_price:,.0f}원 | 진입가: {self.position['entry_price']:,.0f}원 | 수익률: {profit_pct:+.2f}%")
                            print(f"RSI: {latest['rsi']:.1f} | 모드: {self.current_mode}")

                        # 모드 업데이트 (히스테리시스 적용 - prev_mode 전달)
                        new_mode = self.detect_market_mode(latest, prev_mode=self.current_mode)
                        if new_mode != self.current_mode:
                            print(f"🔄 모드 전환: {self.current_mode} → {new_mode}")
                            self.current_mode = new_mode

                        # 청산 체크 - 두 가지 전략 모두 확인 (먼저 충족되는 조건 사용)
                        should_exit, reason, exit_details = (None, None, None)

                        # BOX 전략 청산 조건
                        box_exit, box_reason, box_details = self.check_exit_box(latest, self.position['entry_price'])

                        # TREND 전략 청산 조건
                        trend_exit, trend_reason, trend_details = self.check_exit_trend(latest, self.position['entry_price'])

                        # 기존 포지션은 손절 제외 (언제/왜 샀는지 모르므로)
                        is_existing = self.position.get('is_existing', False)
                        if is_existing:
                            if box_exit and box_reason == "손절":
                                box_exit = False
                                box_reason = None
                                box_details = None
                            if trend_exit and trend_reason == "손절":
                                trend_exit = False
                                trend_reason = None
                                trend_details = None

                        # 둘 중 하나라도 청산 신호면 매도 (보수적)
                        if box_exit:
                            should_exit, reason, exit_details = box_exit, f"BOX: {box_reason}", box_details
                        elif trend_exit:
                            should_exit, reason, exit_details = trend_exit, f"TREND: {trend_reason}", trend_details

                        if should_exit:
                            if reason == "부분 익절":
                                success, profit = self.execute_sell(latest['close'], ratio=0.5)
                                if success:
                                    profit_pct = (profit / self.initial_balance) * 100

                                    # 실거래는 실제 잔고 조회
                                    if not self.dry_run:
                                        current_total = self.get_account_balance()
                                    else:
                                        current_total = self.balance_krw + self.position['quantity'] * latest['close']

                                    total_return = ((current_total - self.initial_balance) / self.initial_balance) * 100

                                    log_msg = f"💰 부분 익절 ({profit_pct:+.2f}%)\n조건: {exit_details}"
                                    print(log_msg)
                                    self.telegram.send(f"💰 부분 익절 50%\n조건: {exit_details}\n수익: {profit_pct:+.2f}%\n총 자산: {current_total:,.0f}원\n누적: {total_return:+.2f}%")
                            else:
                                success, profit = self.execute_sell(latest['close'], ratio=1.0)
                                if success:
                                    profit_pct = (profit / self.initial_balance) * 100

                                    # 실거래는 실제 잔고 조회, 시뮬레이션은 balance_krw 사용
                                    if not self.dry_run:
                                        current_total = self.get_account_balance()
                                    else:
                                        current_total = self.balance_krw

                                    total_return = ((current_total - self.initial_balance) / self.initial_balance) * 100

                                    log_msg = f"📊 전체 청산 ({reason}): {profit_pct:+.2f}% | 누적: {total_return:+.2f}%\n조건: {exit_details}"
                                    print(log_msg)
                                    self.telegram.send(f"📊 매도 ({reason})\n조건: {exit_details}\n수익: {profit_pct:+.2f}%\n총 자산: {current_total:,.0f}원\n누적: {total_return:+.2f}%")

                time.sleep(1)

            except KeyboardInterrupt:
                print("\n⚠️ 사용자 중지")
                self.running = False
            except Exception as e:
                print(f"❌ 오류: {e}")
                time.sleep(5)

        print("\n봇 종료")
        self.telegram.send("✅ 봇 종료")

    def get_status(self):
        """상태 조회"""
        # 실거래는 실제 잔고 조회, 시뮬레이션은 계산
        if not self.dry_run:
            current_total = self.get_account_balance()
        else:
            if self.position:
                df = self.fetch_candles(self.position['market'], count=200)
                if df is not None:
                    current_price = df.iloc[-1]['close']
                    current_total = self.balance_krw + self.position['quantity'] * current_price
                else:
                    current_total = self.balance_krw
            else:
                current_total = self.balance_krw

        total_return = ((current_total - self.initial_balance) / self.initial_balance) * 100

        if self.position:
            df = self.fetch_candles(self.position['market'], count=200)
            if df is not None:
                current_price = df.iloc[-1]['close']
                profit_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100

                return f"""📊 현재 상태
모드: {self.current_mode}
코인: {self.position['market']}
진입가: {self.position['entry_price']:,.0f}원
현재가: {current_price:,.0f}원
수익률: {profit_pct:+.2f}%
총 자산: {current_total:,.0f}원
누적 수익률: {total_return:+.2f}%
"""
        else:
            return f"""📊 현재 상태
모드: {self.current_mode}
포지션: 없음
총 자산: {current_total:,.0f}원
누적 수익률: {total_return:+.2f}%
"""


if __name__ == "__main__":
    access_key = os.getenv('UPBIT_ACCESS_KEY')
    secret_key = os.getenv('UPBIT_SECRET_KEY')
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

    # 모드 설정
    dry_run = True
    timeframe = 5

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

    # 봇 실행
    bot = UpbitHybridBot(
        access_key=access_key,
        secret_key=secret_key,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        dry_run=dry_run,
        initial_balance_krw=None,
        timeframe=timeframe
    )

    bot.run()
