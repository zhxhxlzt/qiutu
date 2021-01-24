import asyncio
import random
import json
import struct
import threading
from typing import List
import sys


def Log(*msg):
    print(*msg)


class Config:
    def __init__(self):
        self.server_host = "45.67.54.238"
        self.server_port = 52314
        self.stop_prop = 0.15
        self.debug = False

    def DebugMode(self):
        self.server_host = "localhost"

    def AliyunServer(self):
        self.server_host = "172.21.87.68"

    def ApplyClientMode(self):
        self.server_host = "47.115.57.161"


g_Config = Config()
print('platform:', sys.platform)
if g_Config.debug:
    g_Config.DebugMode()
elif 'win' in sys.platform or 'mac' in sys.platform:
    g_Config.ApplyClientMode()
else:
    g_Config.AliyunServer()


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
    Talk = 9
    Name = 10


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
        Log("成功连接！")

    async def Join(self):
        await SendMsg(self.m_writer, Protocol.Join, '')
        Log('成功加入比赛队列！')

    async def Start(self):
        await SendMsg(self.m_writer, Protocol.Start, '')
        Log("申请开始比赛...")

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

    async def Talk(self, msg):
        await SendMsg(self.m_writer, Protocol.Talk, msg)

    async def SetName(self, name):
        await SendMsg(self.m_writer, Protocol.Name, name)


class RaceClient:
    def __init__(self):
        self.m_player = ClientPlayer()
        self.m_cmd = ''
        self.m_cmdLock = threading.Lock()
        self.m_cmdThread = None
        self.m_close = False

    def Start(self):
        self.m_cmdThread = threading.Thread(target=self.UserCmd)
        self.m_cmdThread.setDaemon(True)
        self.m_cmdThread.start()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._Start())

    def Help(self):
        Log("0、输入help显示此帮助信息")
        Log("1、以msg开头来发送信息，如输入 'msg 你好!'，则对方收到 '你好!'")
        Log("2、以name开关来设置昵称，如输入 'name 小皮蛋'，则设置昵称为 小皮蛋")
        Log("3、输入2申请开始比赛")
        Log('''
【重复囚徒困境 规则说明】
双方轮流行动，可以选择合作或背叛，根据双方的行动来获取得分。
我方合作，对方合作，各得3分。
我方合作，对方背叛，只有背叛方得5分，反之类推。
我方背叛，对方背叛，各得1分。
        ''')

    async def _Start(self):
        self.Help()
        await self.m_player.Connect()
        await self.m_player.Join()
        loop = asyncio.get_running_loop()
        loop.create_task(self.ListenServer())
        while not self.m_close:
            await self.ProcessCmd()
            await asyncio.sleep(0.1)
        print('已断开连接！')

    async def ListenServer(self):
        while not self.m_close:
            try:
                proto, data = await RcvMsg(self.m_player.m_reader)
            except:
                self.m_close = True
                return
            if proto == Protocol.Info:
                Log(data)

    async def ProcessCmd(self):
        cmd = self.FetchCmd()
        if not cmd:
            return

        if cmd == str(Protocol.Start):
            await self.m_player.Start()

        elif cmd == "y":
            await self.m_player.Cooperate()

        elif cmd == "n":
            await self.m_player.Betray()
        elif cmd == "-1":
            await self.m_player.Quit()
        elif cmd.startswith("msg"):
            msg = cmd.strip("msg")
            await self.m_player.Talk(msg.strip())
        elif cmd.startswith('name'):
            msg = cmd.strip('name')
            await self.m_player.SetName(msg.strip())
        elif cmd.startswith('help'):
            self.Help()

    def UserCmd(self):
        while not self.m_close:
            cmd = input()
            with self.m_cmdLock:
                self.m_cmd = cmd

    def FetchCmd(self):
        if not self.m_cmd:
            return ""
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
            await self.SendMsg("目前是对手的回合，不接受行动指令!")
        self.m_responce = op

    def GetResponse(self):
        return self.m_responce

    async def WaitResponse(self, op):
        opstrs = {
            None: "无",
            ResponceOp.Cooperate: "合作",
            ResponceOp.Betry: "背叛"
        }
        await self.SendMsg(f"回合[ {self.m_round} ]，对手的行动:[ {opstrs[op]} ]; 开始你的行动(y:合作, n:背叛):")

        self.m_responce = None
        self.m_waitingResponse = True
        while self.m_responce is None:
            await asyncio.sleep(0.1)
        await self.SendMsg(f'你的行动是[{opstrs[self.m_responce]}], 等待对手行动...')
        self.m_waitingResponse = False
        return self.m_responce

    async def Close(self):
        self.m_writer.close()

    async def FinishRace(self):
        await self.SendMsg(f"比赛结束！")

    async def SendMsg(self, msg):
        await SendMsg(self.m_writer, Protocol.Info, msg)


class ServerRaceMgr:
    def __init__(self):
        self.m_players: List[ServerPlayer] = []
        self.m_playing = False

    async def Join(self, player):
        if player in self.m_players:
            await player.SendMsg("已加入比赛，不能重复加入!")
            return

        self.m_players.append(player)

        info = f"当前人数: {len(self.m_players)}"
        if self.m_playing:
            await player.SendMsg(info + f", 比赛正在进行中, 请等待!")
            return

        await self.BroadcastMsg(info + ', 按2申请开始比赛！')

    async def Remove(self, player):
        if player in self.m_players:
            self.m_players.remove(player)

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
        if self.m_playing:
            return
        if len(self.m_players) % 2 != 0:
            await self.BroadcastMsg(f'当前人数{len(self.m_players)}不为偶数, 无法开始比赛！')
            return
        self.m_playing = True
        races = self.GetRaces()
        await self.RunRaces(races)
        await self.Stop()

    async def RunRaces(self, races):
        fs = []
        loop = asyncio.get_event_loop()

        for race in races:
            fut = loop.create_task(self.StartRace(race))
            fs.append(fut)

        await asyncio.wait(fs)

    def CheckStop(self, race):
        for p in race:
            if not p.alive:
                return False
        return random.random() < g_Config.stop_prop

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
        next_player: ServerPlayer = race[next_idx]
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

        await self.BroadcastMsg("比赛开始！", race)
        op = None
        await next_player.SendMsg("等待对手行动...")
        minRound = 3  # 至少3个回合吧
        while minRound > 0 or not self.CheckStop(race):
            minRound -= 1
            await self.NewRound(race)
            op = await cur_player.WaitResponse(op)
            op = await next_player.WaitResponse(op)
            await self.RoundEnd(race)

        await self.FinishRace(race)

    async def Stop(self):
        self.m_playing = False
        marks = []
        for p in self.m_players:
            marks.append((p, p.GetMark()))
        marks.sort(key=lambda x: x[1])
        info = "排行榜:\n"
        info = info + "\n".join([f"选手: {k.name}\t 得分: [{v}]" for k, v in marks])

        for p in self.m_players:
            my_info = f'我的得分: [{p.GetMark()}]\n'
            await SendMsg(p.m_writer, Protocol.Info, my_info + info)

    async def BroadcastMsg(self, msg, players=None):
        if players is None:
            players = self.m_players
        fs = []
        for p in players:
            if not p.alive:
                continue
            f = p.SendMsg(msg)
            fs.append(f)
        if fs:
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
        sp.name = str(addr)
        sp.SetReaderWriter(reader, writer)
        loop = asyncio.get_running_loop()
        while sp.alive:
            try:
                prot, data = await RcvMsg(reader)
            except:
                sp.alive = False
                await self.m_race_mgr.Remove(sp)
                return

            print(f"Received Protocol:{prot}, data: {data} from {addr!r}")
            if prot == Protocol.Join:
                await self.m_race_mgr.Join(sp)

            elif prot == Protocol.Start:
                if self.m_race_mgr.m_playing:
                    await sp.SendMsg('不能申请开始比赛，比赛正在进行中！')
                loop.create_task(self.m_race_mgr.Start())

            elif prot == Protocol.Response:
                if not self.m_race_mgr.m_playing:
                    await sp.SendMsg('未开始比赛！')
                else:
                    await sp.SetResponse(data)
            elif prot == Protocol.Quit:
                sp.alive = False

            elif prot == Protocol.Talk:
                players = self.m_race_mgr.m_players[:]
                players.remove(sp)
                msg = sp.name + "说: " + data
                await self.m_race_mgr.BroadcastMsg(msg, players)
            elif prot == Protocol.Name:
                names = set([e.name for e in self.m_race_mgr.m_players])
                if data not in names:
                    sp.name = data
                    await sp.SendMsg(f"成功设置名字: [{data}]")
                else:
                    await sp.SendMsg(f"名字已被占用！")
