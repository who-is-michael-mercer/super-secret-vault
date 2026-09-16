"""Fixed relay interfaces and pseudo-resources; never a filesystem or shell."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LevelRule:
    command: str
    # None matches a nonempty argument list only after exact rules.
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


COMMON = ("help", "clear", "status", "pwd", "ls", "cat")

LEVELS = {
    "relay_root": LevelDefinition(
        "relay_root", "relay0:/proc/relay>", "--[ relay0 ]--",
        ("relay0: carrier detected",), COMMON + ("connect",), (
            LevelRule("status", message="relay0: carrier detected\nbus: online\nroute: unresolved"),
            LevelRule("ls", message="interfaces  relay.conf"),
            LevelRule("cat", ("interfaces",), message="bus          device interface\ndiagnostics  telemetry interface"),
            LevelRule("cat", ("relay.conf",), message="node=relay0\ntransport=local\ninterfaces=bus,diagnostics"),
            LevelRule("connect", ("bus",), transition_to="device_bus"),
            LevelRule("connect", ("diagnostics",), transition_to="diagnostics"),
        ),
    ),
    "device_bus": LevelDefinition(
        "device_bus", "relay0:/dev/bus>", "--[ bus0 | mux0 ]--",
        ("bus0: interface attached",), COMMON + ("scan", "route", "back"), (
            LevelRule("status", requires_flags=frozenset({"bus_scanned"}), message="bus0: online\nmux0: enumerated"),
            LevelRule("status", message="bus0: online\nmux0: enumeration pending"),
            LevelRule("ls", message="devices  mux.conf"),
            LevelRule("cat", ("devices",), message="mux0  route multiplexer\nscan: enumeration available"),
            LevelRule("cat", ("mux.conf",), message="table=routes\nformat=numeric\nread_requires=enumeration"),
            LevelRule("scan", sets_flags=frozenset({"bus_scanned"}),
                      message="mux0: enumeration complete\nroute -n: table available"),
            LevelRule("route", ("-n",), requires_flags=frozenset({"bus_scanned"}), transition_to="route_table"),
        ), "relay_root",
    ),
    "route_table": LevelDefinition(
        "route_table", "relay0:/proc/routes>", "--[ 03 | 08 | 13 ]--",
        ("route: numeric table loaded", "03  closed\n08  closed\n13  listening"),
        COMMON + ("route", "probe", "back"), (
            LevelRule("status", requires_flags=frozenset({"route_verified"}), message="mux0: ready\nroute13: verified"),
            LevelRule("status", message="mux0: ready\nroute13: unverified"),
            LevelRule("ls", message="routes  transport.conf"),
            LevelRule("route", ("-n",), message="03  closed\n08  closed\n13  listening"),
            LevelRule("cat", ("routes",), message="03  closed\n08  closed\n13  listening"),
            LevelRule("cat", ("transport.conf",), message="probe: endpoint verification\nconnect: verified endpoints only"),
            LevelRule("probe", ("13",), sets_flags=frozenset({"route_verified"}),
                      message="route13: endpoint=null\nstate: listening\ncarrier: stable\nconnect: available"),
            LevelRule("connect", ("13",), requires_flags=frozenset({"route_verified"}),
                      transition_to="null_link", hidden=True),
            LevelRule("probe", ("03",), trap_id="false_probe"),
            LevelRule("probe", ("08",), trap_id="false_probe"),
            LevelRule("connect", None, trap_id="false_probe", hidden=True),
        ), "device_bus",
    ),
    "null_link": LevelDefinition(
        "null_link", "route13:/link/null>", "--[ route13 > null ]--",
        ("route13: link established",), COMMON + ("mount", "back"), (
            LevelRule("status", message="route13: carrier stable\narchive0: unmounted"),
            LevelRule("ls", message="mounts  link.log"),
            LevelRule("cat", ("mounts",), message="archive0  archive bus  available"),
            LevelRule("cat", ("link.log",), message="rx=0\ntx=0\ncarrier=stable\narchive0: mount request pending"),
            LevelRule("mount", ("archive0",), transition_to="archive_bus"),
        ), "route_table",
    ),
    "archive_bus": LevelDefinition(
        "archive_bus", "archive0:/mnt>", "--[ white | red | black ]--",
        ("archive0: mount table available",), COMMON + ("mount", "umount", "back"), (
            LevelRule("status", message="archive0: online\nwhite  ro  clean\nred    rw  degraded\nblack  ro  sealed"),
            LevelRule("ls", message="mounts"),
            LevelRule("cat", ("mounts",), message="white  public index\nred    maintenance volume\nblack  sealed volume"),
            LevelRule("mount", ("white",), transition_to="white_archive"),
            LevelRule("mount", ("red",), transition_to="red_maintenance"),
            LevelRule("mount", ("black",), transition_to="black_archive"),
            LevelRule("umount", ("archive0",), transition_to="null_link"),
        ), "null_link",
    ),
    "diagnostics": LevelDefinition(
        "diagnostics", "relay0:/var/diag>", "--[ telemetry ]--",
        ("diag0: retained records available",), COMMON + ("back",), (
            LevelRule("status", message="diag0: read-only\ncarrier: 1\nretries: 08\nclock: unsynchronized"),
            LevelRule("ls", message="relay.log  history  telemetry"),
            LevelRule("cat", ("relay.log",), message="mux0: enumeration invalidated\nroute03: refused\nroute08: refused\nroute13: carrier retained"),
            LevelRule("cat", ("history",), message="archive0: white index rebuilt\narchive0: red journal detached\nsealctl: external keyring unchanged"),
            LevelRule("cat", ("telemetry",), message="bus0 rx=0000 tx=0000\nroute13 carrier=stable\narchive0 heartbeat=--"),
        ), "relay_root",
    ),
    "white_archive": LevelDefinition(
        "white_archive", "archive0:/mnt/white>", "--[ white : ro ]--",
        ("white: mounted read-only",), COMMON + ("umount", "back"), (
            LevelRule("status", message="index: clean\nerrors: 0\nchecks: complete\nretention: standard"),
            LevelRule("ls", message="index  readme  inventory"),
            LevelRule("cat", ("index",), message="readme     current\ninventory  current\nrecords: 2"),
            LevelRule("cat", ("readme",), message="standard archive\nlast audit: complete\nexceptions: none"),
            LevelRule("cat", ("inventory",), message="forms: 0\nnotices: 0\npending: 0"),
            LevelRule("umount", ("white",), transition_to="archive_bus"),
        ), "archive_bus",
    ),
    "red_maintenance": LevelDefinition(
        "red_maintenance", "archive0:/mnt/red>", "--[ red : degraded ]--",
        ("red: journal unstable",), COMMON + ("probe", "mount", "umount", "back"), (
            LevelRule("status", message="journal: inconsistent\nmount: read-only\nrecovery: unsafe"),
            LevelRule("ls", message="journal  maintenance.conf"),
            LevelRule("cat", ("journal",), message="metadata: sequence mismatch\nwriter: detached\nprobe journal: integrity check available"),
            LevelRule("cat", ("maintenance.conf",), message="volume=red\nremount=rw\nwrite_barrier=failed"),
            LevelRule("probe", ("journal",), trap_id="false_probe"),
            LevelRule("mount", ("-o", "rw", "red"), trap_id="red_purge"),
            LevelRule("umount", ("red",), transition_to="archive_bus"),
        ), "archive_bus",
    ),
    "black_archive": LevelDefinition(
        "black_archive", "archive0:/mnt/black>", "--[ black : sealed ]--",
        ("black: sealed volume attached",), COMMON + ("connect", "umount", "back"), (
            LevelRule("status", requires_flags=frozenset({"controller_found"}), message="black: sealed\ncontroller: available"),
            LevelRule("status", message="black: sealed\nindex: unavailable\ncontroller: detached"),
            LevelRule("ls", message="controller  seal.meta"),
            LevelRule("cat", ("controller",), sets_flags=frozenset({"controller_found"}),
                      message="device=sealctl\nchannel=local\nconnect=available"),
            LevelRule("cat", ("seal.meta",), message="format=1\nkeyring=external\ncontroller=sealctl"),
            LevelRule("connect", ("sealctl",), requires_flags=frozenset({"controller_found"}), transition_to="seal_controller"),
            LevelRule("umount", ("black",), transition_to="archive_bus"),
        ), "archive_bus",
    ),
    "seal_controller": LevelDefinition(
        "seal_controller", "sealctl:/control>", "--[ sealctl | keyring ]--",
        ("sealctl: channel active",), COMMON + ("sealctl", "back"), (
            LevelRule("status", requires_flags=frozenset({"seal_ready"}), message="sealctl: online\nstate: locked\ncontrol: verified"),
            LevelRule("status", message="sealctl: online\nstate: locked\ncontrol: unverified"),
            LevelRule("ls", message="control  driver"),
            LevelRule("cat", ("control",), message="sealctl status: read control register\nwrite_requires=verified register"),
            LevelRule("cat", ("driver",), message="driver=mirror\nkeyring=external\noperations=status,unlock"),
            LevelRule("sealctl", ("status",), sets_flags=frozenset({"seal_ready"}),
                      message="sealctl: register verified\nstate: locked\ncontrol: unlock available"),
            LevelRule("sealctl", ("unlock",), requires_flags=frozenset({"seal_ready"}), transition_to="authentication_gate"),
            LevelRule("sealctl", None, trap_id="seal_lockout"),
        ), "black_archive",
    ),
}
