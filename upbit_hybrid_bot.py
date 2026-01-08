#!/usr/bin/env python3
"""
실전 자동매매 봇 - 멀티 코인 다층 전략

핵심 원리:
1. 다층 방어 시스템 (Buy & Hold + Momentum + Volatility)
2. 멀티 코인 분산 (BTC, ETH, SOL, XRP, ADA)
3. 동적 리밸런싱 (월 1회)
4. 엄격한 리스크 관리 (각 Layer 독립적 손절)
"""

import pyupbit
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
import os
import requests


class TelegramNotifier:
    """텔레그램 알림"""

    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = self.token and self.chat_id
        self.update_id_file = 'telegram_last_update_id.txt'
        self.last_update_id = self._load_last_update_id()
        self.stop_requested = False

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
                        self._save_last_update_id()
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


class LiveTradingBot:
    """실전 자동매매 봇"""

    def __init__(self, access_key, secret_key, initial_balance=None):
        """
        초기화

        Args:
            access_key: 업비트 Access Key
            secret_key: 업비트 Secret Key
            initial_balance: 초기 자본 (None이면 현재 잔고 사용)
        """
        self.upbit = pyupbit.Upbit(access_key, secret_key)

        # 거래할 코인 목록
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA']
        self.markets = [f'KRW-{coin}' for coin in self.coins]

        # 코인별 균등 배분 (20% 씩)
        self.coin_allocation = {coin: 0.20 for coin in self.coins}

        # Layer별 배분
        self.layer_allocation = {
            'buy_hold': 0.60,      # 60%: 장기 보유
            'momentum_trend': 0.25, # 25%: 강한 모멘텀
            'momentum_swing': 0.10, # 10%: 중간 모멘텀
            'volatility': 0.05      # 5%: 변동성 브레이크아웃
        }

        # 초기 자본 설정
        if initial_balance is None:
            self.initial_balance = self.get_total_balance()
        else:
            self.initial_balance = initial_balance

        print(f"🤖 봇 초기화 완료")
        print(f"초기 자본: {self.initial_balance:,.0f}원")
        print(f"거래 코인: {', '.join(self.coins)}")

        # 포지션 상태 파일
        self.position_file = 'bot_positions.json'
        self.positions = self.load_positions()

        # 마지막 리밸런싱 시간
        self.last_rebalance = None

        # 텔레그램 알림
        self.telegram = TelegramNotifier()
        self.telegram.send(
            f"🤖 <b>Ultimate 전략 봇 시작</b>\n\n"
            f"💰 초기 자본: {self.initial_balance:,.0f}원\n"
            f"🪙 거래 코인: {', '.join(self.coins)}\n\n"
            f"📊 Layer 배분:\n"
            f"  - Buy & Hold: 60%\n"
            f"  - Momentum Trend: 25%\n"
            f"  - Momentum Swing: 10%\n"
            f"  - Volatility: 5%"
        )


    def get_total_balance(self):
        """총 자산 계산 (KRW + 보유 코인 평가액)"""
        balances = self.upbit.get_balances()
        total = 0

        for balance in balances:
            currency = balance['currency']
            amount = float(balance['balance'])

            if currency == 'KRW':
                total += amount
            else:
                # 코인 현재가 조회
                ticker = f'KRW-{currency}'
                price = pyupbit.get_current_price(ticker)
                if price:
                    total += amount * price

        return total


    def load_positions(self):
        """저장된 포지션 로드"""
        if os.path.exists(self.position_file):
            with open(self.position_file, 'r') as f:
                return json.load(f)
        else:
            # 초기 포지션 구조
            positions = {}
            for coin in self.coins:
                positions[coin] = {
                    'buy_hold': None,
                    'momentum_trend': None,
                    'momentum_swing': None,
                    'volatility': None
                }
            return positions


    def save_positions(self):
        """포지션 저장"""
        with open(self.position_file, 'w') as f:
            json.dump(self.positions, f, indent=2, default=str)


    def calculate_momentum_score(self, df):
        """
        모멘텀 스코어 계산 (100점 만점)

        구성:
        - 다중 이동평균 배열: 40점
        - 가격 모멘텀: 30점
        - 볼륨 트렌드: 15점
        - RSI: 15점
        """
        if len(df) < 200:
            return 0

        current = df.iloc[-1]
        score = 0

        # 1. 이동평균 배열 (40점)
        ma10 = df['close'].iloc[-10:].mean()
        ma20 = df['close'].iloc[-20:].mean()
        ma50 = df['close'].iloc[-50:].mean()
        ma100 = df['close'].iloc[-100:].mean()
        ma200 = df['close'].iloc[-200:].mean()

        if current['close'] > ma10 > ma20 > ma50 > ma100 > ma200:
            score += 40  # 완벽한 상승 배열
        elif current['close'] > ma20 > ma50 > ma100:
            score += 30
        elif current['close'] > ma20 > ma50:
            score += 20
        elif current['close'] > ma20:
            score += 10

        # 2. 가격 모멘텀 (30점)
        ret_5d = (current['close'] - df.iloc[-6]['close']) / df.iloc[-6]['close']
        ret_20d = (current['close'] - df.iloc[-21]['close']) / df.iloc[-21]['close']
        ret_60d = (current['close'] - df.iloc[-61]['close']) / df.iloc[-61]['close']

        if ret_5d > 0 and ret_20d > 0 and ret_60d > 0:
            score += 15
            if ret_5d > ret_20d > ret_60d:  # 가속 모멘텀
                score += 15

        # 3. 볼륨 트렌드 (15점)
        vol_ma20 = df['volume'].iloc[-20:].mean()
        vol_ma50 = df['volume'].iloc[-50:].mean()

        if current['volume'] > vol_ma20 > vol_ma50:
            score += 15
        elif current['volume'] > vol_ma20:
            score += 10

        # 4. RSI (15점)
        rsi = self.calculate_rsi(df)
        if 55 < rsi < 70:
            score += 15
        elif 50 < rsi < 75:
            score += 10
        elif rsi < 40:
            score -= 20

        return score


    def calculate_rsi(self, df, period=14):
        """RSI 계산"""
        if len(df) < period + 1:
            return 50

        prices = df['close'].values[-period-1:]
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


    def calculate_atr(self, df, period=14):
        """ATR 계산"""
        if len(df) < period + 1:
            return df.iloc[-1]['high'] - df.iloc[-1]['low']

        tr_list = []
        for i in range(-period, 0):
            high = df.iloc[i]['high']
            low = df.iloc[i]['low']
            prev_close = df.iloc[i-1]['close']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)

        return np.mean(tr_list)


    def execute_strategy(self, coin):
        """
        코인별 전략 실행

        핵심 로직:
        1. 4시간봉 데이터 조회
        2. 모멘텀 스코어 계산
        3. Layer별 진입/청산 판단
        4. 주문 실행
        """
        market = f'KRW-{coin}'

        # 4시간봉 데이터 (500개)
        df = pyupbit.get_ohlcv(market, interval='minute240', count=500)

        if df is None or len(df) < 200:
            print(f"⚠️ {coin}: 데이터 부족")
            return

        current_price = df.iloc[-1]['close']
        score = self.calculate_momentum_score(df)

        print(f"\n{'='*60}")
        print(f"🪙 {coin} 분석")
        print(f"{'='*60}")
        print(f"현재가: {current_price:,.0f}원")
        print(f"모멘텀 스코어: {score}점")

        # Layer별 실행
        self.execute_buy_hold(coin, market, df)
        self.execute_momentum_trend(coin, market, df, score)
        self.execute_momentum_swing(coin, market, df, score)
        self.execute_volatility(coin, market, df)


    def execute_buy_hold(self, coin, market, df):
        """
        Buy & Hold Layer (60%)

        전략:
        - 최초 1회 매수
        - 절대 매도 안 함
        - 가장 안정적인 기반
        """
        pos = self.positions[coin]['buy_hold']

        # 포지션 없으면 매수
        if pos is None:
            # 해당 코인 배분 자본의 60%
            target_amount = self.initial_balance * self.coin_allocation[coin] * 0.60

            # 현재 KRW 잔고
            krw_balance = self.upbit.get_balance('KRW')

            if krw_balance >= target_amount:
                # 매수
                order = self.upbit.buy_market_order(market, target_amount * 0.9995)  # 수수료 고려

                if order:
                    self.positions[coin]['buy_hold'] = {
                        'entry_price': df.iloc[-1]['close'],
                        'entry_time': str(datetime.now()),
                        'layer': 'buy_hold'
                    }
                    self.save_positions()
                    msg = f"✅ <b>BUY & HOLD 매수</b>\n\n🪙 {coin}\n💰 {target_amount:,.0f}원\n📊 가격: {df.iloc[-1]['close']:,.0f}원"
                    print(f"✅ BUY & HOLD 매수: {target_amount:,.0f}원")
                    self.telegram.send(msg)


    def execute_momentum_trend(self, coin, market, df, score):
        """
        Momentum Trend Layer (25%)

        전략:
        - 스코어 80점 이상: 진입
        - 스코어 50점 이하: 청산
        - 손절: 20일 저점 -2%
        """
        pos = self.positions[coin]['momentum_trend']
        current_price = df.iloc[-1]['close']

        # 진입
        if pos is None and score >= 80:
            target_amount = self.initial_balance * self.coin_allocation[coin] * 0.25
            krw_balance = self.upbit.get_balance('KRW')

            if krw_balance >= target_amount:
                # 손절가 계산
                recent_low = df['low'].iloc[-20:].min()
                stop_loss = recent_low * 0.98

                order = self.upbit.buy_market_order(market, target_amount * 0.9995)

                if order:
                    self.positions[coin]['momentum_trend'] = {
                        'entry_price': current_price,
                        'entry_time': str(datetime.now()),
                        'stop_loss': stop_loss,
                        'entry_score': score,
                        'layer': 'momentum_trend'
                    }
                    self.save_positions()
                    msg = f"✅ <b>MOMENTUM TREND 매수</b>\n\n🪙 {coin}\n💰 {target_amount:,.0f}원\n📊 가격: {current_price:,.0f}원\n⭐ 스코어: {score}점\n🛑 손절: {stop_loss:,.0f}원"
                    print(f"✅ MOMENTUM TREND 매수: {target_amount:,.0f}원 (스코어: {score})")
                    self.telegram.send(msg)

        # 청산
        elif pos is not None:
            should_exit = (score <= 50) or (current_price <= pos['stop_loss'])

            if should_exit:
                # 보유 수량 조회
                balance = self.upbit.get_balance(coin)

                if balance and balance > 0:
                    order = self.upbit.sell_market_order(market, balance)

                    if order:
                        profit_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                        reason = "손절" if current_price <= pos['stop_loss'] else f"스코어 {score}점"
                        msg = f"💰 <b>MOMENTUM TREND 매도</b>\n\n🪙 {coin}\n📊 가격: {current_price:,.0f}원\n📈 수익률: {profit_pct:+.2f}%\n💡 이유: {reason}"
                        print(f"✅ MOMENTUM TREND 매도: 수익률 {profit_pct:+.2f}%")
                        self.telegram.send(msg)

                        self.positions[coin]['momentum_trend'] = None
                        self.save_positions()

            # 트레일링 손절
            elif current_price > pos['entry_price'] * 1.05:
                new_stop = max(pos['stop_loss'], pos['entry_price'] * 1.02)
                self.positions[coin]['momentum_trend']['stop_loss'] = new_stop
                self.save_positions()


    def execute_momentum_swing(self, coin, market, df, score):
        """
        Momentum Swing Layer (10%)

        전략:
        - 스코어 60-80점: 진입
        - 스코어 45점 이하 or +15% 익절: 청산
        """
        pos = self.positions[coin]['momentum_swing']
        current_price = df.iloc[-1]['close']

        # 진입
        if pos is None and 60 <= score < 80:
            target_amount = self.initial_balance * self.coin_allocation[coin] * 0.10
            krw_balance = self.upbit.get_balance('KRW')

            if krw_balance >= target_amount:
                recent_low = df['low'].iloc[-10:].min()
                stop_loss = recent_low * 0.97

                order = self.upbit.buy_market_order(market, target_amount * 0.9995)

                if order:
                    self.positions[coin]['momentum_swing'] = {
                        'entry_price': current_price,
                        'entry_time': str(datetime.now()),
                        'stop_loss': stop_loss,
                        'layer': 'momentum_swing'
                    }
                    self.save_positions()
                    msg = f"✅ <b>MOMENTUM SWING 매수</b>\n\n🪙 {coin}\n💰 {target_amount:,.0f}원\n📊 가격: {current_price:,.0f}원\n⭐ 스코어: {score}점"
                    print(f"✅ MOMENTUM SWING 매수: {target_amount:,.0f}원")
                    self.telegram.send(msg)

        # 청산
        elif pos is not None:
            should_exit = (score <= 45) or (current_price <= pos['stop_loss'])
            profit_target = current_price >= pos['entry_price'] * 1.15

            if should_exit or profit_target:
                balance = self.upbit.get_balance(coin)

                if balance and balance > 0:
                    order = self.upbit.sell_market_order(market, balance)

                    if order:
                        profit_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                        if profit_target:
                            reason = "익절 +15%"
                        elif current_price <= pos['stop_loss']:
                            reason = "손절"
                        else:
                            reason = f"스코어 {score}점"
                        msg = f"💰 <b>MOMENTUM SWING 매도</b>\n\n🪙 {coin}\n📊 가격: {current_price:,.0f}원\n📈 수익률: {profit_pct:+.2f}%\n💡 이유: {reason}"
                        print(f"✅ MOMENTUM SWING 매도: 수익률 {profit_pct:+.2f}%")
                        self.telegram.send(msg)

                        self.positions[coin]['momentum_swing'] = None
                        self.save_positions()


    def execute_volatility(self, coin, market, df):
        """
        Volatility Breakout Layer (5%)

        전략:
        - 14일 고점 돌파 + 거래량 급증
        - 손절: -1.5 ATR
        - 익절: +3 ATR
        """
        pos = self.positions[coin]['volatility']
        current_price = df.iloc[-1]['close']

        # 진입
        if pos is None:
            high_14 = df['high'].iloc[-14:-1].max()
            vol_ma20 = df['volume'].iloc[-20:].mean()
            volume_surge = df.iloc[-1]['volume'] > vol_ma20 * 1.3

            if current_price > high_14 and volume_surge:
                target_amount = self.initial_balance * self.coin_allocation[coin] * 0.05
                krw_balance = self.upbit.get_balance('KRW')

                if krw_balance >= target_amount:
                    atr = self.calculate_atr(df)

                    order = self.upbit.buy_market_order(market, target_amount * 0.9995)

                    if order:
                        self.positions[coin]['volatility'] = {
                            'entry_price': current_price,
                            'entry_time': str(datetime.now()),
                            'stop_loss': current_price - atr * 1.5,
                            'target': current_price + atr * 3,
                            'layer': 'volatility'
                        }
                        self.save_positions()
                        msg = f"✅ <b>VOLATILITY 매수</b>\n\n🪙 {coin}\n💰 {target_amount:,.0f}원\n📊 가격: {current_price:,.0f}원\n🎯 목표: {current_price + atr * 3:,.0f}원"
                        print(f"✅ VOLATILITY 매수: {target_amount:,.0f}원")
                        self.telegram.send(msg)

        # 청산
        elif pos is not None:
            if current_price >= pos['target'] or current_price <= pos['stop_loss']:
                balance = self.upbit.get_balance(coin)

                if balance and balance > 0:
                    order = self.upbit.sell_market_order(market, balance)

                    if order:
                        profit_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                        reason = '익절 목표달성' if current_price >= pos['target'] else '손절'
                        msg = f"💰 <b>VOLATILITY 매도</b>\n\n🪙 {coin}\n📊 가격: {current_price:,.0f}원\n📈 수익률: {profit_pct:+.2f}%\n💡 이유: {reason}"
                        print(f"✅ VOLATILITY 매도: 수익률 {profit_pct:+.2f}% ({reason})")
                        self.telegram.send(msg)

                        self.positions[coin]['volatility'] = None
                        self.save_positions()


    def rebalance(self):
        """
        동적 리밸런싱 (월 1회)

        핵심:
        - 각 코인이 목표 비중(20%)에서 벗어나면 조정
        - 우수 코인에서 이익 실현
        - 저조 코인에 재투자
        """
        print("\n" + "="*80)
        print("📊 리밸런싱 실행")
        print("="*80)

        # 현재 총 자산
        total_balance = self.get_total_balance()
        print(f"현재 총 자산: {total_balance:,.0f}원")

        # 각 코인의 현재 비중 계산
        for coin in self.coins:
            market = f'KRW-{coin}'
            balance = self.upbit.get_balance(coin)
            price = pyupbit.get_current_price(market)

            if balance and price:
                current_value = balance * price
                current_weight = current_value / total_balance
                target_weight = self.coin_allocation[coin]

                print(f"{coin}: 현재 {current_weight*100:.1f}% → 목표 {target_weight*100:.1f}%")

                # 5% 이상 차이나면 조정
                if abs(current_weight - target_weight) > 0.05:
                    diff = target_weight - current_weight
                    adjust_amount = total_balance * abs(diff)

                    if diff > 0:  # 매수 필요
                        krw = self.upbit.get_balance('KRW')
                        if krw >= adjust_amount:
                            self.upbit.buy_market_order(market, adjust_amount * 0.9995)
                            print(f"  → {adjust_amount:,.0f}원 매수")
                    else:  # 매도 필요
                        sell_amount = adjust_amount / price
                        if balance >= sell_amount:
                            self.upbit.sell_market_order(market, sell_amount)
                            print(f"  → {adjust_amount:,.0f}원 매도")

        self.last_rebalance = datetime.now()
        print("✅ 리밸런싱 완료\n")


    def run(self):
        """
        봇 메인 루프

        실행 주기:
        - 전략 체크: 4시간마다
        - 리밸런싱: 월 1회
        """
        print("\n" + "="*80)
        print("🚀 자동매매 봇 시작")
        print("="*80)
        print(f"거래 코인: {', '.join(self.coins)}")
        print(f"체크 주기: 4시간")
        print("="*80 + "\n")

        while True:
            try:
                # 텔레그램 명령어 체크
                cmd = self.telegram.check_commands()
                if cmd == 'stop':
                    self.telegram.send("🛑 <b>봇 중지 요청됨</b>\n\n봇을 종료합니다.")
                    break
                elif cmd == '/status':
                    total = self.get_total_balance()
                    profit = total - self.initial_balance
                    profit_pct = (profit / self.initial_balance) * 100
                    status_msg = (
                        f"📊 <b>봇 상태</b>\n\n"
                        f"💰 총 자산: {total:,.0f}원\n"
                        f"📈 수익: {profit:+,.0f}원 ({profit_pct:+.2f}%)\n"
                        f"🪙 거래 코인: {', '.join(self.coins)}\n"
                        f"⏰ 체크 주기: 4시간"
                    )
                    self.telegram.send(status_msg)

                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                # 각 코인별 전략 실행
                for coin in self.coins:
                    self.execute_strategy(coin)
                    time.sleep(1)  # API 제한

                # 리밸런싱 체크 (월 1회)
                if self.last_rebalance is None or \
                   (datetime.now() - self.last_rebalance).days >= 30:
                    self.rebalance()
                    self.telegram.send("📊 <b>월간 리밸런싱 완료</b>\n\n각 코인 비중이 20%로 조정되었습니다.")

                # 현재 총 자산 출력
                total = self.get_total_balance()
                profit = total - self.initial_balance
                profit_pct = (profit / self.initial_balance) * 100

                print(f"\n{'='*80}")
                print(f"💰 현재 총 자산: {total:,.0f}원")
                print(f"📈 수익: {profit:+,.0f}원 ({profit_pct:+.2f}%)")
                print(f"{'='*80}\n")

                # 일일 리포트 텔레그램 전송
                report_msg = (
                    f"📊 <b>일일 리포트</b>\n\n"
                    f"💰 총 자산: {total:,.0f}원\n"
                    f"📈 수익: {profit:+,.0f}원 ({profit_pct:+.2f}%)\n"
                    f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                self.telegram.send(report_msg)

                # 4시간 대기
                print("😴 다음 체크까지 4시간 대기...")
                time.sleep(4 * 60 * 60)  # 4시간

            except Exception as e:
                print(f"❌ 오류 발생: {e}")
                import traceback
                traceback.print_exc()
                print("⏱️ 10분 후 재시도...")
                time.sleep(600)


def main():
    """메인 함수"""
    print("="*80)
    print("🤖 실전 자동매매 봇 설정")
    print("="*80)

    # 환경변수에서 API 키 읽기 (Docker 환경)
    access_key = os.getenv('UPBIT_ACCESS_KEY')
    secret_key = os.getenv('UPBIT_SECRET_KEY')

    # 환경변수가 없으면 대화형으로 입력받기 (로컬 실행)
    if not access_key or not secret_key:
        print("\n⚠️ 환경변수가 설정되지 않았습니다.")
        print("대화형 모드로 전환합니다.\n")
        access_key = input("Access Key: ").strip()
        secret_key = input("Secret Key: ").strip()

        if not access_key or not secret_key:
            print("❌ API 키를 입력하세요.")
            return

    # 봇 생성
    bot = LiveTradingBot(access_key, secret_key)

    # 확인
    print(f"\n현재 총 자산: {bot.get_total_balance():,.0f}원")
    print(f"초기 자본으로 설정: {bot.initial_balance:,.0f}원")

    # Docker 환경이면 자동 시작, 로컬이면 확인 후 시작
    if os.getenv('UPBIT_ACCESS_KEY'):
        print("\n🚀 Docker 환경 감지 - 자동 시작")
        bot.run()
    else:
        confirm = input("\n봇을 시작하시겠습니까? (yes/no): ").strip().lower()
        if confirm == 'yes':
            bot.run()
        else:
            print("❌ 봇 시작 취소")


if __name__ == "__main__":
    main()
