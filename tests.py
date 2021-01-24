import random
import asyncio
import threading


class MyServer:
    def start(self):
        loop = asyncio.get_event_loop()
        f = self._start()
        loop.run_until_complete(f)

    async def _start(self):
        server = await asyncio.start_server(self.connect_cb, "45.67.54.238", 52314)
        addr = server.sockets[0].getsockname()
        print(f'Serving on {addr}')

        async with server:
            await server.serve_forever()

    async def connect_cb(self, reader:asyncio.StreamReader, writer:asyncio.StreamWriter):
        data = await reader.read(100)
        message = data.decode()
        addr = writer.get_extra_info('peername')

        print(f"Received {message!r} from {addr!r}")

        print(f"Send: {message!r}")
        writer.write(data)
        await writer.drain()

        print("Close the connection")
        writer.close()


class MyClient:
    def start(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._start())


    async def _start(self):
        message = 'hello server'
        reader, writer = await asyncio.open_connection("45.67.54.238", 52314)
        print(f'Send: {message!r}')
        writer.write(message.encode())

        data = await reader.read(100)
        print(f'Received: {data.decode()!r}')

        print('Close the connection')
        writer.close()

def TestRandomStop():
    count = 0
    while True:
        count += 1
        a = random.random()
        if (a < 0.03):
            break

    print(count)
    return count


def TestStruct():
    import struct

    d = struct.pack("i", 10) + b'good'

    s = struct.unpack("i", d)
    print(s)


def TestInput():
    for e in range(3):
        s = input('hello\n')
        print(s)