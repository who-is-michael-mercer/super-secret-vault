-- Viewer-local wl_keyboard matcher. No input history or diagnostics are written.
local M = {}
M.sequence = {102, 65, 107, 99, 104, 58, 1, 102}
M.names = {[102]='HOME', [65]='F7', [107]='END', [99]='PRTSC',
           [104]='PGUP', [58]='CAPSLOCK', [1]='ESC', [110]='INSERT'}
function M.new(sequence, timeout)
    return {sequence=sequence or M.sequence, timeout=timeout or 5, prefix=0, matched=false, matches=0, focused=false, down={},
            counts={}, resets={}, blocked={}, keymaps=0,
            focus_enters=0, focus_leaves=0, held_entries=0}
end
function M.reset(s, reason)
    if s.prefix > 0 or s.matched then
        s.resets[reason] = (s.resets[reason] or 0) + 1
    end
    s.prefix, s.matched = 0, false
end
function M.tick(s, now, visual)
    if not visual then M.reset(s, 'visual') end
    if s.deadline and now >= s.deadline then M.reset(s, 'timeout') end
end
function M.event(s, kind, code, now, visual)
    M.tick(s, now, visual)
    if kind == 'enter' or kind == 'leave' then
        M.reset(s, 'focus')
        s.focused, s.down = kind == 'enter', {}
        local field = kind == 'enter' and 'focus_enters' or 'focus_leaves'
        s[field] = s[field] + 1
    elseif kind == 'held' then
        s.down[code] = true
        s.held_entries = s.held_entries + 1
        M.reset(s, 'held')
    elseif kind == 'change' then
        M.reset(s, 'change')
    elseif kind == 'keymap' then
        s.keymaps = s.keymaps + 1
        M.reset(s, 'keymap')
    else
        local name = M.names[code]
        if name then
            s.counts[name] = s.counts[name] or {press=0, release=0, repeat_count=0}
            local field = kind == 'repeat' and 'repeat_count' or kind
            s.counts[name][field] = (s.counts[name][field] or 0) + 1
        end
        if kind == 'release' then s.down[code] = nil; return end
        if kind == 'repeat' then return end
        if kind ~= 'press' then return end
        local held = next(s.down) ~= nil
        s.down[code] = true
        if not s.focused or held or not visual then
            local reason = not s.focused and 'focus' or (held and 'held' or 'visual')
            s.blocked[reason] = (s.blocked[reason] or 0) + 1
            M.reset(s, 'blocked'); return
        end
        s.matched = false
        -- Longest suffix that remains a prefix, including overlapping Home.
        local seen = {}
        for i=1,s.prefix do seen[i] = s.sequence[i] end
        seen[#seen+1] = code
        s.prefix = 0
        for n=math.min(#seen, #s.sequence),1,-1 do
            local same = true
            for i=1,n do
                if seen[#seen-n+i] ~= s.sequence[i] then same = false; break end
            end
            if same then s.prefix = n; break end
        end
        s.deadline = now + s.timeout
        if s.prefix == #s.sequence then
            s.matches = s.matches + 1
            s.matched = true
            s.prefix = 0
        end
    end
end
function M.geometry(p, c)
    if not p or not p.current or not p.original or p.path ~= c.image or
       p.origin_path ~= c.image or p.width <= 0 or p.height <= 0 or
       p.window_width <= 0 or p.window_height <= 0 or
       p.scale < c.zoom_min or p.scale > c.zoom_max then return false end
    if c.x < 0 or c.y < 0 or c.x+c.width > p.width or
       c.y+c.height > p.height then return false end
    local x, y = p.x+c.x*p.scale, p.y+c.y*p.scale
    local w, h = c.width*p.scale, c.height*p.scale
    local visible_w = math.max(0, math.min(x+w,p.window_width)-math.max(x,0))
    local visible_h = math.max(0, math.min(y+h,p.window_height)-math.max(y,0))
    return math.abs(x+w/2-p.window_width/2) <= c.tolerance_x*p.window_width and
           math.abs(y+h/2-p.window_height/2) <= c.tolerance_y*p.window_height and
           visible_w*visible_h >= 0.9*w*h
end
return M
