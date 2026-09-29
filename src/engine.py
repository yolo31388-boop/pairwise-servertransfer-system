"""转服移民系统 - 7个迁移事故已修复"""
import time
from dataclasses import dataclass, field

MIN_TRANSFER_LEVEL = 50
TRANSFER_COOLDOWN_SECONDS = 30 * 24 * 3600  # 30天冷却
MAX_CARRY_ITEMS = 100          # 携带物品总上限
MAX_RARE_ITEMS = 5             # 稀有物品携带上限, 超出需审核
RARE_RARITIES = ("rare", "epic", "legendary")
RANK_PROTECTION_SECONDS = 7 * 24 * 3600  # 转服排行榜保护期


@dataclass
class Player:
    pid: str
    level: int
    server: str
    name: str
    in_instance: bool = False
    in_battlefield: bool = False
    in_trade: bool = False
    in_safe_zone: bool = True


@dataclass
class Item:
    item_id: str
    name: str
    rarity: str = "common"
    count: int = 1


@dataclass
class Mail:
    mail_id: str
    subject: str = ""
    unread: bool = True
    server: str = ""


class ServerTransferSystem:
    def __init__(self, now=None):
        self.players: dict[str, Player] = {}
        self._now = now or time.time
        self.last_transfer: dict[str, float] = {}   # bug4: 记录上次转服时间
        self.friends: dict[str, dict[str, dict]] = {}  # pid -> {好友pid: {"server", "cross_server"}}
        self.guilds: dict[str, str] = {}            # pid -> 帮派id
        self.mails: dict[str, list[Mail]] = {}
        self.rankings: dict[str, dict[str, int]] = {}  # server -> {pid: 积分}
        self.rank_protection: dict[str, float] = {}    # bug7: 保护期截止时间
        self.pending_audits: list[dict] = []        # bug2: 稀有物品审核记录
        self.rename_offers: dict[str, str] = {}     # bug3: 待确认的改名机会

    # ---------- bug1: 角色状态检查 ----------
    def check_state(self, pid):
        """副本/战场/交易中不可转服, 且必须处于安全场景"""
        p = self.players[pid]
        if p.in_instance or p.in_battlefield or p.in_trade:
            return False
        return p.in_safe_zone

    # ---------- bug4: 时间冷却 + 等级双重条件 ----------
    def check_cooldown(self, pid):
        last = self.last_transfer.get(pid)
        if last is None:
            return True
        return self._now() - last >= TRANSFER_COOLDOWN_SECONDS

    def can_transfer(self, pid, target_server):
        p = self.players[pid]
        if p.server == target_server:
            return False
        if p.level < MIN_TRANSFER_LEVEL:
            return False
        if not self.check_state(pid):       # bug1
            return False
        if not self.check_cooldown(pid):    # bug4
            return False
        return True

    # ---------- bug2: 经济校验 ----------
    def check_economy(self, pid, items):
        """携带物品有总量上限; 稀有物品超限时转入人工审核, 防止经济冲击"""
        if sum(getattr(it, "count", 1) for it in items) > MAX_CARRY_ITEMS:
            return False
        rare = [it for it in items if getattr(it, "rarity", "common") in RARE_RARITIES]
        if len(rare) > MAX_RARE_ITEMS:
            self.pending_audits.append({
                "pid": pid,
                "rare_items": [it.name for it in rare],
                "status": "pending",
                "time": self._now(),
            })
            return False
        return True

    # ---------- bug3: 角色名冲突 ----------
    def check_name_conflict(self, pid, target_server):
        p = self.players[pid]
        return not any(
            q.server == target_server and q.name == p.name
            for q in self.players.values()
            if q.pid != pid
        )

    def resolve_name(self, pid, target_server):
        """冲突时自动生成带后缀的唯一名, 并给玩家一次改名机会"""
        p = self.players[pid]
        if self.check_name_conflict(pid, target_server):
            return p.name
        taken = {q.name for q in self.players.values() if q.server == target_server}
        suffix = 1
        while f"{p.name}#{suffix}" in taken:
            suffix += 1
        new_name = f"{p.name}#{suffix}"
        self.rename_offers[pid] = new_name  # 玩家可改用自选名
        return new_name

    # ---------- 主流程 ----------
    def transfer(self, pid, target_server, items=None, keep_read_mails=False):
        if not self.can_transfer(pid, target_server):
            return False
        if items is not None and not self.check_economy(pid, items):
            return False

        p = self.players[pid]
        old_server = p.server

        # bug3: 重名自动加后缀
        p.name = self.resolve_name(pid, target_server)
        p.server = target_server
        self.last_transfer[pid] = self._now()

        self._migrate_relations(pid, old_server, target_server)   # bug5
        self._migrate_mails(pid, target_server, keep_read_mails)  # bug6
        self._reset_ranking(pid, old_server)                      # bug7
        return True

    # ---------- bug5: 好友/帮派关系迁移规则 ----------
    def _migrate_relations(self, pid, old_server, target_server):
        # 好友: 保留但标记为跨服好友
        for rel in self.friends.get(pid, {}).values():
            rel["cross_server"] = True
        for friend_pid, rels in self.friends.items():
            if friend_pid != pid and pid in rels:
                rels[pid]["server"] = target_server
                rels[pid]["cross_server"] = True
        # 帮派: 不跨服, 转服即解除
        self.guilds.pop(pid, None)

    # ---------- bug6: 邮件迁移 ----------
    def _migrate_mails(self, pid, target_server, keep_read_mails):
        kept = []
        for mail in self.mails.get(pid, []):
            if mail.unread or keep_read_mails:
                mail.server = target_server  # 未读邮件随角色迁移
                kept.append(mail)
            # 已读且选择不保留的邮件留在原服归档, 不再随角色显示
        self.mails[pid] = kept

    # ---------- bug7: 排行榜重置 + 保护期 ----------
    def _reset_ranking(self, pid, old_server):
        self.rankings.get(old_server, {}).pop(pid, None)  # 清掉原服排名
        # 新服从零开始: 不写入任何排名数据, 并进入保护期
        self.rank_protection[pid] = self._now() + RANK_PROTECTION_SECONDS

    def can_enter_ranking(self, pid):
        until = self.rank_protection.get(pid)
        return until is None or self._now() >= until
