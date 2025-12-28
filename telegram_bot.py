import os
import time
import requests
from datetime import datetime, timedelta
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators
from market_scanner import MarketScanner
from advanced_features import TimeBasedStrategy, AdvancedRiskManager
from database_manager import DatabaseManager
from market_regime import MarketRegimeDetector  # Tier 3 개선
from execution_manager import ExecutionManager  # Phase 1: 주문 실행 최적화
from risk_manager import RiskManager  # Phase 1: VaR 리스크 관리
from volatility_strategy import VolatilityScalpingStrategy  # 변동성 스캘핑
from ma_crossover_strategy import MACrossoverStrategy  # MA 크로스오버
from concurrent.futures import ThreadPoolExecutor



class TelegramBot:
    """텔레그램 봇"""
    
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, text):
        """메시지 전송"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            response = requests.post(url, data=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"텔레그램 전송 실패: {e}")
            return None
    
    def get_updates(self, offset=None):
        """메시지 가져오기"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"timeout": 1, "offset": offset}
            response = requests.get(url, params=params, timeout=5)
            return response.json()
        except Exception as e:
            return None


class TradingBot:
    """자동매매 봇"""
    
    def __init__(self, upbit, telegram, market="KRW-ETH", dry_run=False, signal_timeframe=1,
                 enable_multi_coin=False, db=None):
        self.upbit = upbit
        self.telegram = telegram
        self.market = market
        self.dry_run = dry_run  # 시뮬레이션 모드
        self.signal_timeframe = signal_timeframe  # 신호 타임프레임 (1, 5, 15, 60분)
        self.enable_multi_coin = enable_multi_coin  # 멀티 코인 모드
        self.db = db  # 데이터베이스 매니저 (선택적)

        # 전략 파라미터 (다층 익절 시스템) - 실전 최적화
        self.rsi_buy = 42            # 30 → 35 → 42 (실전 최적화: 더 자주 매수)
        self.rsi_sell = 70           # 70 유지

        # 다층 익절 전략 (빠른 수익 실현) - 기본값
        self.quick_profit = 0.008    # 0.8% 퀵 익절 (30분 이내)
        self.take_profit_1 = 0.015   # 1.5% 1차 익절
        self.take_profit_2 = 0.025   # 2.5% 2차 익절
        self.take_profit_3 = 0.04    # 4.0% 최종 익절

        self.stop_loss = -0.015      # -2% → -1.5% (더 빠른 손절, 기본값)

        # Tier 2 개선: 적응형 손절 (변동성 기반)
        self.adaptive_stop_loss = True  # 적응형 손절 활성화
        self.stop_loss_min = -0.008     # 최소 손절: -0.8% (저변동성)
        self.stop_loss_max = -0.015     # 최대 손절: -1.5% (고변동성)

        # Tier 2 개선: 시간 기반 익절 완화
        self.time_based_profit_relaxation = True  # 시간 기반 익절 완화 활성화
        self.relaxation_time_minutes = 30         # 30분 이후 완화
        self.profit_relaxation_amount = 0.003     # -0.3%p 완화

        # 부분 익절 전략 (Tier 1 개선)
        self.enable_partial_sell = True  # 부분 익절 활성화
        self.partial_sell_ratios = [
            (0.015, 0.50),  # 1.5% 도달 시 50% 매도
            (0.025, 0.30),  # 2.5% 도달 시 30% 매도 (남은 것의)
            (0.040, 0.20),  # 4.0% 도달 시 20% 매도 (남은 것의)
        ]

        # 동적 트레일링 스톱
        self.trailing_stop_tight = 0.003   # 0.3% 수익 이후 -0.3% 트레일링
        self.trailing_stop_medium = 0.005  # 0.8% 수익 이후 -0.5% 트레일링
        self.trailing_stop_wide = 0.008    # 1.5% 수익 이후 -0.8% 트레일링

        # 포지션 타임아웃
        self.position_timeout_hours = 3    # 3시간 이후 강제 청산 검토

        self.bb_period = 20
        self.bb_std = 2
        self.volume_threshold = 1.2  # 1.3 → 1.2 (더욱 완화)

        # DB에서 최적 파라미터 로드
        self.load_optimized_parameters()

        # 멀티 코인 설정
        self.market_scanner = MarketScanner(upbit) if enable_multi_coin else None
        self.coin_switch_score_diff = 20  # 코인 전환 최소 점수 차이
        self.last_coin_scan = None

        # Tier 3 개선: 시장 상태 감지
        self.market_regime_detector = MarketRegimeDetector(upbit)
        self.use_market_regime = True  # 시장 상태 기반 조정 활성화

        # Phase 1: 기관급 실행 및 리스크 관리
        self.execution_manager = ExecutionManager(upbit)
        self.risk_manager = RiskManager(upbit)
        self.enable_limit_orders = True  # 지정가 주문 활성화
        self.limit_order_strategy = 'mid'  # 'best', 'mid', 'aggressive'

        # 전략 우선순위 (위에서 아래 순서)
        # 1순위: MA 크로스오버 (가장 신뢰도 높음)
        self.ma_strategy = MACrossoverStrategy(fast_period=7, slow_period=25)
        self.enable_ma_crossover = True

        # 2순위: 변동성 스캘핑
        self.scalping_strategy = VolatilityScalpingStrategy()
        self.enable_scalping = True

        # 상태 (멀티 코인 지원)
        self.positions = {}  # {market: {buy_price, buy_time, amount, ...}}
        self.position_peaks = {}  # {market: peak_profit}
        self.position_lows = {}  # {market: lowest_profit}

        # 멀티 코인 설정
        self.max_positions = 3  # 최대 3개 코인 동시 보유
        self.position_size_per_coin = 0.3  # 코인당 30%

        # 레거시 호환 (기존 코드용)
        self.position = None  # 메인 코인 포지션 (하위 호환)

        self.trade_history = []
        self.is_running = True
        self.error_count = 0
        self.last_daily_report = None
        self.position_peak_profit = 0
        self.position_lowest_profit = 0
        self.last_update_id = None
        # 리소스 최적화: Always Free Tier (1 OCPU)에 맞게 조정
        self.executor = ThreadPoolExecutor(max_workers=1)

        # 일일 손실 제한 (Tier 1 개선)
        self.max_daily_loss = -0.03  # -3%
        self.daily_pnl = 0
        self.daily_pnl_reset_date = datetime.now().date()
        self.trading_paused = False
        self.consecutive_losses = 0  # 연속 손실 카운트

        # 동적 스캔 빈도 (Tier 1 개선)
        self.base_check_interval = 300  # 기본 5분
        self.current_check_interval = 300
        self.last_atr_check = None

        # Tier 4 개선: 실시간 파라미터 최적화
        self.auto_optimize = True  # 자동 최적화 활성화
        self.last_optimization_date = None  # 마지막 최적화 날짜
        self.optimization_interval_days = 7  # 7일마다 재최적화

        # 리소스 최적화: 신호 캐싱 (1 OCPU VM 대응)
        self.signal_cache = {}  # {timeframe: (timestamp, signals)}
        self.signal_cache_duration = 10  # 10초간 캐시 유지 (1분봉 대응)

        # 드라이런 모드용 가상 잔고
        if self.dry_run:
            self.virtual_krw = 1000000  # 100만원
            self.virtual_coin = 0
            self.virtual_avg_price = 0

    def load_optimized_parameters(self):
        """데이터베이스에서 최적화된 파라미터 로드"""
        if not self.db:
            return

        try:
            params = self.db.get_active_parameters(self.market)

            if params:
                self.quick_profit = params['quick_profit']
                self.take_profit_1 = params['take_profit_1']
                self.take_profit_2 = params.get('take_profit_2', 0.025)
                self.stop_loss = params['stop_loss']
                self.trailing_stop_tight = params['trailing_stop_tight']
                self.trailing_stop_medium = params.get('trailing_stop_medium', 0.005)
                self.trailing_stop_wide = params.get('trailing_stop_wide', 0.008)

                print(f"✅ DB에서 최적 파라미터 로드 완료 ({self.market})")
                print(f"   최적화 일자: {params['last_optimized']}")
                print(f"   퀵익절: {self.quick_profit*100:.1f}%")
                print(f"   1차익절: {self.take_profit_1*100:.1f}%")
                print(f"   손절: {self.stop_loss*100:.1f}%")
            else:
                print(f"ℹ️  {self.market} 최적화 데이터 없음, 기본 파라미터 사용")

        except Exception as e:
            print(f"⚠️ 파라미터 로드 실패, 기본값 사용: {e}")

    def save_trade_to_db(self, trade_data):
        """거래 기록을 데이터베이스에 저장"""
        if not self.db:
            return

        try:
            self.db.save_trade(trade_data)
            print(f"✅ 거래 기록 DB 저장 완료")
        except Exception as e:
            print(f"⚠️ 거래 기록 저장 실패: {e}")

    def get_current_status(self):
        """현재 계좌 및 시장 상태"""
        # 드라이런 모드
        if self.dry_run:
            ticker = self.upbit.get_current_price(self.market)
            current_price = ticker['trade_price']
            change_24h = ticker.get('signed_change_rate', 0) * 100

            return {
                'krw': self.virtual_krw,
                'coin': self.virtual_coin,
                'avg_price': self.virtual_avg_price,
                'current_price': current_price,
                'coin_value': self.virtual_coin * current_price,
                'total': self.virtual_krw + (self.virtual_coin * current_price),
                'change_24h': change_24h
            }

        # 실제 모드
        accounts = self.upbit.get_accounts()

        krw = 0
        coin = 0
        avg_price = 0

        for acc in accounts:
            if acc['currency'] == 'KRW':
                krw = float(acc['balance'])
            elif acc['currency'] == self.market.split('-')[1]:
                coin = float(acc['balance'])
                avg_price = float(acc['avg_buy_price'])

        ticker = self.upbit.get_current_price(self.market)
        current_price = ticker['trade_price']
        change_24h = ticker.get('signed_change_rate', 0) * 100

        return {
            'krw': krw,
            'coin': coin,
            'avg_price': avg_price,
            'current_price': current_price,
            'coin_value': coin * current_price,
            'total': krw + (coin * current_price),
            'change_24h': change_24h
        }

    def get_trend_analysis(self):
        """다중 시간대 추세 분석 (1H + 4H)"""
        try:
            # 1시간봉 200개 (약 8일치)
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 200)
            # 4시간봉 200개 (약 33일치)
            candles_4h = self.upbit.get_candles(self.market, "minutes", 240, 200)

            if len(candles_1h) < 50 or len(candles_4h) < 50:
                return None

            # 1시간 추세
            prices_1h = [c['trade_price'] for c in candles_1h]
            rsi_1h = TechnicalIndicators.calculate_rsi(prices_1h, 14)
            ma20_1h = sum(prices_1h[:20]) / 20
            ma50_1h = sum(prices_1h[:50]) / 50
            trend_1h = "up" if ma20_1h > ma50_1h and prices_1h[0] > ma20_1h else "down"

            # 4시간 추세
            prices_4h = [c['trade_price'] for c in candles_4h]
            rsi_4h = TechnicalIndicators.calculate_rsi(prices_4h, 14)
            ma20_4h = sum(prices_4h[:20]) / 20
            ma50_4h = sum(prices_4h[:50]) / 50
            trend_4h = "up" if ma20_4h > ma50_4h and prices_4h[0] > ma20_4h else "down"

            # 추세 상태 판단 (RSI 기준 완화)
            if trend_1h == "up" and trend_4h == "up":
                trend_state = "strong_bull"  # 강한 상승
                buy_allowed = True
                rsi_threshold = 50  # 40 → 50
            elif trend_1h == "down" and trend_4h == "up":
                trend_state = "correction"   # 조정 (상승장 내 조정)
                buy_allowed = True
                rsi_threshold = 45  # 35 → 45
            elif trend_1h == "up" and trend_4h == "down":
                trend_state = "weak_bounce"  # 약한 반등
                buy_allowed = True
                rsi_threshold = 40  # 30 → 40
            else:  # trend_1h == "down" and trend_4h == "down"
                trend_state = "strong_bear"  # 강한 하락
                buy_allowed = True  # False → True (하락장에서도 매수)
                rsi_threshold = 30  # 25 → 30

            return {
                'trend_1h': trend_1h,
                'trend_4h': trend_4h,
                'rsi_1h': rsi_1h,
                'rsi_4h': rsi_4h,
                'trend_state': trend_state,
                'buy_allowed': buy_allowed,
                'rsi_threshold': rsi_threshold,
                'ma20_1h': ma20_1h,
                'ma50_1h': ma50_1h,
                'ma20_4h': ma20_4h,
                'ma50_4h': ma50_4h
            }

        except Exception as e:
            self.log(f"추세 분석 실패: {e}")
            return None
    
    def get_signals(self, timeframe=15):
        """시장 분석 및 신호 (다중 시간대 포함, Tier 1 개선: 스마트 볼륨 필터)

        리소스 최적화: 캐싱으로 불필요한 API 호출 감소

        Args:
            timeframe: 5, 15, 60 등 (분 단위)
        """
        # 캐시 확인 (리소스 최적화)
        now = datetime.now()
        cache_key = f"{self.market}_{timeframe}"
        if cache_key in self.signal_cache:
            cached_time, cached_signals = self.signal_cache[cache_key]
            if (now - cached_time).total_seconds() < self.signal_cache_duration:
                return cached_signals

        candles = self.upbit.get_candles(self.market, "minutes", timeframe, 50)
        if len(candles) < 50:
            return None

        prices = [c['trade_price'] for c in candles]
        volumes = [c['candle_acc_trade_volume'] for c in candles]

        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        upper, middle, lower = AdvancedIndicators.calculate_bollinger_bands(prices, 20, 2)
        vol_ma = AdvancedIndicators.calculate_volume_ma(volumes, 20)

        if not all([rsi, upper, lower, vol_ma]):
            return None

        current_price = prices[0]
        current_vol = volumes[0]
        bb_pos = ((current_price - lower) / (upper - lower)) * 100
        vol_ratio = current_vol / vol_ma

        # 다중 시간대 추세 분석
        trend = self.get_trend_analysis()

        # === 스마트 볼륨 필터 (실전 최적화 - 거래량 대폭 완화) ===
        # 시간대별 동적 임계값 (거래량 조건 대폭 완화)
        if timeframe == 1:
            base_vol_threshold = 0.3  # 1분봉: 1.2 → 0.3 (매우 완화)
        elif timeframe == 5:
            base_vol_threshold = 0.3  # 5분봉: 1.0 → 0.3 (매우 완화)
        elif timeframe == 15:
            base_vol_threshold = 0.3  # 15분봉: 0.95 → 0.3 (매우 완화)
        else:
            base_vol_threshold = 0.3  # 더 긴 시간대: 0.9 → 0.3 (매우 완화)

        # 추세 강할 때 더욱 완화 (0.5배)
        if trend and trend['trend_state'] in ['strong_bull', 'correction']:
            vol_threshold = base_vol_threshold * 0.5  # 0.15배까지 허용
        else:
            vol_threshold = base_vol_threshold

        # 거래량 조건 체크
        volume_ok = vol_ratio >= vol_threshold

        # 매수 조건 (실전 최적화: 거래량 조건 제거, RSI+볼린저만 사용)
        buy_signal = False
        if trend and trend['buy_allowed']:
            rsi_threshold = trend['rsi_threshold']

            # 추세별 조건 (실전 최적화: 거래량 조건 완전 제거)
            if trend['trend_state'] == 'strong_bull':
                # 강한 상승: RSI만
                buy_signal = (rsi < rsi_threshold)
            elif trend['trend_state'] == 'correction':
                # 조정: RSI + 볼린저 완화
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.20)
            elif trend['trend_state'] == 'weak_bounce':
                # 약한 반등: RSI + 볼린저 완화 (거래량 조건 제거)
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.15)
            elif trend['trend_state'] == 'strong_bear':
                # 강한 하락: 과매도 + 볼린저 완화 (거래량 조건 제거)
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.10)
        else:
            # 추세 분석 실패: 과매도 + 볼린저 완화
            buy_signal = (rsi < 35 and current_price <= lower * 1.10)

        signals = {
            'price': current_price,
            'rsi': rsi,
            'upper': upper,
            'lower': lower,
            'bb_pos': bb_pos,
            'vol_ratio': vol_ratio,
            'vol_threshold': vol_threshold,  # 현재 적용된 임계값
            'volume_ok': volume_ok,  # 볼륨 조건 충족 여부
            'trend': trend,
            'buy': buy_signal,
            'sell': rsi > self.rsi_sell and current_price >= upper * 0.99
        }

        # 캐시 저장 (리소스 최적화)
        self.signal_cache[cache_key] = (now, signals)

        return signals

    # === 멀티 코인 포지션 관리 헬퍼 함수 ===

    def can_add_position(self):
        """새로운 포지션 추가 가능 여부"""
        return len(self.positions) < self.max_positions

    def get_available_position_size(self, status):
        """새 포지션에 사용 가능한 금액 (총 자산의 30%)"""
        total_asset = status['total']
        return int(total_asset * self.position_size_per_coin)

    def add_position(self, market, position_data):
        """포지션 추가"""
        self.positions[market] = position_data
        self.position_peaks[market] = 0
        self.position_lows[market] = 0

        # 레거시 호환: 첫 포지션은 self.position에도 저장
        if len(self.positions) == 1:
            self.position = position_data

    def remove_position(self, market):
        """포지션 제거"""
        if market in self.positions:
            del self.positions[market]
            if market in self.position_peaks:
                del self.position_peaks[market]
            if market in self.position_lows:
                del self.position_lows[market]

            # 레거시 호환: 포지션이 하나도 없으면 self.position = None
            if len(self.positions) == 0:
                self.position = None
            # 다른 포지션이 있으면 첫 번째 포지션을 self.position으로 설정
            elif self.position and self.position.get('market') == market:
                self.position = list(self.positions.values())[0] if self.positions else None

    def get_position_for_market(self, market):
        """특정 마켓의 포지션 조회"""
        return self.positions.get(market)

    def has_position_for_market(self, market):
        """특정 마켓의 포지션 보유 여부"""
        return market in self.positions

    def get_total_position_value(self, status):
        """전체 포지션 평가액"""
        total = 0
        for market, pos in self.positions.items():
            # 현재가 조회
            ticker = self.upbit.get_current_price(market)
            if ticker:
                current_price = ticker['trade_price']
                total += pos['amount'] * current_price
        return total

    def buy(self, status, signals, market=None):
        """매수 실행 (멀티 코인 지원)"""
        # 멀티 코인: market 파라미터 사용, 없으면 self.market 사용
        target_market = market or self.market

        # 이미 해당 코인 보유 중이면 스킵
        if self.has_position_for_market(target_market):
            self.log(f"⚠️ {target_market} 이미 보유 중")
            return False

        # 최대 포지션 개수 체크
        if not self.can_add_position():
            self.log(f"⚠️ 최대 포지션 개수 도달 ({len(self.positions)}/{self.max_positions})")
            return False

        krw = status['krw']
        if krw < 5000:
            return False

        try:
            price = signals['price']

            # === 시간대별 전략 체크 ===
            session = TimeBasedStrategy.get_trading_session()
            self.log(f"⏰ {session['name']} (공격성: {session['aggression']}, 변동성: {session['volatility']})")

            # === 포지션 사이징 (멀티 코인용) ===
            # 멀티 코인: 총 자산의 30%씩 배분
            position_krw = self.get_available_position_size(status)

            # 최소 금액 체크
            if position_krw < 5000:
                position_krw = min(krw, 5000)

            # === Phase 1: 리스크 한도 체크 (VaR) ===
            # 전체 포트폴리오 가치 = KRW + 보유 코인 가치
            total_portfolio_krw = status['total']  # KRW + 코인 평가액

            # 디버그 로그
            self.log(f"🔍 리스크 체크: 매수금액={position_krw:,.0f}원, 전체자산={total_portfolio_krw:,.0f}원, "
                    f"비율={position_krw/total_portfolio_krw*100:.1f}%")

            risk_check = self.risk_manager.check_risk_limits(position_krw, total_portfolio_krw, target_market)

            if not risk_check.get('approved'):
                self.log(f"⚠️ 리스크 한도 초과: {risk_check.get('reason')}")
                return False

            # === Phase 1: 슬리피지 추정 ===
            slippage_data = None
            execution_quality = ""
            if self.enable_limit_orders:
                slippage_data = self.execution_manager.estimate_slippage(target_market, 'buy', position_krw)
                if slippage_data:
                    execution_quality = f"\n📊 예상 슬리피지: {slippage_data['estimated_slippage']:.3f}%"
                    execution_quality += f"\n💡 {slippage_data['recommendation']}"

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                amount = position_krw / price
                self.virtual_coin = amount
                self.virtual_krw = krw - position_krw
                self.virtual_avg_price = price
                executed_price = price
            # 실제 주문
            else:
                # Phase 1: 지정가 주문 시도 (슬리피지가 클 경우)
                if self.enable_limit_orders and slippage_data and slippage_data['estimated_slippage'] > 0.10:
                    # 슬리피지 > 0.1%면 지정가 사용
                    order_result = self.execution_manager.execute_limit_order(
                        target_market, 'buy', position_krw,
                        price_strategy=self.limit_order_strategy,
                        max_wait_seconds=20
                    )

                    if order_result.get('success'):
                        executed_price = order_result['price']
                        amount = order_result['volume']
                        execution_quality += f"\n✅ 지정가 체결 ({order_result.get('execution_time', 0):.1f}초)"
                    else:
                        # 지정가 실패시 시장가 폴백 (이미 내부 처리됨)
                        executed_price = price
                        amount = position_krw / price
                else:
                    # 시장가 주문
                    result = self.upbit.order_market_buy(target_market, position_krw)
                    executed_price = price
                    amount = position_krw / price
                    execution_quality += "\n📍 시장가 체결"

            # 멀티 코인: 포지션 딕셔너리에 추가
            position_data = {
                'market': target_market,
                'buy_price': executed_price if not self.dry_run else price,
                'buy_time': datetime.now(),
                'amount': amount,
                'buy_krw': krw
            }
            self.add_position(target_market, position_data)
            
            self.trade_history.append({
                'type': 'BUY',
                'time': datetime.now(),
                'price': price,
                'amount': krw
            })
            
            trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
            trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}

            # 시장 상태 가져오기
            market_regime = None
            if self.use_market_regime and self.market_regime_detector.current_regime:
                market_regime = self.market_regime_detector.current_regime

            # 다중 시간대 신호 강도
            signal_strength = ""
            if 'buy_signal_count' in signals:
                count = signals['buy_signal_count']
                if count == 3:
                    signal_strength = "🔥 매우 강함"
                elif count == 2:
                    signal_strength = "✅ 강함"
                else:
                    signal_strength = "⚠️ 약함"

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}🔵 <b>매수 완료</b>\n"
            msg += f"{'='*30}\n\n"

            # 코인 정보
            msg += f"🪙 <b>{target_market.replace('KRW-', '')}</b>\n"
            msg += f"🎯 <b>보유 포지션: {len(self.positions)}/{self.max_positions}</b>\n"
            msg += f"💰 <b>{price:,.0f}원</b> × {amount:.6f}\n"
            msg += f"💵 투자금: <b>{position_krw:,.0f}원</b> ({position_krw/krw*100:.0f}% 사용)\n"
            msg += f"💼 잔액: {krw - position_krw:,.0f}원\n\n"

            # 시간 및 세션 정보
            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            msg += f"📅 {session['name']} (공격성: {session['aggression']}, 변동성: {session['volatility']})\n\n"

            # 시장 상태 (Tier 3)
            if market_regime:
                regime_emoji = {"bull": "🐂", "bear": "🐻", "sideways": "↔️"}
                msg += f"🌍 <b>시장 상태</b>\n"
                msg += f"  • {regime_emoji.get(market_regime['regime'])} {market_regime['regime'].upper()}"
                msg += f" (신뢰도: {market_regime['strength']:.0f}%)\n"
                msg += f"  • BTC 추세: {market_regime['btc_trend'].upper()}"
                msg += f" (RSI: {market_regime['btc_rsi_1h']:.1f})\n"
                msg += f"  • 시장 심리: {market_regime['market_sentiment']:.0f}%\n\n"

            # 매수 신호 강도 (Tier 2)
            if signal_strength and 'multi_timeframe' in signals:
                msg += f"📶 <b>신호 강도</b>: {signal_strength}\n"
                msg += f"  • 1분봉: {'✅' if signals['multi_timeframe']['1m']['buy'] else '❌'}\n"
                msg += f"  • 5분봉: {'✅' if signals['multi_timeframe']['5m']['buy'] else '❌'}\n"
                msg += f"  • 15분봉: {'✅' if signals['multi_timeframe']['15m']['buy'] else '❌'}\n\n"

            # 추세 분석
            if signals.get('trend'):
                trend = signals['trend']
                state = trend['trend_state']
                msg += f"📈 <b>추세 분석</b>\n"
                msg += f"  • 상태: {trend_emoji.get(state, '📊')} {trend_name.get(state, state)}\n"
                msg += f"  • 1H: {'🔼' if trend['trend_1h'] == 'up' else '🔽'} RSI {trend['rsi_1h']:.1f}"
                msg += f" (MA20: {trend['ma20_1h']:,.0f})\n"
                msg += f"  • 4H: {'🔼' if trend['trend_4h'] == 'up' else '🔽'} RSI {trend['rsi_4h']:.1f}"
                msg += f" (MA20: {trend['ma20_4h']:,.0f})\n\n"

            # 기술적 지표 (전체 시그널이 있을 때만)
            if 'bb_pos' in signals and 'vol_ratio' in signals:
                msg += f"📊 <b>기술적 지표</b>\n"
                msg += f"  • RSI(15m): {signals['rsi']:.1f}"
                msg += f" ({'과매도' if signals['rsi'] < 30 else '중립' if signals['rsi'] < 70 else '과매수'})\n"
                msg += f"  • 볼린저밴드: {signals['bb_pos']:.1f}%"
                msg += f" ({'하단' if signals['bb_pos'] < 20 else '중간' if signals['bb_pos'] < 80 else '상단'})\n"
                msg += f"  • 거래량: {signals['vol_ratio']:.2f}x"
                msg += f" (기준: {signals.get('vol_threshold', 1.2):.2f}x)"
                if signals.get('volume_ok'):
                    msg += " ✅\n"
                else:
                    msg += " ⚠️\n"
                msg += f"  • 가격: {price:,.0f}원\n"
                msg += f"  • 상한: {signals['upper']:,.0f}원 (+{((signals['upper']-price)/price)*100:.1f}%)\n"
                msg += f"  • 하한: {signals['lower']:,.0f}원 ({((signals['lower']-price)/price)*100:.1f}%)\n\n"

            # 익절 목표 (부분 익절 포함)
            msg += f"🎯 <b>익절 목표</b> (부분 익절 전략)\n"
            msg += f"  • ⚡ 퀵 (30분): {price * (1 + self.quick_profit):,.0f}원"
            msg += f" (+{self.quick_profit*100:.1f}%) → 100% 매도\n"
            msg += f"  • 🥉 1차: {price * (1 + self.take_profit_1):,.0f}원"
            msg += f" (+{self.take_profit_1*100:.1f}%) → 50% 매도\n"
            msg += f"  • 🥈 2차: {price * (1 + self.take_profit_2):,.0f}원"
            msg += f" (+{self.take_profit_2*100:.1f}%) → 30% 매도\n"
            msg += f"  • 🥇 최종: {price * (1 + self.take_profit_3):,.0f}원"
            msg += f" (+{self.take_profit_3*100:.0f}%) → 100% 매도\n\n"

            # 리스크 관리 (VaR 추가 - Phase 1)
            adaptive_sl = self.get_adaptive_stop_loss() if hasattr(self, 'get_adaptive_stop_loss') else self.stop_loss
            msg += f"🛡️ <b>리스크 관리</b>\n"
            msg += f"  • 손절: {price * (1 + adaptive_sl):,.0f}원"
            msg += f" ({adaptive_sl*100:.2f}%)"
            if self.adaptive_stop_loss:
                msg += " 📊 적응형\n"
            else:
                msg += "\n"
            msg += f"  • 트레일링 스톱:\n"
            msg += f"    - 0.3% 도달 → -0.3% 트레일링\n"
            msg += f"    - 0.8% 도달 → -0.5% 트레일링\n"
            msg += f"    - 1.5% 도달 → -0.8% 트레일링\n"
            msg += f"  • 타임아웃: {self.position_timeout_hours}시간\n"
            msg += f"  • 일일 손익: {self.daily_pnl*100:.2f}% (한도: {self.max_daily_loss*100:.0f}%)\n"

            # Phase 1: VaR 정보
            var_data = self.risk_manager.calculate_var(self.market, confidence_level=0.95)
            if var_data:
                msg += f"  • VaR(95%, 1일): -{var_data['var_1day']:.2f}% (최대 예상 손실)\n"
                msg += f"  • 변동성: {var_data['volatility']:.2f}%\n"
            msg += "\n"

            # Phase 1: 실행 품질
            if execution_quality:
                msg += f"⚡ <b>실행 품질</b>{execution_quality}\n\n"

            # 거래 통계
            if len(self.trade_history) > 1:
                recent_trades = self.trade_history[-10:]
                wins = sum(1 for t in recent_trades if t.get('profit', 0) > 0)
                win_rate = (wins / len(recent_trades)) * 100 if recent_trades else 0
                msg += f"📈 <b>최근 거래 성과</b> (최근 {len(recent_trades)}건)\n"
                msg += f"  • 승률: {win_rate:.0f}% ({wins}승 {len(recent_trades)-wins}패)\n\n"

            msg += f"{'='*30}"
            
            self.telegram.send_message(msg)
            self.log("✅ 매수 완료")
            return True
            
        except Exception as e:
            self.log(f"❌ 매수 실패: {e}")
            self.telegram.send_message(f"❌ 매수 실패: {e}")
            return False
    
    def sell(self, status, signals, reason, market=None):
        """매도 실행 (멀티 코인 지원)"""
        # 멀티 코인: market 파라미터 사용, 없으면 self.market 사용
        target_market = market or self.market

        # 해당 마켓의 포지션 조회
        position = self.get_position_for_market(target_market)
        if not position:
            return False

        # 현재 보유 수량 확인
        balances = self.upbit.get_balances()
        coin_balance = 0
        for balance in balances:
            if balance['currency'] == target_market.replace('KRW-', ''):
                coin_balance = float(balance['balance'])
                break

        if coin_balance < 0.001:
            self.remove_position(target_market)
            return False

        try:
            price = signals['price']
            buy_price = position['buy_price']
            profit_rate = (price - buy_price) / buy_price * 100

            hold_hours = (datetime.now() - position['buy_time']).total_seconds() / 3600

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                sell_krw = coin_balance * price
                profit = sell_krw - position['buy_krw']
                self.virtual_krw = sell_krw
                self.virtual_coin = 0
                self.virtual_avg_price = 0
            # 실제 주문
            else:
                self.upbit.order_market_sell(target_market, coin_balance)

            sell_krw = coin_balance * price
            profit = sell_krw - position['buy_krw']

            # 포지션의 peak/low 가져오기
            position_peak = self.position_peaks.get(target_market, 0)
            position_low = self.position_lows.get(target_market, 0)

            # 거래 기록 생성
            trade_record = {
                'market': target_market,
                'type': 'SELL',
                'time': datetime.now(),
                'price': price,
                'amount': coin_balance,
                'krw_amount': sell_krw,
                'profit': profit,
                'profit_rate': profit_rate / 100,  # DB에는 0.01 형식으로 저장
                'reason': reason,
                'hold_time_minutes': int(hold_hours * 60),
                'peak_profit': position_peak
            }

            self.trade_history.append(trade_record)

            # 데이터베이스에 저장
            self.save_trade_to_db(trade_record)

            # 수익 여부에 따른 이모지
            if profit > 0:
                emoji = "🟢"
                result_text = "익절 성공"
            else:
                emoji = "🔴"
                result_text = "손절 실행"

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}{emoji} <b>매도 완료 - {result_text}</b>\n"
            msg += f"{'='*30}\n\n"

            # 코인 및 거래 정보
            msg += f"🪙 <b>{target_market.replace('KRW-', '')}</b>\n"
            msg += f"🎯 <b>남은 포지션: {len(self.positions)-1}/{self.max_positions}</b>\n"
            msg += f"💰 매도가: <b>{price:,.0f}원</b>\n"
            msg += f"📈 매수가: {buy_price:,.0f}원\n"
            msg += f"📊 수량: {coin_balance:.6f}\n\n"

            # 수익 정보 (강조)
            profit_emoji = "💰" if profit > 0 else "💸"
            msg += f"{profit_emoji} <b>{'수익' if profit > 0 else '손실'}</b>\n"
            msg += f"  • 금액: <b>{profit:+,.0f}원</b>\n"
            msg += f"  • 수익률: <b>{profit_rate:+.2f}%</b>\n"
            if profit > 0:
                expected_amount = sell_krw + profit
                msg += f"  • 총 회수: {sell_krw:,.0f}원\n\n"
            else:
                msg += f"  • 총 회수: {sell_krw:,.0f}원\n\n"

            # 보유 기간 및 성과
            hold_days = int(hold_hours // 24)
            remaining_hours = hold_hours % 24
            msg += f"⏱️ <b>보유 기간</b>\n"
            if hold_days > 0:
                msg += f"  • {hold_days}일 {remaining_hours:.1f}시간\n"
            else:
                msg += f"  • {hold_hours:.1f}시간\n"
            msg += f"  • 최고 수익률: {position_peak*100:+.2f}%\n"
            msg += f"  • 최저 수익률: {position_low*100:+.2f}%\n"

            # 수익 포기 계산 (최고점 대비)
            if position_peak > 0:
                missed_profit = (position_peak - (profit_rate/100)) * 100
                if missed_profit > 0:
                    msg += f"  • 최고점 대비: -{missed_profit:.2f}%p ⬇️\n"
            msg += "\n"

            # 매도 사유
            msg += f"📝 <b>매도 사유</b>: {reason}\n\n"

            # 현재 시장 상태 (선택적)
            if 'rsi' in signals and 'bb_pos' in signals:
                msg += f"📊 <b>시장 정보</b>\n"
                msg += f"  • RSI: {signals['rsi']:.1f}"
                msg += f" ({'과매도' if signals['rsi'] < 30 else '중립' if signals['rsi'] < 70 else '과매수'})\n"
                msg += f"  • 가격 위치: {signals['bb_pos']:.0f}%"
                msg += f" ({'하단' if signals['bb_pos'] < 20 else '중간' if signals['bb_pos'] < 80 else '상단'})\n\n"

            # 일일 손익 업데이트
            projected_daily_pnl = (self.daily_pnl + (profit / 1000000)) * 100
            msg += f"📈 <b>일일 누적</b>\n"
            msg += f"  • 오늘 손익: {projected_daily_pnl:+.2f}%"
            if projected_daily_pnl > 0:
                msg += " 🔥\n"
            elif projected_daily_pnl < -2:
                msg += " ⚠️\n"
            else:
                msg += "\n"
            msg += f"  • 일일 한도: {self.max_daily_loss*100:.0f}%\n\n"

            # 최근 거래 성과
            recent_trades = [t for t in self.trade_history if t.get('type') == 'SELL'][-10:]
            if len(recent_trades) >= 3:
                wins = sum(1 for t in recent_trades if t.get('profit', 0) > 0)
                total_profit = sum(t.get('profit', 0) for t in recent_trades)
                avg_profit_rate = sum(t.get('profit_rate', 0) for t in recent_trades) / len(recent_trades) * 100
                win_rate = (wins / len(recent_trades)) * 100

                msg += f"📊 <b>최근 성과</b> (최근 {len(recent_trades)}건)\n"
                msg += f"  • 승률: {win_rate:.0f}% ({wins}승 {len(recent_trades)-wins}패)\n"
                msg += f"  • 평균 수익률: {avg_profit_rate:+.2f}%\n"
                msg += f"  • 누적 수익: {total_profit:+,.0f}원\n\n"

            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            msg += f"{'='*30}"
            
            self.telegram.send_message(msg)
            self.log(f"✅ {target_market} 매도 완료")

            # 멀티 코인: 해당 마켓의 포지션 제거
            self.remove_position(target_market)

            # 일일 손실 업데이트
            self.update_daily_pnl(profit)

            return True

        except Exception as e:
            self.log(f"❌ {target_market} 매도 실패: {e}")
            self.telegram.send_message(f"❌ {target_market} 매도 실패: {e}")
            return False

    def partial_sell(self, status, signals, ratio, reason):
        """부분 매도 실행 (Tier 1 개선)"""
        if not self.position:
            return False

        coin = status['coin']
        if coin < 0.001:
            return False

        try:
            price = signals['price']
            buy_price = self.position['buy_price']
            profit_rate = (price - buy_price) / buy_price * 100

            # 매도할 수량 계산
            sell_amount = coin * ratio

            # 너무 적은 양은 거래하지 않음
            if sell_amount < 0.001:
                return False

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                sell_krw = sell_amount * price
                self.virtual_coin -= sell_amount
                self.virtual_krw += sell_krw
            # 실제 주문
            else:
                self.upbit.order_market_sell(self.market, sell_amount)

            sell_krw = sell_amount * price
            profit = sell_krw - (self.position['buy_krw'] * ratio)

            # 포지션 업데이트
            self.position['sold_amount'] = self.position.get('sold_amount', 0) + sell_amount

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}📊 <b>부분 매도 ({ratio*100:.0f}%)</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 금액: {sell_krw:,.0f}원\n"
            msg += f"📊 가격: {price:,.0f}원\n"
            msg += f"📈 매수가: {buy_price:,.0f}원\n\n"
            msg += f"💵 <b>수익: {profit:+,.0f}원 ({profit_rate:+.2f}%)</b>\n\n"
            msg += f"📝 사유: {reason}\n"
            msg += f"💼 남은 포지션: {(1-ratio-self.position.get('sold_ratio', 0))*100:.0f}%\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"

            self.telegram.send_message(msg)
            self.log(f"✅ 부분 매도 완료 ({ratio*100:.0f}%)")

            # 판매 비율 누적
            self.position['sold_ratio'] = self.position.get('sold_ratio', 0) + ratio

            # 일일 손실 업데이트
            self.update_daily_pnl(profit)

            return True

        except Exception as e:
            self.log(f"❌ 부분 매도 실패: {e}")
            return False

    def update_daily_pnl(self, profit):
        """일일 손익 업데이트 (Tier 1 개선)"""
        # 날짜가 바뀌면 리셋
        today = datetime.now().date()
        if today != self.daily_pnl_reset_date:
            self.daily_pnl = 0
            self.daily_pnl_reset_date = today
            self.trading_paused = False
            self.consecutive_losses = 0
            self.log("📅 일일 손익 리셋")

        # 손익 업데이트 (전체 자산 대비 비율)
        status = self.get_current_status()
        total_asset = status['total']
        profit_rate = profit / total_asset if total_asset > 0 else 0
        self.daily_pnl += profit_rate

        # 연속 손실 추적
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # 일일 손실 제한 체크
        if self.daily_pnl <= self.max_daily_loss:
            self.trading_paused = True
            msg = f"⚠️ <b>일일 손실 제한 도달</b>\n\n"
            msg += f"오늘 손익: {self.daily_pnl*100:.2f}%\n"
            msg += f"제한: {self.max_daily_loss*100:.0f}%\n\n"
            msg += f"내일까지 거래가 중단됩니다."
            self.telegram.send_message(msg)
            self.log(f"⚠️ 거래 중단: 일일 손실 {self.daily_pnl*100:.2f}%")

    def get_adaptive_stop_loss(self):
        """적응형 손절 레벨 계산 (Tier 2 개선)

        변동성(ATR)에 따라 손절 레벨 동적 조정:
        - 저변동성: 타이트한 손절 (-0.8%)
        - 고변동성: 넓은 손절 (-1.5%)
        """
        if not self.adaptive_stop_loss:
            return self.stop_loss

        try:
            # ATR 계산 (1시간봉 기준)
            from advanced_features import VolatilityManager
            candles = self.upbit.get_candles(self.market, "minutes", 60, 30)

            if not candles or len(candles) < 14:
                return self.stop_loss  # 데이터 부족 시 기본값

            atr = VolatilityManager.calculate_atr(candles, period=14)
            current_price = candles[0]['trade_price']
            atr_percent = (atr / current_price) * 100

            # 변동성 기반 손절 레벨 결정
            if atr_percent < 2:
                # 저변동성: 타이트한 손절
                adaptive_stop = self.stop_loss_min
            elif atr_percent > 4:
                # 고변동성: 넓은 손절
                adaptive_stop = self.stop_loss_max
            else:
                # 중간: 선형 보간
                ratio = (atr_percent - 2) / (4 - 2)
                adaptive_stop = self.stop_loss_min + (self.stop_loss_max - self.stop_loss_min) * ratio

            self.log(f"🎯 적응형 손절: {adaptive_stop*100:.2f}% (ATR: {atr_percent:.2f}%)")
            return adaptive_stop

        except Exception as e:
            self.log(f"적응형 손절 계산 실패: {e}")
            return self.stop_loss

    def check_multi_coin_switch(self):
        """멀티 코인 모드: 더 나은 코인으로 전환 검토"""
        if not self.enable_multi_coin or not self.market_scanner:
            return False

        # 포지션 없을 때만 코인 변경 고려
        if self.position:
            return False

        # 1분봉 대응: 2분마다 스캔 (1분봉 2번 체크 후 재평가)
        now = datetime.now()
        if self.last_coin_scan and (now - self.last_coin_scan).total_seconds() < 120:
            return False

        self.last_coin_scan = now

        try:
            # 현재 모멘텀 랭킹 확인
            best_coin = self.market_scanner.get_best_coin()

            if not best_coin:
                return False

            # 현재 코인과 다르고, 점수 차이가 크면 전환
            if best_coin['market'] != self.market:
                self.log(f"💱 코인 전환: {self.market} → {best_coin['market']} "
                        f"(점수: {best_coin['score']})")

                # 텔레그램 알림
                msg = f"💱 <b>코인 전환</b>\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"기존: {self.market.replace('KRW-', '')}\n"
                msg += f"신규: {best_coin['name']}\n\n"
                msg += f"📊 모멘텀 점수: {best_coin['score']}\n"
                msg += f"📈 24H 변화: {best_coin['change_24h']:+.2f}%\n"
                msg += f"💰 거래액: {best_coin['volume_24h']/100_000_000:,.0f}억원"
                self.telegram.send_message(msg)

                # 마켓 변경
                self.market = best_coin['market']
                return True

            return False

        except Exception as e:
            self.log(f"코인 전환 검토 실패: {e}")
            return False

    def scan_multi_coin_buy_signals(self, top_n=5):
        """멀티 코인 매수 신호 동시 스캔 (스캘핑 우선)

        1순위: 스캘핑 기회
        2순위: 기술적 신호
        """
        try:
            # 모멘텀 랭킹 가져오기 (2분마다 갱신)
            if (not self.market_scanner.last_scan_time or
                (datetime.now() - self.market_scanner.last_scan_time).total_seconds() > 120):
                self.market_scanner.scan_top_coins(top_n=20, min_volume_100m=50)

            if not self.market_scanner.cached_rankings:
                return None

            # TOP N 코인 체크
            best_signal = None
            best_score = 0

            for coin in self.market_scanner.cached_rankings[:top_n]:
                market = coin['market']

                # === 1순위: 스캘핑 기회 체크 ===
                if self.enable_scalping:
                    scalping_opp = self.scalping_strategy.check_scalping_opportunity(
                        market, self.upbit, None
                    )

                    if scalping_opp and scalping_opp['action'] == 'buy':
                        # 스캘핑 점수 = 신뢰도 * 100 + 모멘텀 점수
                        scalping_score = (scalping_opp['confidence'] * 100) + coin['score']

                        if scalping_score > best_score:
                            # 임시로 마켓 변경해서 신호 가져오기
                            original_market = self.market
                            self.market = market
                            signals = self.get_multi_timeframe_signals()
                            self.market = original_market

                            if signals:
                                best_score = scalping_score
                                best_signal = {
                                    'market': market,
                                    'name': coin['name'],
                                    'signals': signals,
                                    'buy_signal_count': 3,  # 스캘핑은 최고 신호로 표시
                                    'momentum_score': coin['score'],
                                    'total_score': scalping_score,
                                    'is_scalping': True,
                                    'scalping_target': scalping_opp.get('target_profit', 1.5),
                                    'scalping_stop': scalping_opp.get('stop_loss', -1.0),
                                    'scalping_reason': scalping_opp['reason']
                                }
                                continue  # 스캘핑 발견하면 다음 코인으로

                # === 2순위: 기술적 신호 ===
                original_market = self.market
                self.market = market
                signals = self.get_multi_timeframe_signals()
                self.market = original_market

                if not signals:
                    continue

                buy_signal_count = signals.get('buy_signal_count', 0)
                signal_score = (buy_signal_count * 10) + coin['score']

                if buy_signal_count >= 1 and signal_score > best_score:
                    best_score = signal_score
                    best_signal = {
                        'market': market,
                        'name': coin['name'],
                        'signals': signals,
                        'buy_signal_count': buy_signal_count,
                        'momentum_score': coin['score'],
                        'total_score': signal_score,
                        'is_scalping': False
                    }

            if best_signal:
                if best_signal.get('is_scalping'):
                    self.log(f"⚡ 최강 스캘핑: {best_signal['name']} (신뢰도: {best_signal['total_score']:.0f})")
                    self.log(f"   사유: {best_signal['scalping_reason']}")
                else:
                    self.log(f"🎯 최강 매수 신호: {best_signal['name']} (신호: {best_signal['buy_signal_count']}/3, 모멘텀: {best_signal['momentum_score']})")

            return best_signal

        except Exception as e:
            self.log(f"멀티 코인 스캔 실패: {e}")
            return None

    def get_multi_timeframe_signals(self):
        """다중 시간대 신호 분석 (Tier 2 개선)

        1분/5분/15분을 모두 체크하여 신호 강도 판단
        """
        try:
            # 각 시간대별 신호 가져오기
            signals_1m = self.get_signals(1)
            signals_5m = self.get_signals(5)
            signals_15m = self.get_signals(15)

            if not all([signals_1m, signals_5m, signals_15m]):
                return None

            # 매수 신호 강도 계산
            buy_signals = [
                signals_1m['buy'],
                signals_5m['buy'],
                signals_15m['buy']
            ]
            buy_signal_count = sum(buy_signals)

            # 매도 신호 강도 계산
            sell_signals = [
                signals_1m['sell'],
                signals_5m['sell'],
                signals_15m['sell']
            ]
            sell_signal_count = sum(sell_signals)

            # 강한 신호: 2개 이상 동의
            strong_buy = buy_signal_count >= 2
            strong_sell = sell_signal_count >= 2

            # 매우 강한 신호: 3개 모두 동의
            very_strong_buy = buy_signal_count == 3
            very_strong_sell = sell_signal_count == 3

            # 15분봉을 기본으로 사용하되, 다중 시간대 정보 추가
            base_signals = signals_15m.copy()
            base_signals.update({
                'multi_timeframe': {
                    '1m': signals_1m,
                    '5m': signals_5m,
                    '15m': signals_15m
                },
                'buy_signal_count': buy_signal_count,
                'sell_signal_count': sell_signal_count,
                'strong_buy': strong_buy,
                'strong_sell': strong_sell,
                'very_strong_buy': very_strong_buy,
                'very_strong_sell': very_strong_sell,
                # 기존 buy/sell을 강한 신호로 대체
                'buy': strong_buy,
                'sell': strong_sell
            })

            return base_signals

        except Exception as e:
            self.log(f"다중 시간대 분석 실패: {e}")
            # 실패 시 기본 15분봉으로 fallback
            return self.get_signals(15)

    def check_and_trade_multi_coin(self):
        """멀티 코인 동시 보유 메인 로직"""
        try:
            # 일일 손실 제한 체크
            if self.trading_paused:
                self.log(f"⏸️ 거래 중단: 일일 손실 {self.daily_pnl*100:.2f}%")
                return

            # 1. 보유 중인 포지션들 체크 (매도 기회)
            for market in list(self.positions.keys()):  # copy to avoid modification during iteration
                self.check_and_trade_single_coin(market)

            # 2. 새로운 매수 기회 찾기 (포지션이 꽉 차지 않았을 때)
            if self.can_add_position() and self.enable_multi_coin and self.market_scanner:
                # TOP 코인들 스캔
                markets_to_scan = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-SOL', 'KRW-DOGE']

                best_opportunity = None
                best_score = 0

                for market in markets_to_scan:
                    # 이미 보유 중이면 스킵
                    if self.has_position_for_market(market):
                        continue

                    # MA 크로스오버 체크
                    if self.enable_ma_crossover:
                        ma_opp = self.ma_strategy.check_trading_opportunity(market, self.upbit, None)
                        if ma_opp and ma_opp['action'] == 'buy':
                            score = ma_opp['confidence'] * 100
                            if score > best_score:
                                best_score = score
                                best_opportunity = {
                                    'market': market,
                                    'type': 'ma_crossover',
                                    'opportunity': ma_opp
                                }

                    # 스캘핑 체크
                    if self.enable_scalping:
                        scalping_opp = self.scalping_strategy.check_scalping_opportunity(market, self.upbit, None)
                        if scalping_opp and scalping_opp['action'] == 'buy':
                            score = scalping_opp['confidence'] * 100
                            if score > best_score:
                                best_score = score
                                best_opportunity = {
                                    'market': market,
                                    'type': 'scalping',
                                    'opportunity': scalping_opp
                                }

                # 가장 좋은 기회가 있으면 매수
                if best_opportunity:
                    market = best_opportunity['market']
                    opp_type = best_opportunity['type']
                    opp = best_opportunity['opportunity']

                    self.log(f"💰 새 매수 기회: {market} ({opp_type}, 신뢰도 {opp['confidence']*100:.0f}%)")

                    # 해당 마켓으로 전환하여 매수
                    self.check_and_trade_single_coin(market, force_buy_opportunity=best_opportunity)

        except Exception as e:
            self.log(f"❌ 멀티 코인 체크 실패: {e}")
            import traceback
            traceback.print_exc()

    def check_and_trade(self):
        """메인 체크 로직 - 멀티 코인 동시 보유"""
        # 멀티 코인 모드로 실행
        self.check_and_trade_multi_coin()

    def check_and_trade_single_coin(self, market=None, force_buy_opportunity=None):
        """단일 코인 체크 및 거래 (멀티 코인 지원 버전)"""
        target_market = market or self.market

        # 해당 마켓의 포지션 조회
        position = self.get_position_for_market(target_market)

        try:
            # 강제 매수 기회가 있으면 바로 매수 실행
            if force_buy_opportunity:
                opp_type = force_buy_opportunity['type']
                opp = force_buy_opportunity['opportunity']

                status = self.get_current_status()
                signals = {
                    'price': status['current_price'],
                    'rsi': 50,
                    'buy_signal_count': 1
                }

                self.buy(status, signals, market=target_market)

                # 매수 성공하면 포지션에 정보 저장
                position = self.get_position_for_market(target_market)
                if position:
                    if opp_type == 'ma_crossover':
                        position['target_profit'] = opp.get('target_profit', 2.0)
                        position['stop_loss'] = opp.get('stop_loss', -1.0)
                        position['is_ma_crossover'] = True
                    elif opp_type == 'scalping':
                        position['target_profit'] = opp.get('target_profit', 1.5)
                        position['stop_loss'] = opp.get('stop_loss', -1.0)
                        position['is_scalping'] = True
                        self.scalping_strategy.record_trade(target_market, 'buy', signals['price'])
                return

            # 포지션이 없으면 체크 종료 (매도할 게 없음)
            if not position:
                return

            # 현재가 조회
            ticker = self.upbit.get_current_price(target_market)
            if not ticker:
                return

            current_price = ticker['trade_price']
            buy_price = position['buy_price']
            profit_rate = (current_price - buy_price) / buy_price

            # 포지션별 peak/low 업데이트
            if profit_rate > self.position_peaks.get(target_market, 0):
                self.position_peaks[target_market] = profit_rate
            if profit_rate < self.position_lows.get(target_market, 0):
                self.position_lows[target_market] = profit_rate

            # 보유 시간
            hold_hours = (datetime.now() - position['buy_time']).total_seconds() / 3600

            self.log(f"[{target_market}] 포지션: {profit_rate*100:+.2f}% (최고: {self.position_peaks.get(target_market, 0)*100:+.2f}%) | 보유: {hold_hours:.1f}h")

            # === 1순위: MA 크로스오버 매도 체크 ===
            if self.enable_ma_crossover and not position.get('is_scalping'):
                ma_opp = self.ma_strategy.check_trading_opportunity(target_market, self.upbit, position)

                if ma_opp and ma_opp['action'] == 'sell':
                    reason = ma_opp['reason']
                    self.log(f"📈 {target_market} MA 데스 크로스 → 매도")

                    signals = {'price': current_price}
                    self.sell(None, signals, reason, market=target_market)
                    return

            # === 2순위: 스캘핑 매도 체크 ===
            if self.enable_scalping:
                scalping_opp = self.scalping_strategy.check_scalping_opportunity(target_market, self.upbit, position)

                if scalping_opp and scalping_opp['action'] == 'sell':
                    reason = scalping_opp['reason']
                    self.log(f"⚡ {target_market} 스캘핑 매도: {reason}")

                    signals = {'price': current_price}
                    self.sell(None, signals, reason, market=target_market)
                    self.scalping_strategy.record_trade(target_market, 'sell', current_price)
                    return

            # === 3순위: 기본 익절/손절 체크 ===
            target_profit = position.get('target_profit', self.take_profit_1)
            stop_loss = position.get('stop_loss', self.stop_loss)

            if profit_rate >= target_profit:
                reason = f"목표 수익 달성 ({profit_rate*100:.2f}% >= {target_profit*100:.2f}%)"
                self.log(f"💰 {target_market} {reason}")
                signals = {'price': current_price}
                self.sell(None, signals, reason, market=target_market)
                return

            if profit_rate <= stop_loss:
                reason = f"손절 ({profit_rate*100:.2f}% <= {stop_loss*100:.2f}%)"
                self.log(f"🔴 {target_market} {reason}")
                signals = {'price': current_price}
                self.sell(None, signals, reason, market=target_market)
                return

        except Exception as e:
            self.log(f"❌ {target_market} 체크 실패: {e}")
            import traceback
            traceback.print_exc()

    def check_and_trade_legacy(self):
        """레거시 단일 코인 로직 (백업용)"""
        try:
            # 일일 손실 제한 체크 (Tier 1 개선)
            if self.trading_paused:
                self.log(f"⏸️ 거래 중단: 일일 손실 {self.daily_pnl*100:.2f}%")
                return

            # Tier 3 개선: 시장 상태 감지
            market_regime = None
            if self.use_market_regime:
                # 10분마다 시장 상태 체크
                if not self.market_regime_detector.last_check_time or \
                   (datetime.now() - self.market_regime_detector.last_check_time).total_seconds() > 600:
                    market_regime = self.market_regime_detector.detect_market_regime()
                    if market_regime:
                        regime_emoji = {"bull": "🐂", "bear": "🐻", "sideways": "↔️"}
                        self.log(f"{regime_emoji.get(market_regime['regime'])} 시장: {market_regime['regime'].upper()} "
                                f"(신뢰도: {market_regime['strength']:.0f}%, BTC RSI: {market_regime['btc_rsi_1h']:.1f})")

                # 약세장이 매우 강할 때도 과매도 반등 매수 허용
                bear_market_active = market_regime and market_regime['regime'] == 'bear' and market_regime['strength'] > 80
                btc_rsi = market_regime.get('btc_rsi_1h', 50) if market_regime else 50

                if bear_market_active:
                    self.log(f"🐻 강한 약세장 (BTC RSI: {btc_rsi:.1f}) - 과매도 반등만 매수")

            # 레거시 로직은 더 이상 사용하지 않음 (멀티 코인 모드로 대체)
            pass

        except Exception as e:
            self.log(f"❌ 레거시 체크 실패: {e}")

    def check_and_trade_legacy_old(self):
        """완전히 제거 예정 - 멀티 코인 모드로 대체됨"""
        try:
            # 더 이상 사용하지 않음
            pass

        except Exception as e:
            self.log(f"레거시 로직 오류: {e}")
    
    def daily_report(self):
        """일일 리포트"""
        try:
            status = self.get_current_status()
            
            today = datetime.now().date()
            today_trades = [t for t in self.trade_history if t['time'].date() == today]
            
            buys = sum(1 for t in today_trades if t['type'] == 'BUY')
            sells = sum(1 for t in today_trades if t['type'] == 'SELL')
            today_profit = sum(t.get('profit', 0) for t in today_trades if t['type'] == 'SELL')
            
            all_sells = [t for t in self.trade_history if t['type'] == 'SELL']
            total_profit = sum(t.get('profit', 0) for t in all_sells)
            wins = sum(1 for t in all_sells if t.get('profit', 0) > 0)
            win_rate = (wins / len(all_sells) * 100) if all_sells else 0
            
            msg = f"📊 <b>일일 리포트</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 자산:\n"
            msg += f"  • 총: {status['total']:,.0f}원\n"
            msg += f"  • 원화: {status['krw']:,.0f}원\n"
            msg += f"  • 코인: {status['coin_value']:,.0f}원\n\n"
            msg += f"📈 오늘:\n"
            msg += f"  • 거래: {len(today_trades)}회\n"
            msg += f"  • 손익: {today_profit:+,.0f}원\n\n"
            
            if self.position:
                profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
                msg += f"💼 포지션:\n"
                msg += f"  • 수익률: {profit_rate:+.2f}%\n\n"
            
            msg += f"📊 전체:\n"
            msg += f"  • 총거래: {len(all_sells)}회\n"
            msg += f"  • 누적: {total_profit:+,.0f}원\n"
            msg += f"  • 승률: {win_rate:.1f}%\n"
            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            self.telegram.send_message(msg)
            self.log("📊 일일 리포트")
            
        except Exception as e:
            self.log(f"리포트 실패: {e}")
    
    def check_daily_report(self):
        """오후 9시 리포트"""
        now = datetime.now()
        if now.hour == 21 and now.minute < 5:
            if not self.last_daily_report or self.last_daily_report.date() < now.date():
                self.daily_report()
                self.last_daily_report = now
    
    def handle_command(self, command):
        """명령어 처리 (비동기)"""
        try:
            cmd = command.lower()
            # 즉시 응답 전송 (사용자 경험 개선)
            self.telegram.send_message("⏳ 처리 중...")

            if cmd == '/status':
                self.send_status()
            elif cmd == '/report':
                self.daily_report()
            elif cmd == '/position':
                self.send_position_info()
            elif cmd == '/market':
                self.send_market_info()
            elif cmd == '/trend':
                self.send_trend_info()
            elif cmd == '/help':
                self.send_help()
            else:
                self.telegram.send_message(f"❌ 알 수 없는 명령어\n/help 입력")
        except Exception as e:
            self.telegram.send_message(f"명령어 처리 실패: {e}")
    
    def send_status(self):
        """현재 상태"""
        try:
            status = self.get_current_status()
            signals = self.get_signals(self.signal_timeframe)

            msg = f"📊 <b>현재 상태</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 총자산: {status['total']:,.0f}원\n"
            msg += f"💵 원화: {status['krw']:,.0f}원\n"
            msg += f"🪙 코인: {status['coin']:.6f} ETH\n\n"
            
            if self.position:
                profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
                msg += f"💼 포지션: {profit_rate:+.2f}%\n\n"
            else:
                msg += f"💼 포지션 없음\n\n"
            
            if signals:
                msg += f"📈 시장:\n"
                msg += f"  • RSI: {signals['rsi']:.1f}\n"
                msg += f"  • 볼린저: {signals['bb_pos']:.1f}%\n\n"
            
            msg += f"🤖 봇: 정상 작동\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self.telegram.send_message(msg)
            
        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_position_info(self):
        """포지션 정보"""
        try:
            if not self.position:
                self.telegram.send_message("💼 포지션 없음")
                return
            
            status = self.get_current_status()
            profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
            
            msg = f"💼 <b>포지션</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 매수가: {self.position['buy_price']:,.0f}원\n"
            msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
            msg += f"💵 수익률: {profit_rate:+.2f}%\n\n"
            msg += f"🎯 익절: {self.position['buy_price']*1.05:,.0f}원\n"
            msg += f"🎯 손절: {self.position['buy_price']*0.97:,.0f}원"
            
            self.telegram.send_message(msg)
            
        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_market_info(self):
        """시장 정보"""
        try:
            status = self.get_current_status()
            signals = self.get_signals(self.signal_timeframe)

            if not signals:
                self.telegram.send_message("시장 정보 없음")
                return

            msg = f"📈 <b>시장</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
            msg += f"📊 24시간: {status['change_24h']:+.2f}%\n\n"

            if signals.get('trend'):
                trend = signals['trend']
                trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
                trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}
                state = trend['trend_state']
                msg += f"🌐 추세: {trend_emoji.get(state, '📊')} {trend_name.get(state, state)}\n"
                msg += f"  • 1H: {'↑' if trend['trend_1h'] == 'up' else '↓'}\n"
                msg += f"  • 4H: {'↑' if trend['trend_4h'] == 'up' else '↓'}\n\n"

            msg += f"📊 {self.signal_timeframe}분봉:\n"
            msg += f"  • RSI: {signals['rsi']:.1f}\n"
            msg += f"  • 볼린저: {signals['bb_pos']:.1f}%\n"
            msg += f"  • 거래량: {signals['vol_ratio']:.2f}x\n\n"

            if signals['buy']:
                msg += f"🟢 매수 신호!"
            elif signals['sell']:
                msg += f"🔴 매도 신호!"
            else:
                msg += f"⚪ 대기"

            self.telegram.send_message(msg)

        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")

    def send_trend_info(self):
        """추세 상세 정보"""
        try:
            trend = self.get_trend_analysis()

            if not trend:
                self.telegram.send_message("추세 정보 없음")
                return

            trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
            trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}
            state = trend['trend_state']

            msg = f"🌐 <b>추세 분석</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 현재: {trend_emoji.get(state, '📊')} <b>{trend_name.get(state, state)}</b>\n\n"

            msg += f"⏱️ 1시간봉:\n"
            msg += f"  • 추세: {'↑ 상승' if trend['trend_1h'] == 'up' else '↓ 하락'}\n"
            msg += f"  • RSI: {trend['rsi_1h']:.1f}\n"
            msg += f"  • MA20: {trend['ma20_1h']:,.0f}원\n"
            msg += f"  • MA50: {trend['ma50_1h']:,.0f}원\n\n"

            msg += f"⏱️ 4시간봉:\n"
            msg += f"  • 추세: {'↑ 상승' if trend['trend_4h'] == 'up' else '↓ 하락'}\n"
            msg += f"  • RSI: {trend['rsi_4h']:.1f}\n"
            msg += f"  • MA20: {trend['ma20_4h']:,.0f}원\n"
            msg += f"  • MA50: {trend['ma50_4h']:,.0f}원\n\n"

            msg += f"🎯 전략:\n"
            msg += f"  • 매수: {'✅ 가능' if trend['buy_allowed'] else '❌ 금지'}\n"
            msg += f"  • RSI 기준: < {trend['rsi_threshold']}\n"

            self.telegram.send_message(msg)

        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_help(self):
        """도움말"""
        msg = f"🤖 <b>명령어</b>\n━━━━━━━━━━━━━━━━━\n\n"
        msg += f"/status - 현재 상태\n"
        msg += f"/position - 포지션\n"
        msg += f"/market - 시장 현황\n"
        msg += f"/trend - 추세 분석\n"
        msg += f"/report - 일일 리포트\n"
        msg += f"/help - 도움말\n\n"
        msg += f"⚙️ 다층 익절 전략:\n"
        msg += f"  • ⚡ 퀵익절: +{self.quick_profit*100:.1f}% (30분내)\n"
        msg += f"  • 1차: +{self.take_profit_1*100:.1f}%\n"
        msg += f"  • 2차: +{self.take_profit_2*100:.1f}%\n"
        msg += f"  • 최종: +{self.take_profit_3*100:.0f}%\n\n"
        msg += f"🛡️ 리스크 관리:\n"
        msg += f"  • 손절: {self.stop_loss*100:.1f}%\n"
        msg += f"  • 동적 트레일링: 0.3/0.5/0.8%\n"
        msg += f"  • 타임아웃: {self.position_timeout_hours}h\n\n"
        msg += f"📊 추세별 매수 (1H+4H):\n"
        msg += f"  • 🚀 강한상승: RSI < 50\n"
        msg += f"  • 📊 조정: RSI < 45\n"
        msg += f"  • ⚡ 약한반등: RSI < 40\n"
        msg += f"  • 🔻 강한하락: RSI < 30"

        self.telegram.send_message(msg)
    
    def check_telegram_commands(self):
        """명령어 체크 (백그라운드 처리)"""
        try:
            updates = self.telegram.get_updates(self.last_update_id)

            if not updates or 'result' not in updates:
                return

            for update in updates['result']:
                self.last_update_id = update['update_id'] + 1

                if 'message' in update and 'text' in update['message']:
                    text = update['message']['text'].strip()

                    if text.startswith('/'):
                        self.log(f"명령어: {text}")
                        # 백그라운드로 실행하여 메인 루프 차단 방지
                        self.executor.submit(self.handle_command, text)

        except Exception as e:
            pass
    
    def initialize(self):
        """초기화"""
        try:
            status = self.get_current_status()
            
            self.log(f"\n{'='*50}")
            self.log(f"초기화")
            self.log(f"원화: {status['krw']:,.0f}원")
            self.log(f"코인: {status['coin']:.6f} ETH")
            self.log(f"총자산: {status['total']:,.0f}원")
            
            # 기존 코인
            if status['coin'] >= 0.001:
                buy_price = status['avg_price'] if status['avg_price'] > 0 else status['current_price']
                
                self.position = {
                    'buy_price': buy_price,
                    'buy_time': datetime.now(),
                    'amount': status['coin'],
                    'buy_krw': status['coin'] * buy_price
                }
                
                profit_rate = (status['current_price'] - buy_price) / buy_price * 100
                
                msg = f"💼 <b>기존 포지션</b>\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"🪙 {status['coin']:.6f} ETH\n"
                msg += f"📊 매수가: {buy_price:,.0f}원\n"
                msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
                msg += f"💵 수익률: {profit_rate:+.2f}%\n\n"
                msg += f"✅ 감시 시작!"
                
                self.telegram.send_message(msg)
                self.log("✅ 기존 포지션")
            
            else:
                mode_tag = "🧪 [시뮬레이션 모드]" if self.dry_run else ""
                msg = f"💰 <b>봇 시작</b> {mode_tag}\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"💵 원화: {status['krw']:,.0f}원\n"
                msg += f"✅ 매수 신호 대기\n\n"
                msg += f"⚙️ 다층 익절 전략:\n"
                msg += f"  • 다중 시간대 분석 (1H + 4H)\n"
                msg += f"  • 익절: ⚡{self.quick_profit*100:.1f}% / {self.take_profit_1*100:.1f}% / {self.take_profit_2*100:.1f}% / {self.take_profit_3*100:.0f}%\n"
                msg += f"  • 손절: {abs(self.stop_loss)*100:.1f}%\n"
                msg += f"  • 동적 트레일링 & 타임아웃 {self.position_timeout_hours}h"

                self.telegram.send_message(msg)
                self.log("✅ 신호 대기")
                
        except Exception as e:
            self.log(f"초기화 실패: {e}")
    
    def log(self, msg):
        """로그"""
        print(msg)
    
    def update_check_interval(self):
        """동적 스캔 빈도 업데이트 (Tier 1 개선)"""
        # 5분마다 변동성 체크
        now = datetime.now()
        if self.last_atr_check and (now - self.last_atr_check).total_seconds() < 300:
            return

        self.last_atr_check = now

        try:
            # ATR 계산을 위한 데이터 가져오기
            from advanced_features import VolatilityManager
            candles = self.upbit.get_candles(self.market, 15, 30)  # 15분봉 30개
            if not candles or len(candles) < 14:
                return

            atr = VolatilityManager.calculate_atr(candles, period=14)
            if not atr:
                return

            current_price = candles[0]['trade_price']
            atr_percent = (atr / current_price) * 100

            # 변동성 기반 동적 간격
            if atr_percent > 4:
                self.current_check_interval = 120  # 2분 (고변동성)
            elif atr_percent > 2:
                self.current_check_interval = 180  # 3분 (중변동성)
            else:
                self.current_check_interval = 300  # 5분 (저변동성)

            # 포지션 보유 중이면 더 자주 체크
            if self.position:
                self.current_check_interval = min(self.current_check_interval, 60)  # 최대 1분

            self.log(f"⏱️ 스캔 간격 업데이트: {self.current_check_interval}초 (ATR: {atr_percent:.2f}%)")

        except Exception as e:
            self.log(f"스캔 간격 업데이트 실패: {e}")

    def run(self, interval=300):
        """실행 (Tier 1 개선: 동적 스캔 빈도)"""
        self.initialize()
        self.send_help()
        self.base_check_interval = interval
        self.current_check_interval = interval

        self.log(f"\n🤖 봇 시작 (기본 {interval}초 체크, 동적 조절 활성화)")

        try:
            while self.is_running:
                # 동적 스캔 빈도 업데이트
                self.update_check_interval()

                self.check_and_trade()
                self.check_daily_report()
                self.check_telegram_commands()

                # 동적으로 조절된 간격으로 대기
                time.sleep(self.current_check_interval)
        except KeyboardInterrupt:
            self.log("\n봇 종료")
            self.telegram.send_message("⏹️ 봇 중지")
        finally:
            # 백그라운드 작업 정리
            self.executor.shutdown(wait=True)


# ===== 실행 =====
if __name__ == "__main__":
    from config import get_config

    try:
        # .env 파일에서 설정 로드
        config = get_config()

        # 멀티 코인 모드 활성화 여부 (환경변수로 제어)
        enable_multi_coin = os.environ.get('ENABLE_MULTI_COIN', 'true').lower() == 'true'

        print("✅ 설정 로드 완료")
        print(f"Market: {config['market']}")
        print(f"Check Interval: {config['check_interval']}초")
        print(f"멀티 코인 모드: {'ON' if enable_multi_coin else 'OFF'}\n")

        # 실행
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])
        bot = TradingBot(
            upbit,
            telegram,
            config['market'],
            enable_multi_coin=enable_multi_coin
        )
        bot.run(config['check_interval'])

    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        print("\n.env 파일을 확인해주세요.")