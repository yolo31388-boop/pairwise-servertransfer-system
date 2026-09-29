"""转服移民 - 带7个bug"""
from dataclasses import dataclass, field

@dataclass class Player:
    pid: str
    level: int
    server: str
    name: str
    in_instance: bool = False

class ServerTransferSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.cooldown = {}  # bug4: 只看等级
        self.friends = {}
        self.mails = {}

    def can_transfer(self, pid, target_server):
        p = self.players[pid]
        # bug1: 不检查角色状态
        return p.level >= 50

    def check_economy(self, pid, items):
        # bug2: 不做经济校验
        return True

    def check_name_conflict(self, pid, target_server):
        # bug3: 不处理重名
        return True

    def transfer(self, pid, target_server):
        p = self.players[pid]
        p.server = target_server
        # bug5: 好友关系不处理
        # bug6: 邮件不迁移
        # bug7: 排行榜不重置
        return True
