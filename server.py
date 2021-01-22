import socket


import asyncio



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


# server = MyServer()
# server.start()

import player
raceServer = player.RaceServer()
raceServer.Start()
