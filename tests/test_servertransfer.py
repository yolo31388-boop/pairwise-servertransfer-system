"""转服移民系统测试 - 覆盖7个迁移事故"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.engine import (
    Item,
    Mail,
    Player,
    ServerTransferSystem,
    TRANSFER_COOLDOWN_SECONDS,
)


def fresh_system():
    sts = ServerTransferSystem(now=lambda: fresh_system.now)
    return sts


fresh_system.now = 1_000_000.0


class TestStateCheck:
    def test_instance_battlefield_trade_blocked(self):
        sts = fresh_system()
        sts.players = {
            "p1": Player("p1", 60, "s1", "a", in_instance=True),
            "p2": Player("p2", 60, "s1", "b", in_battlefield=True),
            "p3": Player("p3", 60, "s1", "c", in_trade=True),
            "p4": Player("p4", 60, "s1", "d", in_safe_zone=False),
        }
        for pid in ("p1", "p2", "p3", "p4"):
            assert not sts.can_transfer(pid, "s2"), f"{pid} 状态不满足仍可转服"

    def test_safe_idle_player_allowed(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        assert sts.can_transfer("p1", "s2")


class TestEconomy:
    def test_carry_limit_and_rare_audit(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        too_many = [Item(f"i{i}", f"item{i}") for i in range(101)]
        assert not sts.check_economy("p1", too_many), "超携带上限未拦截"
        rare = [Item(f"r{i}", f"rare{i}", rarity="epic") for i in range(6)]
        assert not sts.check_economy("p1", rare), "稀有物品未进审核"
        assert sts.pending_audits, "未生成审核记录"
        assert sts.check_economy("p1", [Item("x", "普通")])


class TestNameConflict:
    def test_conflict_gets_suffix_and_rename_offer(self):
        sts = fresh_system()
        sts.players = {
            "p1": Player("p1", 60, "s1", "hero"),
            "p2": Player("p2", 60, "s2", "hero"),
        }
        assert not sts.check_name_conflict("p1", "s2")
        assert sts.transfer("p1", "s2")
        assert sts.players["p1"].name != "hero"
        assert sts.players["p1"].name.startswith("hero#")
        assert "p1" in sts.rename_offers, "未提供改名机会"


class TestCooldown:
    def test_time_cooldown_and_level(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        assert sts.transfer("p1", "s2")
        assert not sts.can_transfer("p1", "s3"), "冷却期内可再次转服"
        fresh_system.now += TRANSFER_COOLDOWN_SECONDS + 1
        assert sts.can_transfer("p1", "s3"), "冷却结束仍不可转服"
        sts.players["p1"].level = 10
        assert not sts.can_transfer("p1", "s3"), "等级不足仍可转服"


class TestRelations:
    def test_friends_marked_cross_server_and_guild_released(self):
        sts = fresh_system()
        sts.players = {
            "p1": Player("p1", 60, "s1", "a"),
            "p2": Player("p2", 60, "s1", "b"),
        }
        sts.friends = {
            "p1": {"p2": {"server": "s1", "cross_server": False}},
            "p2": {"p1": {"server": "s1", "cross_server": False}},
        }
        sts.guilds = {"p1": "g1"}
        assert sts.transfer("p1", "s2")
        assert sts.friends["p1"]["p2"]["cross_server"]
        assert sts.friends["p2"]["p1"]["cross_server"]
        assert sts.friends["p2"]["p1"]["server"] == "s2"
        assert "p1" not in sts.guilds, "帮派关系未解除"


class TestMails:
    def test_unread_mails_migrate_read_optional(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        sts.mails = {"p1": [
            Mail("m1", "未读1", unread=True, server="s1"),
            Mail("m2", "已读1", unread=False, server="s1"),
        ]}
        assert sts.transfer("p1", "s2")
        remaining = sts.mails["p1"]
        assert [m.mail_id for m in remaining] == ["m1"], "未读邮件丢失或已读邮件未归档"
        assert remaining[0].server == "s2"

    def test_read_mails_kept_when_requested(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        sts.mails = {"p1": [Mail("m2", "已读", unread=False, server="s1")]}
        assert sts.transfer("p1", "s2", keep_read_mails=True)
        assert len(sts.mails["p1"]) == 1


class TestRanking:
    def test_ranking_reset_with_protection(self):
        sts = fresh_system()
        sts.players = {"p1": Player("p1", 60, "s1", "a")}
        sts.rankings = {"s1": {"p1": 9999}, "s2": {"other": 100}}
        assert sts.transfer("p1", "s2")
        assert "p1" not in sts.rankings["s1"], "原服排名未清除"
        assert "p1" not in sts.rankings["s2"], "新服排名未从零开始"
        assert not sts.can_enter_ranking("p1"), "保护期内可上榜"
