"""
주문 실행 관리자 (Institutional-Level Phase 1)
- 지정가 주문 (Limit Orders)
- 슬리피지 추정 (Slippage Estimation)
- 호가창 분석 (Orderbook Analysis)
- 실행 품질 측정 (Execution Quality)
"""
from datetime import datetime
import time


class ExecutionManager:
    """주문 실행 최적화 및 품질 관리"""

    def __init__(self, upbit):
        self.upbit = upbit
        self.execution_history = []

    def estimate_slippage(self, market, order_type, krw_amount):
        """
        슬리피지 추정 (호가창 분석)

        Args:
            market: 마켓 (KRW-BTC)
            order_type: 'buy' or 'sell'
            krw_amount: 주문 금액 (KRW)

        Returns:
            dict: {
                'estimated_slippage': float (%),
                'estimated_price': float,
                'orderbook_depth': int (몇 호가까지 소진),
                'recommendation': str
            }
        """
        try:
            orderbook = self.upbit.get_orderbook(market)
            if not orderbook:
                return None

            # 매수/매도 호가 선택
            if order_type == 'buy':
                orders = orderbook['orderbook_units']  # 매도 호가 (ask)
                prices = [(unit['ask_price'], unit['ask_size']) for unit in orders]
            else:  # sell
                orders = orderbook['orderbook_units']  # 매수 호가 (bid)
                prices = [(unit['bid_price'], unit['bid_size']) for unit in orders]

            if not prices:
                return None

            # 시장가로 체결될 평균 가격 계산
            best_price = prices[0][0]
            remaining_krw = krw_amount
            total_cost = 0
            total_quantity = 0
            depth_count = 0

            for price, size in prices:
                depth_count += 1

                if order_type == 'buy':
                    # 매수: 해당 호가에서 얼마나 살 수 있는지
                    available_krw = price * size
                    if remaining_krw <= available_krw:
                        # 이 호가에서 다 채움
                        quantity = remaining_krw / price
                        total_cost += remaining_krw
                        total_quantity += quantity
                        remaining_krw = 0
                        break
                    else:
                        # 이 호가 전부 소진
                        total_cost += available_krw
                        total_quantity += size
                        remaining_krw -= available_krw
                else:  # sell
                    # 매도: 해당 호가에서 얼마나 팔 수 있는지 (역산)
                    sell_quantity = krw_amount / best_price  # 대략적인 매도 수량
                    available_quantity = size

                    if sell_quantity <= available_quantity:
                        total_cost += price * sell_quantity
                        total_quantity += sell_quantity
                        break
                    else:
                        total_cost += price * available_quantity
                        total_quantity += available_quantity
                        sell_quantity -= available_quantity

            # 평균 체결가
            avg_price = total_cost / total_quantity if total_quantity > 0 else best_price

            # 슬리피지 계산 (최우선 호가 대비)
            slippage_pct = ((avg_price - best_price) / best_price) * 100 if order_type == 'buy' else ((best_price - avg_price) / best_price) * 100

            # 추천사항
            if slippage_pct < 0.05:
                recommendation = "지정가 불필요 (시장가 OK)"
            elif slippage_pct < 0.15:
                recommendation = "지정가 권장 (중간가)"
            else:
                recommendation = "지정가 필수 (분할 매수 고려)"

            return {
                'estimated_slippage': abs(slippage_pct),
                'estimated_price': avg_price,
                'best_price': best_price,
                'orderbook_depth': depth_count,
                'recommendation': recommendation,
                'sufficient_liquidity': remaining_krw == 0 or sell_quantity == 0
            }

        except Exception as e:
            print(f"슬리피지 추정 실패: {e}")
            return None

    def execute_limit_order(self, market, order_type, amount, price_strategy='best', max_wait_seconds=30):
        """
        지정가 주문 실행

        Args:
            market: 마켓
            order_type: 'buy' or 'sell'
            amount: 수량 (코인 개수) or 금액 (KRW)
            price_strategy:
                - 'best': 최우선 호가
                - 'mid': 최우선 호가 + 1틱 (더 유리한 가격)
                - 'aggressive': 최우선 호가 - 1틱 (빠른 체결)
            max_wait_seconds: 최대 대기 시간 (초과시 시장가 전환)

        Returns:
            dict: 주문 결과
        """
        try:
            orderbook = self.upbit.get_orderbook(market)
            if not orderbook:
                return self._fallback_market_order(market, order_type, amount)

            # 가격 전략에 따른 지정가 결정
            if order_type == 'buy':
                best_price = orderbook['orderbook_units'][0]['ask_price']

                if price_strategy == 'best':
                    limit_price = best_price
                elif price_strategy == 'mid':
                    # 매수호가와 매도호가 중간
                    bid_price = orderbook['orderbook_units'][0]['bid_price']
                    limit_price = (best_price + bid_price) / 2
                else:  # aggressive
                    limit_price = best_price * 1.0001  # 0.01% 더 높게

            else:  # sell
                best_price = orderbook['orderbook_units'][0]['bid_price']

                if price_strategy == 'best':
                    limit_price = best_price
                elif price_strategy == 'mid':
                    ask_price = orderbook['orderbook_units'][0]['ask_price']
                    limit_price = (best_price + ask_price) / 2
                else:  # aggressive
                    limit_price = best_price * 0.9999  # 0.01% 더 낮게

            # 주문 실행 (업비트 API)
            start_time = datetime.now()

            if order_type == 'buy':
                # 매수: 금액(KRW) 기준
                result = self.upbit.buy_limit(market, limit_price, amount)
            else:
                # 매도: 수량(코인) 기준
                result = self.upbit.sell_limit(market, limit_price, amount)

            if not result:
                # 실패시 시장가로 전환
                print(f"⚠️ 지정가 주문 실패, 시장가로 전환")
                return self._fallback_market_order(market, order_type, amount)

            order_uuid = result.get('uuid')

            # 주문 체결 대기
            waited_seconds = 0
            while waited_seconds < max_wait_seconds:
                time.sleep(1)
                waited_seconds += 1

                # 주문 상태 확인
                order_status = self.upbit.get_order(order_uuid)

                if order_status and order_status.get('state') == 'done':
                    # 체결 완료
                    execution_time = (datetime.now() - start_time).total_seconds()

                    executed_price = float(order_status.get('price', limit_price))
                    executed_volume = float(order_status.get('executed_volume', 0))

                    # 실행 품질 기록
                    self._record_execution_quality(
                        market=market,
                        order_type=order_type,
                        limit_price=limit_price,
                        executed_price=executed_price,
                        executed_volume=executed_volume,
                        execution_time=execution_time,
                        strategy=price_strategy
                    )

                    return {
                        'success': True,
                        'order_type': 'limit',
                        'price': executed_price,
                        'volume': executed_volume,
                        'execution_time': execution_time,
                        'uuid': order_uuid
                    }

            # 시간 초과: 미체결 주문 취소 후 시장가 전환
            print(f"⚠️ 지정가 체결 대기 시간 초과 ({max_wait_seconds}초), 시장가로 전환")
            self.upbit.cancel_order(order_uuid)
            return self._fallback_market_order(market, order_type, amount)

        except Exception as e:
            print(f"지정가 주문 실행 실패: {e}")
            return self._fallback_market_order(market, order_type, amount)

    def _fallback_market_order(self, market, order_type, amount):
        """시장가 주문으로 폴백"""
        try:
            if order_type == 'buy':
                result = self.upbit.buy_market_order(market, amount)
            else:
                result = self.upbit.sell_market_order(market, amount)

            if result:
                return {
                    'success': True,
                    'order_type': 'market',
                    'price': result.get('price'),
                    'volume': result.get('executed_volume'),
                    'uuid': result.get('uuid')
                }
            return {'success': False}

        except Exception as e:
            print(f"시장가 주문 실패: {e}")
            return {'success': False}

    def _record_execution_quality(self, market, order_type, limit_price, executed_price,
                                   executed_volume, execution_time, strategy):
        """실행 품질 기록 (내부 추적)"""

        # 가격 개선도 (Price Improvement)
        if order_type == 'buy':
            price_improvement = ((limit_price - executed_price) / limit_price) * 100
        else:
            price_improvement = ((executed_price - limit_price) / limit_price) * 100

        record = {
            'timestamp': datetime.now(),
            'market': market,
            'order_type': order_type,
            'strategy': strategy,
            'limit_price': limit_price,
            'executed_price': executed_price,
            'executed_volume': executed_volume,
            'execution_time': execution_time,
            'price_improvement': price_improvement
        }

        self.execution_history.append(record)

        # 최근 100건만 유지
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]

    def get_execution_stats(self, minutes=60):
        """
        실행 품질 통계 (최근 N분)

        Returns:
            dict: {
                'total_orders': int,
                'avg_execution_time': float (초),
                'avg_price_improvement': float (%),
                'limit_order_ratio': float (%),
                'fill_rate': float (%)
            }
        """
        cutoff = datetime.now()
        recent = [r for r in self.execution_history
                  if (cutoff - r['timestamp']).total_seconds() <= minutes * 60]

        if not recent:
            return None

        total_orders = len(recent)
        avg_exec_time = sum(r['execution_time'] for r in recent) / total_orders
        avg_price_improvement = sum(r['price_improvement'] for r in recent) / total_orders
        limit_orders = sum(1 for r in recent if r.get('strategy') != 'market')
        limit_order_ratio = (limit_orders / total_orders) * 100

        return {
            'total_orders': total_orders,
            'avg_execution_time': round(avg_exec_time, 2),
            'avg_price_improvement': round(avg_price_improvement, 4),
            'limit_order_ratio': round(limit_order_ratio, 1),
            'period_minutes': minutes
        }
