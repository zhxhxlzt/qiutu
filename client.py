

import asyncio


class MyClient:
    def start(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._start())


    async def _start(self):
        message = 'hello server'
        reader, writer = await asyncio.open_connection("localhost", 52314)
        print(f'Send: {message!r}')
        writer.write(message.encode())

        data = await reader.read(100)
        print(f'Received: {data.decode()!r}')

        print('Close the connection')
        writer.close()

client = MyClient()
client.start()