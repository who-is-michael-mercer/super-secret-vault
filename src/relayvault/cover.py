"""A quiet public image/file inspection view. No capsule metadata is displayed."""

from pathlib import Path
import os
import shutil
import stat
import unicodedata

from . import image_info


def display(text):
    return ''.join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


def clip(text, width):
    text = display(text)
    result = ''
    cells = 0
    for c in text:
        size = 0 if unicodedata.combining(c) else (2 if unicodedata.east_asian_width(c) in {'W','F'} else 1)
        if cells+size > width:
            break
        result += c
        cells += size
    return result


def snapshot(path=None):
    """One scan per cover entry, reused across arbitrary terminal resizes."""
    source = [('file', Path(path).name if path else 'none'), ('type','local file'), ('extent','unavailable')]
    structure = [('inspection','unavailable')]
    status = 'source unavailable'
    if path is not None:
        try:
            info = Path(path).lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('not regular')
            source[2] = ('extent', f'{info.st_size / (1024*1024):.2f} MiB ({info.st_size:,} bytes)')
            status = 'inspection incomplete'
            details = image_info.inspect(path)
        except (OSError, ValueError, RuntimeError):
            # Capsule-aware errors and untrusted chunk names never reach this view.
            pass
        else:
            source = [('file',Path(details.path).name), ('type','PNG / image/png'),
                ('dimensions',f'{details.width} x {details.height}'),
                ('channels',details.channels), ('profile',details.profile),
                ('depth',f'{details.depth}-bit'),
                ('extent',f'{details.size / (1024*1024):.2f} MiB ({details.size:,} bytes)')]
            structure = [('chunks',str(details.chunks)), ('checksum','valid (all chunk CRCs)')]
            status = 'inspection complete'
    return source, structure, status


def render(terminal, path=None, *, data=None):
    data = snapshot(path) if data is None else data
    try:
        size = os.get_terminal_size(terminal.stream.fileno())
        width, height = size.columns or 80, size.lines or 24
    except (AttributeError, OSError, ValueError):
        width, height = shutil.get_terminal_size((80,24))
    width, height = max(1,width-1), max(1,height-1)
    source, structure, status = data
    if height < 16 or width < 38:
        rows = ['IMAGE INSPECTION', ''] + [f'{k}: {v}' for k,v in source]
        rows += [f'{k}: {v}' for k,v in structure] + ['',status]
    else:
        rule = '-' * min(54,width)
        rows = ['IMAGE INSPECTION UTILITY', '', 'SOURCE', rule]
        rows += [f'{k:12} {v}' for k,v in source]
        rows += ['', 'STRUCTURE', rule] + [f'{k:12} {v}' for k,v in structure]
        rows += ['', 'STATUS', rule, status]
    for row in rows[:height]:
        terminal.print(clip(row,width))
