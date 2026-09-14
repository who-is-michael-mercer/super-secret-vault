-- Pure deterministic checks; no desktop or keyboard synthesis.
local M = dofile(arg[1] or 'integrations/swayimg/matcher.lua')
local tests = 0
local function check(name, f) f(); tests=tests+1; print('PASS '..name) end
local function state()
    local s = M.new(); M.event(s, 'enter', 0, 0, true); return s
end
local function press(s, code, now, visual)
    M.event(s, 'press', code, now or 0, visual ~= false)
    M.event(s, 'release', code, now or 0, visual ~= false)
end
check('complete preferred sequence', function()
    local s=state()
    for _,code in ipairs(M.sequence) do press(s,code) end
    assert(s.matched and s.matches==1)
end)
check('all eight press/release counters; PrtSc explicitly selected', function()
    local s=state()
    for code,name in pairs(M.names) do
        press(s,code)
        assert(s.counts[name].press==1 and s.counts[name].release==1)
    end
    assert(M.sequence[4]==99 and M.names[99]=='PRTSC')
    -- Pause, Insert and AC Print are not aliases for physical PrtSc/SysRq.
    for _,wrong in ipairs({119,110,210}) do
        local attempt=state()
        for _,code in ipairs(M.sequence) do press(attempt, code==99 and wrong or code) end
        assert(attempt.matches==0)
    end
end)
check('repeat and duplicate press never advance', function()
    local s=state()
    M.event(s,'press',102,0,true)
    for _=1,100 do M.event(s,'repeat',102,0,true) end
    assert(s.prefix==1 and s.counts.HOME.repeat_count==100)
    M.event(s,'press',102,0,true); assert(s.prefix==0)
end)
check('overlapping Home prefixes and wrong key', function()
    local s=state()
    press(s,102); press(s,65); press(s,102); assert(s.prefix==1)
    for i=2,#M.sequence do press(s,M.sequence[i]) end
    assert(s.matches==1)
    press(s,102); press(s,30); assert(s.prefix==0 and not s.matched)
end)
check('timeout boundary and fresh retry', function()
    local s=state(); press(s,102,1)
    M.tick(s,5.99,true); assert(s.prefix==1)
    M.tick(s,6,true); assert(s.prefix==0)
    for _,code in ipairs(M.sequence) do press(s,code,7) end
    assert(s.matches==1)
end)
check('focus loss; held before focus; release gate', function()
    local s=state(); press(s,102)
    M.event(s,'leave',0,0,true); assert(s.prefix==0 and not s.focused)
    press(s,102); assert(s.prefix==0)
    M.event(s,'enter',0,0,true); M.event(s,'held',102,0,true)
    press(s,65); assert(s.prefix==0)
    M.event(s,'release',102,0,true)
    for _,code in ipairs(M.sequence) do press(s,code) end
    assert(s.matches==1)
end)
check('keymap resets without inventing focus loss or dropping held keys', function()
    local s=state()
    M.event(s,'press',102,0,true)
    M.event(s,'keymap',0,0,true)
    assert(s.focused and s.prefix==0 and s.down[102] and s.keymaps==1)
    M.event(s,'release',102,0,true)
    for _,code in ipairs(M.sequence) do press(s,code) end
    assert(s.matches==1)
end)
check('partial reset for every view boundary', function()
    for _,reason in ipairs({'zoom','pan','image','resize','file','pose'}) do
        local s=state(); press(s,102); M.reset(s,reason); assert(s.prefix==0)
        for i=2,#M.sequence do press(s,M.sequence[i]) end
        assert(s.matches==0)
    end
end)
check('ineligible geometry blocks full sequence', function()
    local s=state()
    for _,code in ipairs(M.sequence) do press(s,code,0,false) end
    assert(s.matches==0)
end)
check('visual tolerances, wrong image, stale, transforms', function()
    local c={image='/test/grid.png',x=350,y=250,width=100,height=100,
        zoom_min=.9,zoom_max=1.1,tolerance_x=.12,tolerance_y=.12}
    local p={current=true,original=true,path=c.image,origin_path=c.image,width=800,
        height=600,window_width=900,window_height=700,x=50,y=50,scale=1}
    assert(M.geometry(p,c))
    for key,val in pairs({current=false,original=false,path='/other/grid.png',
        origin_path='/old/grid.png',scale=1.25,x=-450,window_height=0}) do
        local old=p[key]; p[key]=val; assert(not M.geometry(p,c),key); p[key]=old
    end
    p.x=55; assert(M.geometry(p,c))
end)
print(string.format('%d checks passed',tests))
