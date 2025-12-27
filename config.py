"""
환경 변수 로더
.env 파일에서 API 키 및 설정을 읽어옵니다
"""
import os


def load_env(filepath='.env'):
    """
    .env 파일에서 환경 변수 로드
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"{filepath} 파일이 없습니다. .env 파일을 생성해주세요.")

    env_vars = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # 빈 줄이나 주석 무시
            if not line or line.startswith('#'):
                continue

            # KEY=VALUE 형식 파싱
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def get_config():
    """
    설정 가져오기
    """
    try:
        env = load_env()

        config = {
            'upbit_access_key': env.get('UPBIT_ACCESS_KEY', ''),
            'upbit_secret_key': env.get('UPBIT_SECRET_KEY', ''),
            'telegram_token': env.get('TELEGRAM_TOKEN', ''),
            'telegram_chat_id': env.get('TELEGRAM_CHAT_ID', ''),
            'market': env.get('MARKET', 'KRW-ETH'),
            'check_interval': int(env.get('CHECK_INTERVAL', '300'))
        }

        # 필수 값 검증
        required = ['upbit_access_key', 'upbit_secret_key', 'telegram_token', 'telegram_chat_id']
        missing = [k for k in required if not config[k]]

        if missing:
            raise ValueError(f"필수 설정 누락: {', '.join(missing)}")

        return config

    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n.env 파일 예시:")
        print("=" * 50)
        print("UPBIT_ACCESS_KEY=your_access_key")
        print("UPBIT_SECRET_KEY=your_secret_key")
        print("TELEGRAM_TOKEN=your_telegram_token")
        print("TELEGRAM_CHAT_ID=your_chat_id")
        print("MARKET=KRW-ETH")
        print("CHECK_INTERVAL=300")
        print("=" * 50)
        raise
    except ValueError as e:
        print(f"❌ {e}")
        raise


if __name__ == "__main__":
    # 테스트
    try:
        config = get_config()
        print("✅ 설정 로드 성공!")
        print(f"Market: {config['market']}")
        print(f"Check Interval: {config['check_interval']}초")
        print(f"Upbit API Key: {config['upbit_access_key'][:10]}...")
        print(f"Telegram Token: {config['telegram_token'][:20]}...")
    except Exception as e:
        print(f"설정 로드 실패: {e}")
