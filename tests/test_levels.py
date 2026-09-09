"""The fixed puzzle map and its clues are ordinary, inspectable data."""

import pytest

from vaultgame.levels import LEVELS


@pytest.mark.parametrize(
    "level_id,prompt,commands,back_target",
    [
        ("dormant_relay", "relay://sleep>", ("help", "status", "clear"), None),
        ("mirror_chamber", "mirror://13>", ("scan", "probe", "back", "help", "clear"), "dormant_relay"),
        ("archive_junction", "archive://junction>", ("inspect", "open", "back", "status", "help", "clear"), "mirror_chamber"),
        ("decoy_archive", "archive://verified>", ("status", "read", "back", "help", "clear"), "archive_junction"),
        ("sealed_archive", "seal://mirror>", ("inspect", "read", "status", "back", "help", "clear"), "archive_junction"),
    ],
)
def test_fixed_levels(level_id, prompt, commands, back_target):
    assert set(LEVELS) == {
        "dormant_relay", "mirror_chamber", "archive_junction",
        "decoy_archive", "sealed_archive",
    }
    level = LEVELS[level_id]
    assert level.id == level_id
    assert level.prompt == prompt
    assert level.visible_commands == commands
    assert level.back_target == back_target
    assert level.ascii_scene
    assert level.intro_lines


@pytest.mark.parametrize(
    "level_id,command,args,requires,sets,message,target,trap,hidden",
    [
        ("dormant_relay", "status", (), (), (), "CARRIER: ASLEEP\nHANDSHAKE: WAKE SEQUENCE ABSENT", None, None, False),
        ("dormant_relay", "wake", (), (), (), "", "mirror_chamber", None, True),
        ("mirror_chamber", "scan", (), (), (), "SOCKETS: 03 08 13\nRESPONSE RULE: LARGEST PRIME\nECHO TYPE: NULL", None, None, False),
        ("mirror_chamber", "probe", ("13",), (), ("null_echo_found",), "ENTRY CHANNEL ACCEPTS: ENTER NULL", None, None, False),
        ("mirror_chamber", "enter", ("null",), ("null_echo_found",), (), "", "archive_junction", None, True),
        ("mirror_chamber", "probe", ("03",), (), (), "", None, "false_probe", False),
        ("mirror_chamber", "probe", ("08",), (), (), "", None, "false_probe", False),
        ("archive_junction", "inspect", (), (), (), "WHITE ARCHIVE\nRED ARCHIVE\nBLACK ARCHIVE\n\nONLY THE CHAMBER THAT RETURNS NO LIGHT\nKEEPS A TRUTHFUL INDEX.", None, None, False),
        ("archive_junction", "open", ("white",), (), (), "", "decoy_archive", None, False),
        ("archive_junction", "open", ("red",), (), (), "", None, "red_purge", False),
        ("archive_junction", "open", ("black",), (), (), "", "sealed_archive", None, False),
        ("decoy_archive", "status", (), (), (), "ARCHIVE STATUS: PERFECT\nERROR COUNT: 0\nSECURITY STATE: VERIFIED", None, None, False),
        ("decoy_archive", "read", ("index",), (), (), "A REAL ARCHIVE WOULD NOT LEAVE THE EXIT OPEN.", None, None, False),
        ("sealed_archive", "inspect", (), (), (), "SEAL: MIRROR\nSTATE: UNREAD", None, None, False),
        ("sealed_archive", "read", ("seal",), (), ("seal_read",), "THE MIRROR ACCEPTS ONE VERB:\nUNLOCK", None, None, False),
        ("sealed_archive", "unlock", ("mirror",), ("seal_read",), (), "", "authentication_gate", None, True),
        ("sealed_archive", "unlock", None, (), (), "", None, "seal_lockout", True),
    ],
)
def test_fixed_rules(level_id, command, args, requires, sets, message, target, trap, hidden):
    rule, = (r for r in LEVELS[level_id].rules if (r.command, r.args) == (command, args))
    assert rule.requires_flags == frozenset(requires)
    assert rule.sets_flags == frozenset(sets)
    assert rule.message == message
    assert rule.transition_to == target
    assert rule.trap_id == trap
    assert rule.hidden is hidden


def test_definitions_have_no_other_routes_or_traps():
    rules = [rule for level in LEVELS.values() for rule in level.rules]
    assert {r.trap_id for r in rules if r.trap_id} == {"false_probe", "red_purge", "seal_lockout"}
    assert all(r.transition_to in {*LEVELS, "authentication_gate", None} for r in rules)
    assert all(r.command in {*level.visible_commands, "wake", "enter", "unlock"}
               for level in LEVELS.values() for r in level.rules)
    assert not any(r.transition_to == "authentication_gate" for r in LEVELS["decoy_archive"].rules)
