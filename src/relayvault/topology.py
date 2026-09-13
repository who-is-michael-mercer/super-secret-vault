"""Fixed local pseudo-resources. Never maps to host paths or a shell."""

RESOURCES = {
    "link": {
        "interfaces": "13  local control\ndiagnostics  retained telemetry",
        "link.conf": "transport=local\nattach=13",
    },
    "control": {
        "control": "state=sealed\noperation=unlock",
        "driver": "sealctl\nidentity=external",
    },
    "diagnostics": {
        "relay.log": "13: retained\nlink: idle\ncontrol: detached",
        "telemetry": "rx=0000\ntx=0000\nclock=local",
    },
}
PROMPTS = {
    "link": "relay0:/link> ",
    "control": "sealctl:/control> ",
    "diagnostics": "relay0:/diag> ",
}
