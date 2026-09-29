"""转服移民系统"""
import time
from dataclasses import dataclass, field

MIN_LEVEL = 50
COOLDOWN_SECONDS = 30 * 24 * 3600          # fix4: 30天时间冷却
ITEM_COUNT_LIMIT = 200                     # fix2: 携带物品总数上限
RARE_ITEM_LIMIT = 10                       # fix2: 稀有物品携带上限
RANKING_PROTECT_SECONDS = 7 * 24 * 3600    # fix7: 新服排行榜保护期


@dataclass
class Player:
    pid: str
    level: int
    server: str
    name: str
    in_instance: bool = False
    in_battleground: bool = False
    in_trade: bool = False


class ServerTransferSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.cooldown: dict[str, float] = {}      # fix4: pid -> 上次转服时间戳
        self.friends: dict[str, list] = {}        # pid -> 好友pid列表
        self.guilds: dict[str, str] = {}          # pid -> 帮派名
        self.cross_server_friends: dict[str, list] = {}  # fix5: 跨服好友
        self.mails: dict[str, list] = {}          # pid -> 邮件列表
        self.names: dict[str, set] = {}           # server -> 已占用角色名
        self.rankings: dict[str, dict] = {}       # server -> {pid: score}
        self.ranking_protection: dict[str, float] = {}   # fix7: pid -> 保护期截止

    def _unsafe_state(self, p: Player):
        # fix1: 副本/战场/交易中禁止转服
        if p.in_instance:
            return "in_instance"
        if p.in_battleground:
            return "in_battleground"
        if p.in_trade:
            return "in_trade"
        return None

    def can_transfer(self, pid, target_server, now=None):
        p = self.players[pid]
        if p.server == target_server:
            return False
        if self._unsafe_state(p):                 # fix1: 角色状态检查
            return False
        if p.level < MIN_LEVEL:
            return False
        now = time.time() if now is None else now
        last = self.cooldown.get(pid)
        if last is not None and now - last < COOLDOWN_SECONDS:  # fix4: 时间冷却
            return False
        return True

    def check_economy(self, pid, items):
        # fix2: 物品总数上限 + 稀有物品审核，防止经济冲击
        if len(items) > ITEM_COUNT_LIMIT:
            return False
        rare = [i for i in items if i.get("rare") or i.get("rarity") in ("rare", "epic", "legendary")]
        if len(rare) > RARE_ITEM_LIMIT:
            return False
        return True

    def check_name_conflict(self, pid, target_server):
        # fix3: 重名时自动生成不冲突的后缀名
        p = self.players[pid]
        taken = self.names.setdefault(target_server, set())
        if p.name not in taken:
            return p.name
        suffix = 1
        while f"{p.name}_{suffix}" in taken:
            suffix += 1
        return f"{p.name}_{suffix}"

    def transfer(self, pid, target_server, items=None, now=None):
        p = self.players[pid]
        if not self.can_transfer(pid, target_server, now=now):
            return False
        if items is not None and not self.check_economy(pid, items):
            return False
        now = time.time() if now is None else now

        # fix3: 落地前解决角色名冲突
        p.name = self.check_name_conflict(pid, target_server)
        self.names.setdefault(target_server, set()).add(p.name)
        self.names.get(p.server, set()).discard(p.name)

        # fix5: 好友/帮派关系标记为跨服，不再混入原服列表
        for fid in self.friends.get(pid, []):
            self.cross_server_friends.setdefault(pid, []).append(fid)
            if pid in self.friends.get(fid, []):
                self.friends[fid].remove(pid)
                self.cross_server_friends.setdefault(fid, []).append(pid)
        self.friends[pid] = []
        self.guilds.pop(pid, None)  # 帮派关系解除，需在新服重新加入

        # fix6: 未读邮件随角色迁移，已读邮件留在原服
        mails = self.mails.get(pid, [])
        self.mails[pid] = [m for m in mails if not m.get("read")]

        # fix7: 原服排名清除，新服从零开始并进入保护期
        self.rankings.get(p.server, {}).pop(pid, None)
        self.rankings.setdefault(target_server, {})[pid] = 0
        self.ranking_protection[pid] = now + RANKING_PROTECT_SECONDS

        p.server = target_server
        self.cooldown[pid] = now  # fix4: 记录转服时间
        return True
