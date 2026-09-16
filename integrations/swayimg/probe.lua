-- Development configuration, loaded explicitly with --config. No default config.
local root = assert(os.getenv('RELAY_SWAYIMG_SCRIPTS'))
local directory = assert(os.getenv('RELAY_SWAYIMG_PROBE'))
local M = dofile(root .. '/matcher.lua')
local c = dofile(directory .. '/config.lua')
local s = M.new()
local drawn, dirty, last_output, last_status = nil, true, nil, ''
local recorded_match = 0
local redraws = 0
local initialized = false

-- JSON diagnostic snapshots contain only pose and eight aggregate key counters.
local function json(v)
    if type(v) == 'string' then return '"' .. v:gsub('[%z\1-\31\\"]', function(ch)
        return string.format('\\u%04x', string.byte(ch)) end) .. '"' end
    if type(v) ~= 'table' then return tostring(v) end
    local fields = {}
    for k,item in pairs(v) do fields[#fields+1] = json(tostring(k)) .. ':' .. json(item) end
    table.sort(fields)
    return '{' .. table.concat(fields, ',') .. '}'
end
local function pose()
    local i = swayimg.viewer.get_image()
    if not i then return nil end
    local pos, w = swayimg.viewer.get_position(), swayimg.get_window_size()
    return {path=i.path, origin_path=i.relay_path, current=i.relay_current,
        origin=i.relay_origin, generation=i.relay_generation, original=i.relay_original,
        width=i.width, height=i.height, scale=swayimg.viewer.scale,
        x=pos.x, y=pos.y, window_width=w.width, window_height=w.height}
end
local function visual(p)
    return not dirty and drawn == json(p) and M.geometry(p, c)
end
local function report()
    if not initialized then return end
    local p = pose()
    M.tick(s, swayimg.relay_time(), visual(p))
    local eligible = visual(p) and s.focused and s.matched
    local status = eligible and 'ELIGIBLE' or ''
    if status ~= last_status then swayimg.text.status = status; last_status = status end
    local result = json({viewer='swayimg-stage1b', pose=p or {}, visual=visual(p),
        eligible=eligible, prefix=s.prefix, matches=s.matches, focused=s.focused,
        focus_enters=s.focus_enters, focus_leaves=s.focus_leaves,
        held_entries=s.held_entries, keymaps=s.keymaps, blocked=s.blocked,
        counts=s.counts, resets=s.resets, redraws=redraws})
    if result ~= last_output then
        local f = assert(io.open(directory .. '/latest.tmp', 'w'))
        f:write(result, '\n'); f:close()
        assert(os.rename(directory .. '/latest.tmp', directory .. '/latest.json'))
        last_output = result
    end
    if eligible and s.matches > recorded_match then
        -- Keep only the latest successful predicate snapshot, never input history.
        local f = assert(io.open(directory .. '/last-success.tmp', 'w'))
        f:write(result, '\n'); f:close()
        assert(os.rename(directory .. '/last-success.tmp', directory .. '/last-success.json'))
        recorded_match = s.matches
    end
end
local function change(reason)
    M.reset(s, reason); dirty = true
end
swayimg.mode = 'viewer'
swayimg.overlay = false
swayimg.exif_orientation = false
swayimg.imagelist.adjacent = false
swayimg.imagelist.fsmon = false -- Explicit reload tests must expose stale display.
swayimg.viewer.preload = 0
swayimg.viewer.history = 2 -- Exercise cached images, not only fresh loads.
swayimg.viewer.default_scale = 1
swayimg.viewer.default_position = 'center'
swayimg.viewer.autocenter = false
swayimg.viewer.bind_reset()
swayimg.viewer.text = {topleft={}, topright={}, bottomleft={}, bottomright={}}
swayimg.text.status_timeout = 0
swayimg.viewer.on_unassigned_key(function() end)
swayimg.on_relay_event(function(kind, code)
    -- A pointer move can leave pixels unchanged and request no redraw. Reset
    -- the prefix, but compare actual pose to the last draw to gate rendering.
    M.event(s, kind, code, swayimg.relay_time(), initialized and visual(pose()))
    report()
end)
swayimg.viewer.on_image_change(function() change('image') end)
swayimg.on_window_resize(function() change('resize') end)
swayimg.on_redrawn(function()
    if not initialized then return end
    redraws = redraws + 1
    local p = pose()
    if drawn ~= json(p) then M.reset(s, 'pose') end
    drawn, dirty = json(p), false
    report()
end)
local function control(key, action)
    swayimg.viewer.on_key(key, function() change('control'); action() end)
end
control('q', function() swayimg.exit() end)
control('r', function() swayimg.viewer.reset() end)
control('z', function() swayimg.viewer.scale = swayimg.viewer.scale * 1.25 end)
control('x', function() swayimg.viewer.scale = swayimg.viewer.scale / 1.25 end)
for key,delta in pairs({h={40,0}, l={-40,0}, j={0,-40}, k={0,40}}) do
    control(key, function()
        local p = swayimg.viewer.get_position()
        swayimg.viewer.set_abs_position(p.x+delta[1], p.y+delta[2])
    end)
end
control('n', function() swayimg.viewer.open('next') end)
control('b', function() swayimg.viewer.open('prev') end)
control('o', function() swayimg.viewer.reload() end)
control('f', function() swayimg.fullscreen = not swayimg.fullscreen end)
control('bracketright', function() swayimg.viewer.rotate(90) end)
control('m', function() swayimg.viewer.flip_horizontal() end)
swayimg.on_initialized(function()
    initialized = true
    swayimg.viewer.animation = false
    swayimg.title = 'Swayimg Stage 1B - physical key test'
    -- Only this viewer and the configured file are sampled. No desktop observer.
    local function tick() report(); swayimg.defer(0.1, tick) end
    tick()
end)

-- Only the automated wrapper receives this seam. It seeds a PARTIAL prefix to
-- test real view/focus invalidations; never generates a key or a successful match.
if os.getenv('RELAY_SWAYIMG_TESTING') == '1' then
    return {seed_partial=function()
        assert(s.focused and visual(pose()), 'seed requires a qualified view')
        s.prefix, s.deadline = 2, swayimg.relay_time()+5
        report()
    end}
end
