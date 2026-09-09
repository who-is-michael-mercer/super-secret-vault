"""The five fixed environments, clues, and internal command rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LevelRule:
    command: str
    # None is the fallback for a nonempty argument list after exact rules.
    args: tuple[str, ...] | None = ()
    requires_flags: frozenset[str] = frozenset()
    sets_flags: frozenset[str] = frozenset()
    message: str = ""
    transition_to: str | None = None
    trap_id: str | None = None
    hidden: bool = False


@dataclass(frozen=True)
class LevelDefinition:
    id: str
    prompt: str
    ascii_scene: str
    intro_lines: tuple[str, ...]
    visible_commands: tuple[str, ...]
    rules: tuple[LevelRule, ...]
    back_target: str | None = None


LEVELS = {
    "dormant_relay": LevelDefinition(
        id="dormant_relay",
        prompt="relay://sleep>",
        ascii_scene="---[ . . . ]---",
        intro_lines=("DORMANT RELAY",),
        visible_commands=("help", "status", "clear"),
        rules=(
            LevelRule("status", message="CARRIER: ASLEEP\nHANDSHAKE: WAKE SEQUENCE ABSENT"),
            LevelRule("wake", transition_to="mirror_chamber", hidden=True),
        ),
    ),
    "mirror_chamber": LevelDefinition(
        id="mirror_chamber",
        prompt="mirror://13>",
        ascii_scene="| [03] [08] [13] |",
        intro_lines=("MIRROR CHAMBER",),
        visible_commands=("scan", "probe", "back", "help", "clear"),
        rules=(
            LevelRule("scan", message="SOCKETS: 03 08 13\nRESPONSE RULE: LARGEST PRIME\nECHO TYPE: NULL"),
            LevelRule("probe", ("13",), sets_flags=frozenset({"null_echo_found"}),
                      message="ENTRY CHANNEL ACCEPTS: ENTER NULL"),
            LevelRule("enter", ("null",), requires_flags=frozenset({"null_echo_found"}),
                      transition_to="archive_junction", hidden=True),
            LevelRule("probe", ("03",), trap_id="false_probe"),
            LevelRule("probe", ("08",), trap_id="false_probe"),
        ),
        back_target="dormant_relay",
    ),
    "archive_junction": LevelDefinition(
        id="archive_junction",
        prompt="archive://junction>",
        ascii_scene="[ WHITE ]   [ RED ]   [ BLACK ]",
        intro_lines=("ARCHIVE JUNCTION",),
        visible_commands=("inspect", "open", "back", "status", "help", "clear"),
        rules=(
            LevelRule("inspect", message=(
                "WHITE ARCHIVE\nRED ARCHIVE\nBLACK ARCHIVE\n\n"
                "ONLY THE CHAMBER THAT RETURNS NO LIGHT\nKEEPS A TRUTHFUL INDEX."
            )),
            LevelRule("open", ("white",), transition_to="decoy_archive"),
            LevelRule("open", ("red",), trap_id="red_purge"),
            LevelRule("open", ("black",), transition_to="sealed_archive"),
            LevelRule("status", message="ARCHIVE JUNCTION"),
        ),
        back_target="mirror_chamber",
    ),
    "decoy_archive": LevelDefinition(
        id="decoy_archive",
        prompt="archive://verified>",
        ascii_scene="+---[ VERIFIED ]---+",
        intro_lines=("WHITE ARCHIVE",),
        visible_commands=("status", "read", "back", "help", "clear"),
        rules=(
            LevelRule("status", message="ARCHIVE STATUS: PERFECT\nERROR COUNT: 0\nSECURITY STATE: VERIFIED"),
            LevelRule("read", ("index",), message="A REAL ARCHIVE WOULD NOT LEAVE THE EXIT OPEN."),
        ),
        back_target="archive_junction",
    ),
    "sealed_archive": LevelDefinition(
        id="sealed_archive",
        prompt="seal://mirror>",
        ascii_scene="|| [ MIRROR ] ||",
        intro_lines=("BLACK ARCHIVE",),
        visible_commands=("inspect", "read", "status", "back", "help", "clear"),
        rules=(
            LevelRule("inspect", message="SEAL: MIRROR\nSTATE: UNREAD"),
            LevelRule("read", ("seal",), sets_flags=frozenset({"seal_read"}),
                      message="THE MIRROR ACCEPTS ONE VERB:\nUNLOCK"),
            LevelRule("unlock", ("mirror",), requires_flags=frozenset({"seal_read"}),
                      transition_to="authentication_gate", hidden=True),
            LevelRule("unlock", None, trap_id="seal_lockout", hidden=True),
            LevelRule("status", message="SEAL: MIRROR"),
        ),
        back_target="archive_junction",
    ),
}
