#!/usr/bin/env python3
"""
텔레그램 알림 전송
"""
import sys
import requests

def send_notification(needs_optimization, token, chat_id):
    """텔레그램으로 최적화 결과 알림"""

    if needs_optimization == 'true':
        message = """
🤖 <b>자동 최적화 실행됨</b>
━━━━━━━━━━━━━━━━━

📊 거래 성과가 목표치 미달로 파라미터를 자동 조정했습니다.

✅ GitHub에 PR이 생성되었습니다.
📋 리뷰 후 승인해주세요.

⚠️ 긴급 최적화의 경우 자동 적용됩니다.
        """
    else:
        message = """
✅ <b>성과 양호</b>
━━━━━━━━━━━━━━━━━

📊 거래 성과가 목표치를 충족하고 있습니다.
🎯 최적화가 필요하지 않습니다.
        """

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=data, timeout=10)
        if response.ok:
            print("✅ 텔레그램 알림 전송 완료")
        else:
            print(f"⚠️ 텔레그램 전송 실패: {response.text}")
    except Exception as e:
        print(f"❌ 텔레그램 전송 오류: {e}")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: send_telegram_notification.py <needs_optimization> <token> <chat_id>")
        sys.exit(1)

    send_notification(sys.argv[1], sys.argv[2], sys.argv[3])
