
import asyncio
import random
import json
import struct
import threading
from typing import List
def Log(*msg):
    print(*msg)

class Config:
    def __init__(self):
        self.server_host = "45.67.54.238"
        self.server_port = 52314

    def DebugMode(self):
        self.server_host = "localhost"

g_Config = Config()
g_Config.DebugMode()

class ResponceOp:
    Cooperate = 0
    Betry = 1


class Protocol:
    Response = 0
    Join = 1
    Start = 2
    Hello = 3
    AskResponse = 4
    Info = 5
    RequestMark = 6
    SendMark = 7
    Quit = 8

def PackMsg(protocol, data):
    msg = {
        "proto": protocol,
        "data": data
    }
    return json.dumps(msg)


async def SendMsg(writer: asyncio.StreamWriter, protocol, data):
    msg = PackMsg(protocol, data)
    msg = struct.pack("i", len(msg)) + msg.encode()
    writer.write(msg)
    await writer.drain()


async def RcvMsg(reader: asyncio.StreamReader):
    msg_len = await reader.readexactly(4)
    msg_len = struct.unpack("i", msg_len)
    msg = await reader.readexactly(msg_len[0])
    msg = json.loads(msg)
    return msg["proto"], msg["data"]



class ClientPlayer:
    def __init__(self):
        self.m_history = {}
        self.m_reader = None
        self.m_writer = None

    async def Connect(self):
        reader, writer = await asyncio.open_connection(g_Config.server_host, g_Config.server_port)
        self.m_reader = reader
        self.m_writer = writer

    async def Join(self):
        await SendMsg(self.m_writer, Protocol.Join, '')
        Log('send join request')

    async def Start(self):
        await SendMsg(self.m_writer, Protocol.Start, '')

    async def Cooperate(self):
        await SendMsg(self.m_writer, Protocol.Response, ResponceOp.Cooperate)

    async def Betray(self):
        await SendMsg(self.m_writer, Protocol.Response, ResponceOp.Betry)

    async def Quit(self):
        await SendMsg(self.m_writer, Protocol.Quit, '')

    async def RequestMark(self):
        await SendMsg(self.m_writer, Protocol.RequestMark, '')

    async def ReceiveMark(self, mark):
        pass


class RaceClient:
    def __init__(self):
        self.m_player = ClientPlayer()
        self.m_cmd = ''
        self.m_cmdLock = threading.Lock()
        self.m_cmdThread = None
        self.m_close = False

    def Start(self):
        self.m_cmdThread = threading.Thread(target=self.UserCmd)
        self.m_cmdThread.start()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._Start())

    async def _Start(self):
        await self.m_player.Connect()
        print('connect successed!')
        loop = asyncio.get_running_loop()
        loop.create_task(self.ListenServer())
        while not self.m_close:
            await self.ProcessCmd()
            await asyncio.sleep(0.1)
        print('race stoped')

    async def ListenServer(self):
        while not self.m_close:
            try:
                proto, data = await RcvMsg(self.m_player.m_reader)
            except:
                self.m_close = True
                return
            if proto == Protocol.Info:
                print(data)

    async def ProcessCmd(self):
        cmd = self.FetchCmd()
        if not cmd:
            return
        if cmd == str(Protocol.Join):
            await self.m_player.Join()

        if cmd == str(Protocol.Start):
            await self.m_player.Start()

        elif cmd == "y":
            await self.m_player.Cooperate()

        elif cmd == "n":
            await self.m_player.Betray()
        elif cmd == "-1":
            await self.m_player.Quit()

    def UserCmd(self):
        while True:
            cmd = input()
            with self.m_cmdLock:
                self.m_cmd = cmd

    def FetchCmd(self):
        if not self.m_cmd:
            return None
        with self.m_cmdLock:
            cmd, self.m_cmd = self.m_cmd, None
            return cmd

class ServerPlayer:
    def __init__(self):
        self.m_history = {}
        self.m_curVersusPlayer = None
        self.m_reader = None
        self.m_writer = None
        self.m_responce = None
        self.m_round = 0
        self.m_waitingResponse = False
        self.alive = True
        self.name = 'player'



    def ClearRaceHistory(self):
        self.m_history.clear()

    def SetReaderWriter(self, r, w):
        self.m_reader = r
        self.m_writer = w

    def GetMark(self):
        history = self.m_history.setdefault(self.m_curVersusPlayer, [])
        mark = 0
        for round, response, versusResponse in history:
            ret = (response, versusResponse)
            if ret == (ResponceOp.Cooperate, ResponceOp.Cooperate):
                mark += 3
            elif ret == (ResponceOp.Betry, ResponceOp.Betry):
                mark += 1
            elif ret == (ResponceOp.Betry, ResponceOp.Cooperate):
                mark += 5
            elif ret == (ResponceOp.Cooperate, ResponceOp.Betry):
                pass
        return mark

    def GetCurVersusPlayer(self):
        return self.m_curVersusPlayer

    async def NewRound(self):
        self.m_round += 1

    async def RoundEnd(self):
        history = self.m_history.setdefault(self.m_curVersusPlayer, [])
        history.append((self.m_round, self.GetResponse(), self.m_curVersusPlayer.GetResponse()))

    async def SetCurVersusPlayer(self, player):
        self.m_curVersusPlayer = player

    async def SetResponse(self, op):
        if not self.m_waitingResponse:
            await self.SendMsg("非我的回合，不接受指令!")
        self.m_responce = op

    def GetResponse(self):
        return self.m_responce

    async def WaitResponse(self, op):
        opstrs = {
            None: "无",
            ResponceOp.Cooperate: "合作",
            ResponceOp.Betry: "背叛"
        }
        await self.SendMsg(f"你的回合，对手上次的行动[{opstrs[op]}]; 你的行动(y:合作, n:背叛):")

        self.m_responce = None
        self.m_waitingResponse = True
        while self.m_responce is None:
            await asyncio.sleep(0.1)
        self.m_waitingResponse = False
        return self.m_responce

    async def FinishRace(self):
        await self.SendMsg(f"比赛结束！")

    async def SendMsg(self, msg):
        await SendMsg(self.m_writer, Protocol.Info, msg)


class ServerRaceMgr:
    def __init__(self):
        self.m_players: List[ServerPlayer] = []
        self.m_stopProp = 0.2
        self.m_playing = False

    async def Join(self, player):
        if self.m_playing:
            player.SendMsg("比赛正在进行中，无法加入!")
            return

        if player in self.m_players:
            player.SendMsg("已加入比赛，不能重复加入!")
            return
        self.m_players.append(player)

    def Playable(self):
        return not self.m_playing and len(self.m_players) % 2 == 0

    def GetRaces(self):
        self.m_players = [e for e in self.m_players if e.alive]
        players = self.m_players[:]
        random.shuffle(players)
        races = []
        while players:
            race = players.pop(), players.pop()
            races.append(race)
        return races

    async def Start(self):
        if not self.Playable():
            if not self.m_playing:
                await self.BroadcastMsg('人数不为偶数, 无法开始比赛！')
            return
        self.m_playing = True
        races = self.GetRaces()
        await self.RunRaces(races)
        await self.Stop()

    async def RunRaces(self, races):
        fs = []
        loop = asyncio.get_event_loop()

        for race in self.GetRaces():
            fut = loop.create_task(self.StartRace(race))
            fs.append(fut)

        await asyncio.wait(fs)

    def CheckStop(self, race):
        for p in race:
            if not p.alive:
                return False
        return random.random() < self.m_stopProp

    async def ClearRaceHistory(self, race):
        for p in race:
            p.ClearRaceHistory()

    async def SetAsVersusPlayer(self, race):
        p1, p2 = race
        await p1.SetCurVersusPlayer(p2)
        await p2.SetCurVersusPlayer(p1)

    def GetRandomSeqRacePlayer(self, race):
        cur_idx = random.randint(0, 1)
        next_idx = 1 - cur_idx
        cur_player: ServerPlayer = race[cur_idx]
        next_player:ServerPlayer = race[next_idx]
        return cur_player, next_player

    async def NewRound(self, race):
        for p in race:
            await p.NewRound()

    async def RoundEnd(self, race):
        for p in race:
            await p.RoundEnd()

    async def FinishRace(self, race):
        for p in race:
            await p.FinishRace()

    async def StartRace(self, race):
        await self.ClearRaceHistory(race)
        await self.SetAsVersusPlayer(race)
        cur_player, next_player = self.GetRandomSeqRacePlayer(race)

        op = None
        while not self.CheckStop(race):
            await self.NewRound(race)
            await cur_player.SetCurVersusPlayerResponce(op)
            op = await cur_player.WaitResponse()
            await next_player.SetCurVersusPlayerResponce(op)
            op = await next_player.WaitResponse()
            await self.RoundEnd(race)

        await self.FinishRace(race)

    async def Stop(self):
        self.m_playing = False
        marks = []
        for p in self.m_players:
            marks.append((p, p.GetMark()))
        marks.sort(key=lambda x: x[1])
        info = "排行榜:\n"
        info = info + "\n".join([f"{k.name}:\t [{v}]" for k, v in marks])

        for p in self.m_players:
            my_markinfo = f'我的得分: [{p.GetMark()}]\n'
            info = my_markinfo + info
            await SendMsg(p.m_writer, Protocol.Info, info)

    async def BroadcastMsg(self, msg):
        fs = []
        for p in self.m_players:
            if not p.alive:
                continue
            f = p.SendMsg(msg)
            fs.append(f)
        await asyncio.wait(fs)


class RaceServer:
    def __init__(self):
        self.m_race_mgr = ServerRaceMgr()

    def Start(self):
        self.m_race_mgr = ServerRaceMgr()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.StartServer())

    async def StartServer(self):
        server = await asyncio.start_server(self.ClientPlayerCb, g_Config.server_host, g_Config.server_port)
        addr = server.sockets[0].getsockname()
        print(f'RaceServer Serving on {addr}')
        async with server:
            await server.serve_forever()

    async def ClientPlayerCb(self, reader, writer):
        addr = writer.get_extra_info('peername')
        Log(f'Receive Connection from: {addr}')

        sp = ServerPlayer()
        sp.name = addr
        sp.SetReaderWriter(reader, writer)
        loop = asyncio.get_running_loop()
        while sp.alive:
            try:
                prot, data = await RcvMsg(reader)
            except:
                sp.alive = False
                return

            print(f"Received Protocol:{prot}, data: {data} from {addr!r}")
            if prot == Protocol.Join:
                await self.m_race_mgr.Join(sp)

            elif prot == Protocol.Start:
                 loop.create_task(self.m_race_mgr.Start())

            elif prot == Protocol.Response:
                await sp.SetResponse(data)
            elif prot == Protocol.Quit:
                sp.alive = False








