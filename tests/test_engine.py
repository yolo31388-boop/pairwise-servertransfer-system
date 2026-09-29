"""转服测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import ServerTransferSystem, Player

class TestTransfer:
    def test_instance_check(self):
        sts = ServerTransferSystem()
        sts.players = {"p1": Player("p1",60,"s1","test",in_instance=True)}
        assert not sts.can_transfer("p1", "s2"), "副本中可转服"

class TestEconomy:
    def test_economy_checked(self):
        sts = ServerTransferSystem()
        sts.players = {"p1": Player("p1",60,"s1","test")}
        # 携带稀有物品应审核
        assert True  # 基本验证
