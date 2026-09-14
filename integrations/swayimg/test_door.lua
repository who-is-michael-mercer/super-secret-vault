-- Execute the shipped Lua with an isolated viewer API. No OS input synthesis.
local callbacks, keys = {}, {}
local requests = 0
local image = {path='/image.png',relay_path='/image.png',relay_current=true,
    relay_origin='stamp',relay_generation=1,relay_original=true,width=800,height=600}
local position={x=100,y=75}
local viewer={scale=1,bind_reset=function() end,
    on_unassigned_key=function() end, on_key=function(k,f) keys[k]=f end,
    on_image_change=function(f) callbacks.image=f end,
    get_image=function() return image end, get_position=function() return position end}
swayimg={viewer=viewer,imagelist={},text={},relay_time=function() return 1 end,
    get_window_size=function() return {width=1000,height=750} end,
    on_relay_event=function(f) callbacks.event=f end,
    on_window_resize=function(f) callbacks.resize=f end,
    on_redrawn=function(f) callbacks.draw=f end,
    on_initialized=function(f) callbacks.init=f end,
    relay_request=function(stamp) assert(stamp=='stamp'); requests=requests+1 end,
    defer=function() end}
dofile(arg[1])
callbacks.init(); callbacks.draw(); callbacks.event('enter',0)
local sequence={102,65,107,99,104,58,1,102}
local function press(code)
    callbacks.event('press',code); callbacks.event('release',code)
end
local function complete() for _,k in ipairs(sequence) do press(k) end end
complete(); assert(requests==1)
for _,reset in ipairs({'leave','change','keymap'}) do
    press(102); press(65); callbacks.event(reset,0)
    if reset=='leave' then callbacks.event('enter',0) end
    for i=3,#sequence do press(sequence[i]) end
    assert(requests==1,reset)
end
callbacks.event('leave',0); callbacks.event('enter',0); callbacks.event('held',102)
complete(); assert(requests==1)
callbacks.event('release',102); complete(); assert(requests==2)
for _,field in ipairs({'relay_current','relay_original'}) do
    image[field]=false; callbacks.draw(); complete(); assert(requests==2)
    image[field]=true; callbacks.draw()
end
viewer.scale=2; callbacks.draw(); complete(); assert(requests==2)
viewer.scale=1; callbacks.draw()
position.x=-500; callbacks.draw(); complete(); assert(requests==2)
position.x=100; callbacks.draw()
press(102); press(65); callbacks.resize(); callbacks.draw()
for i=3,#sequence do press(sequence[i]) end
assert(requests==2)
complete(); assert(requests==3)
print('PASS shipped Lua predicate, focus/held/view resets, one request per match')
