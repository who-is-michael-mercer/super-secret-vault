"""Fictional routing only. Authentication is an intent handled outside this module."""

from dataclasses import dataclass
from enum import Enum, auto
from .topology import RESOURCES, PROMPTS, LAYERS, STATUS


class AccessState(Enum):
    COVER = auto()
    VAULT_BUILD = auto()
    VAULT_WAIT = auto()
    VAULT_FADE = auto()
    ROUTE = auto()
    AUTHENTICATING = auto()
    UNLOCKED = auto()


@dataclass
class AccessResult:
    message: str = ''
    action: str = ''


class AccessController:
    def __init__(self):
        self.node = 'media'

    @property
    def prompt(self):
        return PROMPTS[self.node]

    def handle(self, command):
        name,args = command.name,command.args
        if not name:
            return AccessResult()
        if not args and name in {'sleep','exit','clear'}:
            return AccessResult(action=name)
        if name == 'peel' and not args and self.node == 'media':
            return AccessResult(LAYERS)
        if name == 'follow' and self.node == 'media':
            if args == ('3',):
                self.node='13'
                return AccessResult('handoff: local\nchannel: 13\nroundtrip: below useful precision')
            if args == ('service',):
                self.node='service'
                return AccessResult('reports: retained')
        if name == 'open' and not args:
            return AccessResult(action='authenticate') if self.node == '13' else AccessResult('endpoint: not selected')
        if name == 'back' and not args:
            self.node='media'
            return AccessResult('route: media')
        if name == 'ls' and not args:
            return AccessResult('  '.join(RESOURCES[self.node]))
        if name in {'cat','inspect'} and len(args)==1 and args[0] in RESOURCES[self.node]:
            return AccessResult(RESOURCES[self.node][args[0]])
        if name == 'inspect' and args == ('3',) and self.node == 'media':
            return AccessResult('route: follow 3\nendpoint: sealed')
        if name == 'status' and not args:
            return AccessResult(STATUS[self.node])
        if name == 'trace' and not args:
            return AccessResult('media -> 3 -> 13\nnetwork hops: none')
        if name == 'probe' and not args:
            return AccessResult('external sockets: absent\nrouting: internal')
        if name == 'knock' and self.node == '13':
            if not args:
                return AccessResult('no.')
            if args == ('--politely',):
                return AccessResult('noted.')
        if name == 'reset' and args == ('channel',):
            self.node='media'
            return AccessResult(action='incident')
        return AccessResult('command: unavailable')
