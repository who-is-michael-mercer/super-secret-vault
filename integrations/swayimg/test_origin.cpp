// SPDX-License-Identifier: MIT
// Headless: the real pinned PNG loader, no UI or machine actions.
#include "formatfactory.hpp"
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
namespace fs = std::filesystem;
ImagePtr load(const fs::path& p) {
    auto e = std::make_shared<ImageEntry>(); e->path=p;
    auto i=FormatFactory::self().load(e); assert(i); return i;
}
int main(int argc, char** argv) {
    assert(argc==2);
    const fs::path dir=argv[1], path=dir/"grid.png", other=dir/"other/grid.png";
    setenv("RELAY_SWAYIMG_PROBE", dir.c_str(), 1);
    if (getenv("RELAY_SWAYIMG_DOOR")) {
        auto large=load(dir/"large.png");
        assert(large->relay_origin.current());
        assert(large->entry->size < 16*1024*1024);
        assert(fs::file_size(dir/"large.png") > 16*1024*1024);
        puts("PASS production skips large carrier payload and binds original source");
        for (const char* name : {"wide.png", "pixels.png"}) {
            auto entry=std::make_shared<ImageEntry>(); entry->path=dir/name;
            assert(!FormatFactory::self().load(entry));
        }
        puts("PASS decoded dimension/pixel budgets reject before decoder allocation");
    }
    auto image=load(path);
    assert(image->relay_origin.current());
    assert(image->frames[0].pm.width()==800 && image->frames[0].pm.height()==600);
    auto different=load(other);
    assert(different->relay_origin.current());
    assert(different->relay_origin.path != image->relay_origin.path);
    assert(different->relay_origin.stamp != image->relay_origin.stamp);
    puts("PASS exact loaded path and same basename in another directory");
    fs::rename(path,dir/"renamed.png");
    assert(!image->relay_origin.current());
    fs::rename(dir/"renamed.png",path);
    image=load(path);
    puts("PASS rename invalidates; fresh load requalifies");
    struct stat before; assert(stat(path.c_str(),&before)==0);
    fs::copy_file(other,dir/"replacement.png");
    const timespec times[]={before.st_atim,before.st_mtim};
    assert(utimensat(AT_FDCWD,(dir/"replacement.png").c_str(),times,0)==0);
    fs::rename(dir/"replacement.png",path);
    assert(!image->relay_origin.current());
    auto fresh=load(path);
    assert(fresh->relay_origin.current());
    assert(fresh->relay_origin.generation != image->relay_origin.generation);
    assert(fresh->relay_origin.stamp != image->relay_origin.stamp);
    puts("PASS atomic replacement preserving mtime, stale decode, fresh reload");
    fs::create_symlink(path,dir/"alias.png");
    auto alias=std::make_shared<ImageEntry>(); alias->path=dir/"alias.png";
    assert(!FormatFactory::self().load(alias));
    fs::create_hard_link(path,dir/"hard.png");
    assert(!fresh->relay_origin.current()); fs::remove(dir/"hard.png");
    puts("PASS symlink load and hardlink alias rejected");
    fresh=load(path); fresh->rotate(90); assert(!fresh->relay_origin.current());
    fresh=load(path); fresh->flip_horizontal(); assert(!fresh->relay_origin.current());
    fresh=load(path); fresh->flip_vertical(); assert(!fresh->relay_origin.current());
    puts("PASS transformed pixels disqualify original-coordinate region");
    fresh=load(path);
    fs::resize_file(path,0);
    assert(!fresh->relay_origin.current());
    assert(fresh->frames[0].pm.width()==800); // Private decoded pixels survive.
    puts("PASS truncate leaves decoded pixels safely stale");
}
