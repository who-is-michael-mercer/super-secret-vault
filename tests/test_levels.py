"""V2 topology, discoverable resources, and operational voice."""

import pytest

from vaultgame.levels import LEVELS


EXPECTED_BACK = {
    'relay_root': None, 'device_bus': 'relay_root', 'route_table': 'device_bus',
    'null_link': 'route_table', 'archive_bus': 'null_link',
    'diagnostics': 'relay_root', 'white_archive': 'archive_bus',
    'red_maintenance': 'archive_bus', 'black_archive': 'archive_bus',
    'seal_controller': 'black_archive',
}


@pytest.mark.parametrize('identity', EXPECTED_BACK)
def test_environments_have_exact_routes_and_operational_resources(identity):
    assert set(LEVELS) == set(EXPECTED_BACK)
    level = LEVELS[identity]
    assert level.id == identity
    assert level.back_target == EXPECTED_BACK[identity]
    assert level.prompt.endswith('>') and ':/' in level.prompt
    assert level.ascii_scene and level.intro_lines
    assert {'help', 'status', 'pwd', 'ls', 'cat', 'clear'} <= set(level.visible_commands)
    listing = next(rule.message.split() for rule in level.rules if rule.command == 'ls')
    resources = {rule.args[0] for rule in level.rules if rule.command == 'cat'}
    assert set(listing) == resources
    for rule in level.rules:
        assert rule.transition_to in {*LEVELS, 'authentication_gate', None}
        assert rule.command in level.visible_commands or rule.hidden


def test_only_seal_controller_has_authentication_edge():
    gates = [(level.id, rule) for level in LEVELS.values() for rule in level.rules
             if rule.transition_to == 'authentication_gate']
    assert len(gates) == 1
    identity, rule = gates[0]
    assert identity == 'seal_controller'
    assert (rule.command, rule.args, rule.requires_flags) == ('sealctl', ('unlock',), {'seal_ready'})
    assert {r.trap_id for l in LEVELS.values() for r in l.rules if r.trap_id} == {
        'false_probe', 'red_purge', 'seal_lockout'}


def test_voice_has_no_riddles_player_address_or_solution_narration():
    copy = '\n'.join('\n'.join(level.intro_lines) + '\n' +
                     '\n'.join(rule.message for rule in level.rules) for level in LEVELS.values())
    assert copy == copy.lower()
    for obsolete in ('you ', 'your ', 'riddle', 'chamber', 'largest prime',
                     'solution', 'congrat', 'secret archive', 'try another', 'fake'):
        assert obsolete not in copy
    assert 'route13: endpoint=null' in copy
    assert 'sealctl: channel active' in copy
