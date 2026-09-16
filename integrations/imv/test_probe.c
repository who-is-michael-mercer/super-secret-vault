/* Small contract tests for the exact development probe, no display/input device. */
#include <assert.h>
#include <stdbool.h>
#include "relay_probe.h"

int main(void)
{
  struct relay_probe p={.configured=true,.region={350,250,100,100,.9,2.1,.12,.12}};
  struct relay_pose s={.iw=800,.ih=600,.ww=800,.wh=600,.bw=800,.bh=600,
    .zoom=1,.focus=true,.file_ok=true};
  assert(relay_eligible(&p,&s));
  s.zoom=.5; assert(!relay_eligible(&p,&s)); s.zoom=1;
  s.x=300; assert(!relay_eligible(&p,&s)); s.x=0;
  s.focus=false; assert(!relay_eligible(&p,&s)); s.focus=true;
  s.file_ok=false; assert(!relay_eligible(&p,&s)); s.file_ok=true;
  s.rotation=90; assert(!relay_eligible(&p,&s)); s.rotation=0;
  s.mirror=true; assert(!relay_eligible(&p,&s)); s.mirror=false;
  s.loading=true; assert(!relay_eligible(&p,&s)); s.loading=false;
  s.zoom=NAN; assert(!relay_eligible(&p,&s)); s.zoom=1;
  s.bw=1600; s.bh=1200; s.zoom=2; assert(relay_eligible(&p,&s));
  // Exercise the exact pose-update/reset function used by the real event loop.
  // Seed only matched-prefix state: these are not claims of physical key input.
  relay_update_pose(&p,&s,0);
  p.prefix=3; s.focus=false;
  assert(relay_update_pose(&p,&s,.1) && !p.prefix);
  p.prefix=3; s.zoom=1.5;
  assert(relay_update_pose(&p,&s,.2) && !p.prefix);
  p.prefix=3; s.x=20;
  assert(relay_update_pose(&p,&s,.3) && !p.prefix);
  p.prefix=3; s.ww=900;
  assert(relay_update_pose(&p,&s,.4) && !p.prefix);
  p.prefix=3; ++s.generation;
  assert(relay_update_pose(&p,&s,.5) && !p.prefix);
  p.prefix=3; s.file_ok=false;
  assert(relay_update_pose(&p,&s,.6) && !p.prefix);
  p.prefix=3; assert(!relay_update_pose(&p,&s,.7) && p.prefix==3);
  relay_reset(&p);
  // Every possible prefix must be invalidatable, including at a geometry change.
  for (int n=1;n<8;++n) {
    for (int i=0;i<n;++i) relay_feed(&p,true,relay_sequence[i],1,i*.1);
    assert(p.prefix==(unsigned)n); relay_reset(&p); assert(!p.prefix);
    for (int i=n;i<8;++i) relay_feed(&p,true,relay_sequence[i],1,i*.1);
    assert(!p.matches); relay_reset(&p);
  }
  relay_feed(&p,true,KEY_HOME,1,0); relay_feed(&p,true,KEY_HOME,2,.1);
  assert(p.prefix==1); relay_feed(&p,true,KEY_HOME,0,.2); assert(p.prefix==1);
  relay_feed(&p,true,KEY_F7,1,5); assert(p.prefix==0);
  // Home overlaps the beginning without permitting arbitrary intervening keys.
  relay_feed(&p,true,KEY_HOME,1,6); relay_feed(&p,true,KEY_HOME,1,6.1);
  assert(p.prefix==1); relay_feed(&p,true,KEY_A,1,6.2); assert(!p.prefix);
  for (int i=0;i<8;++i) relay_feed(&p,true,relay_sequence[i],1,7+i*.1);
  assert(p.matches==1 && !p.prefix);
  relay_feed(&p,false,KEY_HOME,1,9); assert(!p.prefix);
  puts("probe contract: geometry, DPI, prefix/reset, timeout, overlap, press/release/repeat passed");
}
