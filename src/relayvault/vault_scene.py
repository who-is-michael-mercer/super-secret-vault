"""Terminal-native architectural assembly. One canvas; the existing TTY owns input."""

import os
import time


BUILD_SECONDS = {'slow':5.4, 'normal':3.6, 'fast':1.4}


def dimensions(keyboard):
    size = os.get_terminal_size(keyboard.output.fileno())
    return max(1,(size.columns or 80)-1), max(1,(size.lines or 24)-1)


def canvas(width, height, *, text=False):
    """Return final rows and per-cell assembly times, deterministic at every size."""
    width, height = min(240,max(1,width)), min(80,max(1,height))
    cells = [[' ']*width for _ in range(height)]
    times = [[0.0]*width for _ in range(height)]
    def put(x,y,label,stage=0):
        for i,c in enumerate(label):
            if 0 <= x+i < width and 0 <= y < height:
                cells[y][x+i]=c
                times[y][x+i]=min(.99,stage+(i/max(1,len(label)))*.06)
    def box(x,y,w,h,stage):
        put(x,y,'+'+'-'*(w-2)+'+',stage+.07)
        put(x,y+h-1,'+'+'-'*(w-2)+'+',stage)
        for n in range(1,h-1):
            put(x,y+n,'|',stage+.07*(1-n/h))
            put(x+w-1,y+n,'|',stage+.07*(1-n/h))
    if text or width<42 or height<16:
        w=min(31,width)
        label='[ R / 13 ]'
        rows=['+'+'-'*max(0,w-2)+'+', '|'+ ' '*max(0,w-2)+'|',
              '|'+label.center(max(0,w-2))+'|', '|'+ ' '*max(0,w-2)+'|',
              '+'+'='*max(0,w-2)+'+']
        for n,row in enumerate(rows[:height]):
            put(max(0,(width-w)//2),max(0,(height-len(rows))//2)+n,row,.12*n)
        return [''.join(row) for row in cells], times
    left,right=2,width-3
    top,bottom=1,height-3
    put(left-1,bottom+1,'/ '+'='*(right-left-1)+' \\',0)
    put(left-1,bottom+2,'+'+'='*(right-left+2)+'+',.03)
    box(left,top,right-left+1,bottom-top+1,.12)
    box(left+2,top+1,right-left-3,bottom-top-1,.26)
    dl,dr=left+max(5,(right-left)//7),right-max(5,(right-left)//7)
    dt,db=top+3,bottom-2
    box(dl,dt,dr-dl+1,db-dt+1,.40)
    # Bevels and inner door skin: a separate structure within the outer housing.
    if db-dt>=7:
        put(dl+1,dt+1,'/'+ '-'*(dr-dl-3)+'\\',.50)
        put(dl+1,db-1,'\\'+ '-'*(dr-dl-3)+'/',.50)
        for y in range(dt+2,db-1):
            put(dl+1,y,'|',.51); put(dr-1,y,'|',.51)
    for y in (dt+2,db-2):
        put(dl-2,y,'[==]',.60)
        put(dr-1,y,'[==]',.60)
    cx,cy=(dl+dr)//2,(dt+db)//2
    wheel=['      |      ', '  \\   |   /  ', '   .--+--.   ',
           '--(---O---)--', "   '--+--'   ", '  /   |   \\  ', '      |      ']
    if db-dt < 11:
        wheel=[' \\  |  / ', '--( O )--', ' /  |  \\ ']
    for n,row in enumerate(wheel):
        put(cx-len(row)//2,cy-len(wheel)//2+n,row,.66+n*.018)
    # Rivets and wall seams settle last, without fictional progress counters.
    for y in range(top+3,bottom-1,3):
        put(left+3,y,'o',.83); put(right-3,y,'o',.83)
    for x in range(left+5,right-3,8):
        put(x,top+2,'.',.86); put(x,bottom-1,'.',.86)
    put(cx-3,dt,'R / 13',.94)
    return [''.join(row) for row in cells], times


def frame(width,height,progress=1,*,text=False):
    rows,times=canvas(width,height,text=text)
    return [''.join(c if times[y][x] <= progress else ' ' for x,c in enumerate(row))
            for y,row in enumerate(rows)]


def draw(keyboard, rows, previous=None):
    # Leave the bottom/right terminal cells unused: no implicit wrapping/scrolling.
    output=[]
    for n,row in enumerate(rows):
        if previous is None or n>=len(previous) or row != previous[n]:
            output.append(f'\x1b[{n+1};1H'+row+'\x1b[K')
    if output:
        keyboard._write(''.join(output))
    return rows


def build(keyboard, config):
    animate(keyboard, config, dissolving=False)


def dissolve(keyboard, config):
    animate(keyboard, config, dissolving=True)


def animate(keyboard, config, *, dissolving):
    keyboard.boundary()
    keyboard._write('\x1b[2J\x1b[H' + ('\x1b[2m' if dissolving else ''))
    seconds = ({'slow':1.6,'normal':.95,'fast':.5} if dissolving else BUILD_SECONDS)
    duration=seconds[config['animation_speed']] if config['effects'] and config['presentation']=='ascii' else 0
    start=time.monotonic()
    previous=None
    size=None
    try:
        while True:
            current=dimensions(keyboard)
            if current != size:
                keyboard._write('\x1b[2J\x1b[H')
                size,previous=current,None
            progress=min(1,(time.monotonic()-start)/duration) if duration else 1
            rows=frame(*size,1-progress if dissolving else progress,
                text=config['presentation']=='text')
            if dissolving and progress>=1:
                rows=[' '*len(row) for row in rows]
            elif not dissolving and .15 < progress < .80 and size[0]>=48 and size[1]>=18:
                message='structural integrity: probably fine'
                rows[-1]=message.center(len(rows[-1]))[:len(rows[-1])]
            previous=draw(keyboard,rows,previous)
            if progress>=1:
                break
            key=keyboard.poll(min(.04,max(0,duration-(time.monotonic()-start))))
            if key is not None and key.kind in {'RESIZE','RESUME'}:
                previous=None
    finally:
        keyboard._write('\x1b[0m')
    keyboard.boundary()


def hold(keyboard, config):
    from .input import WakeMatcher
    keyboard.boundary()
    matcher=WakeMatcher(config['vault_sequence'],config['sequence_timeout_seconds'])
    draw(keyboard,frame(*dimensions(keyboard),text=config['presentation']=='text'))
    while True:
        key=keyboard.poll()
        if key is None:
            continue
        if key.kind in {'RESIZE','RESUME'}:
            matcher.reset()
            keyboard.boundary()
            keyboard._write('\x1b[2J\x1b[H')
            draw(keyboard,frame(*dimensions(keyboard),text=config['presentation']=='text'))
        elif matcher.feed(key):
            keyboard.boundary()
            return
