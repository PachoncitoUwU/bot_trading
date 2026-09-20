import asyncio
import sys
from app.exchange.iqoption_adapter import IQOptionAdapter
from app.core.constants import BotMode

async def main():
    adapter = IQOptionAdapter(mode=BotMode.TESTNET)
    await adapter.initialize()
    client = adapter.client
    try:
        history = client.get_option_history('binary', 1, 20)
        if isinstance(history, dict) and 'msg' in history:
            result = history['msg'].get('result', {})
            items = result.get('items', [])
            print(f"Total history items: {len(items)}")
            for item in items[:10]:
                print(f"Active: {item.get('active')} | Amount: {item.get('amount')} | Win: {item.get('win')} | WinAmount: {item.get('win_amount')} | Created: {item.get('created')}")
        else:
            print("History raw:", history)
    except Exception as e:
        print("Error history:", e)

if __name__ == "__main__":
    asyncio.run(main())
