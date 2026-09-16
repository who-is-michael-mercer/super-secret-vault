import pytest
from relayvault.input import Key, KeyDecoder, WakeMatcher, VIEWER_KEYS
from relayvault import settings


@pytest.mark.parametrize('raw,name', list(KeyDecoder.sequences.items()))
def test_named_key_fragmentation(raw, name):
    if name == 'PASTE_START':
        return
    decoder = KeyDecoder()
    for byte in raw[:-1]:
        assert decoder.feed(bytes([byte]), 0) == []
    assert decoder.feed(raw[-1:], 0) == [Key(name)]


def test_escape_and_unknown_ss3_do_not_leak():
    decoder = KeyDecoder()
    assert decoder.feed(b'\x1b', 0) == []
    assert decoder.expire(.081) == [Key('ESC')]
    assert decoder.feed(b'\x1bOZ') == [Key('UNKNOWN')]
    assert decoder.feed(b'\x1b[99;3~') == [Key('UNKNOWN')]


def test_named_prefix_overlap_and_paste_reset():
    matcher = WakeMatcher(['KEY_HOME', 'KEY_HOME', 'KEY_END'], 1)
    for moment in (0, .1, .2):
        assert not matcher.feed(Key('HOME'), moment)
    assert matcher.feed(Key('END'), .3)
    matcher.feed(Key('HOME'), .4)
    matcher.feed(Key('PASTE', '\x1b[H\x1b[F'), .5)
    assert not matcher.feed(Key('END'), .6)
    matcher.feed(Key('HOME'), .7)
    assert not matcher.feed(Key('HOME'), 2)
    assert not matcher.feed(Key('END'), 2.1)


def test_v1_migrates_without_enrollment_or_policy_changes():
    old = {k: v for k,v in settings.defaults().items() if k in {
        'version','target','wake','effects','auto_lock_seconds','real_os_actions'}}
    old.update(version=1, wake=['a','UP'], target='/tmp/old.png')
    migrated = settings.validate(old)
    assert migrated['version'] == 2 and migrated['image_door'] is None
    for field in ('wake', 'target', 'real_os_actions', 'effects'):
        assert migrated[field] == old[field]
    assert old['version'] == 1


@pytest.mark.parametrize('key', ['KEY_CAPSLOCK','KEY_PRINT','KEY_PAUSE','KEY_FN','KEY_CTRL'])
def test_terminal_rejects_unavailable_keys(key):
    with pytest.raises(ValueError, match='unsupported key'):
        settings.validate(settings.defaults() | {'vault_sequence':[key]})


@pytest.mark.parametrize('value', [float('nan'),float('inf'),-1,0,61,True,10**1000])
def test_timeout_bounds(value):
    with pytest.raises(ValueError):
        settings.validate(settings.defaults() | {'sequence_timeout_seconds':value})


def test_prtsc_product_mapping_is_not_ac_print():
    assert VIEWER_KEYS['PRINT'] == 99
    assert VIEWER_KEYS['PAUSE'] == 119
    assert VIEWER_KEYS['INSERT'] == 110


def test_suspend_handler_defers_all_io_until_poll(monkeypatch):
    import signal
    from relayvault.input import TTYInput
    from io import StringIO
    keyboard=object.__new__(TTYInput)
    keyboard.stop_requested=False
    monkeypatch.setattr(keyboard,'_restore',lambda:pytest.fail('signal handler performed I/O'))
    keyboard._signal(signal.SIGTSTP,None)
    assert keyboard.stop_requested
