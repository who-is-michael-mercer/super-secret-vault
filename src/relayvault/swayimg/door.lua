-- Explicit isolated viewer configuration. No shell, diagnostics or desktop hooks.
local root = assert(os.getenv('RELAY_SWAYIMG_SCRIPTS'))
local c = dofile(assert(os.getenv('RELAY_SWAYIMG_CONFIG')))
local M = dofile(root .. '/matcher.lua')
local s = M.new(c.sequence, c.timeout)
local drawn, dirty, initialized = nil, true, false
local function pose()
    local i = swayimg.viewer.get_image()
    if not i then return nil end
    local p, w = swayimg.viewer.get_position(), swayimg.get_window_size()
    return {path=i.path, origin_path=i.relay_path, current=i.relay_current,
        origin=i.relay_origin, generation=i.relay_generation, original=i.relay_original,
        width=i.width, height=i.height, scale=swayimg.viewer.scale,
        x=p.x, y=p.y, window_width=w.width, window_height=w.height}
end
local function same(a,b)
    if not a or not b then return false end
    for k,v in pairs(a) do if b[k] ~= v then return false end end
    return true
end
local function visual(p)
    return initialized and not dirty and same(p,drawn) and M.geometry(p,c)
end
local function change()
    M.reset(s,'change'); dirty=true
end
swayimg.mode='viewer'
swayimg.overlay=false
swayimg.exif_orientation=false
swayimg.imagelist.adjacent=false
swayimg.imagelist.fsmon=false
swayimg.viewer.preload=0
swayimg.viewer.history=0
swayimg.viewer.default_scale='optimal'
swayimg.viewer.default_position='center'
swayimg.viewer.autocenter=false
swayimg.viewer.bind_reset()
swayimg.viewer.text={topleft={},topright={},bottomleft={},bottomright={}}
swayimg.viewer.on_unassigned_key(function() end)
swayimg.on_relay_event(function(kind,code)
    local p=pose()
    M.event(s,kind,code,swayimg.relay_time(),visual(p))
    if s.matched then
        M.reset(s,'handoff')
        if visual(p) and s.focused then swayimg.relay_request(p.origin) end
    end
end)
swayimg.viewer.on_image_change(change)
swayimg.on_window_resize(change)
swayimg.on_redrawn(function()
    local p=pose()
    if not same(p,drawn) then M.reset(s,'pose') end
    drawn,dirty=p,false
end)
local function control(key,action)
    swayimg.viewer.on_key(key,function() change(); action() end)
end
control('q',function() swayimg.exit() end)
control('r',function() swayimg.viewer.reset() end)
control('z',function() swayimg.viewer.scale=swayimg.viewer.scale*1.25 end)
control('x',function() swayimg.viewer.scale=swayimg.viewer.scale/1.25 end)
control('equal',function() swayimg.viewer.scale=swayimg.viewer.scale*1.25 end)
control('minus',function() swayimg.viewer.scale=swayimg.viewer.scale/1.25 end)
control('1',function() swayimg.viewer.scale=1 end)
for key,d in pairs({h={40,0},l={-40,0},j={0,-40},k={0,40}}) do
    control(key,function()
        local p=swayimg.viewer.get_position()
        swayimg.viewer.set_abs_position(p.x+d[1],p.y+d[2])
    end)
end
control('n',function() swayimg.viewer.open('next') end)
control('b',function() swayimg.viewer.open('prev') end)
control('o',function() swayimg.viewer.reload() end)
control('f',function() swayimg.fullscreen=not swayimg.fullscreen end)
control('bracketright',function() swayimg.viewer.rotate(90) end)
control('m',function() swayimg.viewer.flip_horizontal() end)
swayimg.on_initialized(function()
    initialized=true
    swayimg.viewer.animation=false
    swayimg.title='Swayimg'
    local function tick()
        M.tick(s,swayimg.relay_time(),visual(pose()))
        swayimg.defer(.1,tick)
    end
    tick()
end)
