import os
import jwt
import hashlib
import requests
import uuid
from urllib.parse import urlencode, unquote

class UpbitAPI:
    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key
        self.server_url = "https://api.upbit.com"
    
    def _get_headers(self, query=None):
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query:
            query_string = unquote(urlencode(query, doseq=True)).encode("utf-8")
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        
        jwt_token = jwt.encode(payload, self.secret_key)
        return {'Authorization': f'Bearer {jwt_token}'}
    
    def get_accounts(self):
        url = f"{self.server_url}/v1/accounts"
        headers = self._get_headers()
        response = requests.get(url, headers=headers)
        return response.json()

    def get_market_all(self):
        """전체 마켓 목록 조회"""
        url = f"{self.server_url}/v1/market/all"
        response = requests.get(url)
        return response.json()

    def get_current_price(self, market="KRW-ETH"):
        url = f"{self.server_url}/v1/ticker"
        params = {"markets": market}
        response = requests.get(url, params=params)
        return response.json()[0]

    def get_ticker(self, markets):
        """여러 마켓의 현재가 정보 조회

        Args:
            markets: 마켓 리스트 또는 단일 마켓

        Returns:
            ticker 정보 리스트
        """
        url = f"{self.server_url}/v1/ticker"

        if isinstance(markets, list):
            markets_str = ','.join(markets)
        else:
            markets_str = markets

        params = {"markets": markets_str}
        response = requests.get(url, params=params)
        return response.json()

    def get_orderbook(self, market="KRW-ETH"):
        url = f"{self.server_url}/v1/orderbook"
        params = {"markets": market}
        response = requests.get(url, params=params)
        return response.json()[0]
    
    def get_candles(self, market="KRW-ETH", interval="minutes", unit=1, count=200):
        if interval == "minutes":
            url = f"{self.server_url}/v1/candles/minutes/{unit}"
        else:
            url = f"{self.server_url}/v1/candles/{interval}"
        
        params = {"market": market, "count": count}
        response = requests.get(url, params=params)
        return response.json()
    
    def order_market_buy(self, market, price):
        """시장가 매수"""
        url = f"{self.server_url}/v1/orders"
        
        query = {
            'market': market,
            'side': 'bid',
            'price': str(price),
            'ord_type': 'price'
        }
        
        headers = self._get_headers(query)
        response = requests.post(url, json=query, headers=headers)
        return response.json()
    
    def order_market_sell(self, market, volume):
        """시장가 매도"""
        url = f"{self.server_url}/v1/orders"

        query = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'ord_type': 'market'
        }

        headers = self._get_headers(query)
        response = requests.post(url, json=query, headers=headers)
        return response.json()

    def get_market_all(self):
        """마켓 코드 조회"""
        url = f"{self.server_url}/v1/market/all"
        params = {"isDetails": "false"}
        response = requests.get(url, params=params)
        return response.json()

    def get_current_prices(self, markets):
        """여러 마켓의 현재가 한번에 조회

        Args:
            markets: 마켓 리스트 ['KRW-BTC', 'KRW-ETH', ...]
        """
        url = f"{self.server_url}/v1/ticker"
        # 한번에 최대 100개까지 조회 가능
        markets_str = ','.join(markets[:100])
        params = {"markets": markets_str}
        response = requests.get(url, params=params)
        return response.json()

    def buy_limit(self, market, price, volume):
        """지정가 매수"""
        url = f"{self.server_url}/v1/orders"

        query = {
            'market': market,
            'side': 'bid',
            'volume': str(volume),
            'price': str(price),
            'ord_type': 'limit'
        }

        headers = self._get_headers(query)
        try:
            response = requests.post(url, json=query, headers=headers)
            return response.json()
        except Exception as e:
            print(f"지정가 매수 실패: {e}")
            return None

    def sell_limit(self, market, price, volume):
        """지정가 매도"""
        url = f"{self.server_url}/v1/orders"

        query = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'price': str(price),
            'ord_type': 'limit'
        }

        headers = self._get_headers(query)
        try:
            response = requests.post(url, json=query, headers=headers)
            return response.json()
        except Exception as e:
            print(f"지정가 매도 실패: {e}")
            return None

    def get_order(self, uuid):
        """주문 상태 조회"""
        url = f"{self.server_url}/v1/order"

        query = {'uuid': uuid}
        headers = self._get_headers(query)

        try:
            response = requests.get(url, params=query, headers=headers)
            return response.json()
        except Exception as e:
            print(f"주문 조회 실패: {e}")
            return None

    def cancel_order(self, uuid):
        """주문 취소"""
        url = f"{self.server_url}/v1/order"

        query = {'uuid': uuid}
        headers = self._get_headers(query)

        try:
            response = requests.delete(url, params=query, headers=headers)
            return response.json()
        except Exception as e:
            print(f"주문 취소 실패: {e}")
            return None

    def buy_market_order(self, market, krw_amount):
        """시장가 매수 (wrapper)"""
        return self.order_market_buy(market, krw_amount)

    def sell_market_order(self, market, volume):
        """시장가 매도 (wrapper)"""
        return self.order_market_sell(market, volume)

    def get_balances(self):
        """잔고 조회 (wrapper)"""
        return self.get_accounts()