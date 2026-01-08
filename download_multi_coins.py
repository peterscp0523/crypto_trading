#!/usr/bin/env python3
"""
여러 코인 데이터 다운로드 (업비트)
BTC, ETH, SOL, XRP 등
"""
import requests
import pandas as pd
from datetime import datetime
import time


def download_upbit_candles(market='KRW-BTC', unit=240, start_date='2022-01-01'):
    """업비트 캔들 데이터 다운로드"""
    print(f"\n{'='*80}")
    print(f"{market} {unit}분봉 다운로드 중...")
    print(f"{'='*80}")

    base_url = f"https://api.upbit.com/v1/candles/minutes/{unit}"
    all_data = []
    to_timestamp = None
    request_count = 0
    target_start = datetime.strptime(start_date, '%Y-%m-%d')

    while True:
        params = {
            'market': market,
            'count': 200
        }

        if to_timestamp:
            params['to'] = to_timestamp

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            request_count += 1
            all_data.extend(data)

            oldest_candle_time = data[-1]['candle_date_time_kst']
            oldest_dt = datetime.fromisoformat(oldest_candle_time.replace('Z', '+00:00'))

            if request_count % 20 == 0:
                print(f"  {len(all_data)}개 수집 중...")

            if oldest_dt.replace(tzinfo=None) <= target_start:
                print(f"  ✅ 목표 날짜 도달! 총 {len(all_data)}개")
                break

            to_timestamp = oldest_candle_time
            time.sleep(0.12)

            if request_count >= 500:
                print(f"  ⚠️ 최대 요청 도달")
                break

        except Exception as e:
            print(f"  ❌ 오류: {e}")
            break

    return all_data


def process_and_save(data, filename):
    """데이터 처리 및 저장"""
    if not data:
        return None

    df = pd.DataFrame(data)
    df = df[[
        'candle_date_time_kst',
        'opening_price',
        'high_price',
        'low_price',
        'trade_price',
        'candle_acc_trade_volume'
    ]].copy()

    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"  💾 저장: {filename}")
    print(f"     기간: {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    return df


def main():
    """메인 함수"""
    print("="*80)
    print("멀티 코인 데이터 다운로드")
    print("="*80)

    # 주요 코인 목록
    coins = [
        ('KRW-BTC', 'btc'),
        ('KRW-ETH', 'eth'),
        ('KRW-XRP', 'xrp'),
        ('KRW-SOL', 'sol'),
        ('KRW-ADA', 'ada')
    ]

    for market, symbol in coins:
        # 4시간봉 다운로드
        data = download_upbit_candles(
            market=market,
            unit=240,
            start_date='2022-01-01'
        )

        if data:
            filename = f'upbit_{symbol}_4h.csv'
            process_and_save(data, filename)

        time.sleep(1)  # 거래소 부하 방지

    print("\n" + "="*80)
    print("✅ 모든 다운로드 완료!")
    print("="*80)


if __name__ == "__main__":
    main()
