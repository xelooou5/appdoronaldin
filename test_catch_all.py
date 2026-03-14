import asyncio

# Import handler from bot_start
from bot_start import catch_all

class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.chat = type('C', (), {'id': 123})

    async def reply_text(self, text):
        print('TEST_REPLY:', text)

class DummyUpdate:
    def __init__(self, msg):
        self.message = msg

    def to_dict(self):
        return {'message': {'text': self.message.text}}

class DummyContext:
    pass

async def run_test():
    upd = DummyUpdate(DummyMessage('/start'))
    ctx = DummyContext()
    await catch_all(upd, ctx)

if __name__ == '__main__':
    asyncio.run(run_test())

