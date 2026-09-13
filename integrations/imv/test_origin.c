/* Real libpng decoder + source, without a compositor or test double. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "backend.h"
#include "image.h"
#include "source.h"

extern const struct imv_backend imv_backend_libpng;
static struct imv_image *displayed;

static struct imv_source *begin(const char *path)
{
  struct imv_source *source=NULL;
  displayed=NULL;
  assert(imv_backend_libpng.open_path(path,&source)==BACKEND_SUCCESS);
  return source;
}

static void finish(struct imv_source *source)
{
  int frametime;
  assert(imv_source_load_first_frame(source,&displayed,&frametime));
  assert(displayed);
  assert(imv_image_width(displayed)==800 && imv_image_height(displayed)==600);
}

int main(int argc, char **argv)
{
  assert(argc==3);
  const char *path=argv[1], *replacement=argv[2];
  struct imv_source *source=begin(path);
  finish(source);
  const struct imv_origin *origin=imv_image_origin(displayed);
  struct stat disk;
  assert(origin->stable && !strcmp(origin->path,path));
  assert(!stat(path,&disk) && relay_same_file(&disk,&origin->identity));
  // Replace after decoding: displayed origin must remain the original inode.
  assert(!rename(replacement,path));
  assert(!stat(path,&disk) && !relay_same_file(&disk,&origin->identity));
  imv_image_free(displayed); imv_source_free(source);
  source=begin(path); finish(source);
  origin=imv_image_origin(displayed);
  assert(origin->stable && relay_same_file(&disk,&origin->identity));
  imv_image_free(displayed); imv_source_free(source);
  // Change the actual open file after headers, before pixels are decoded.
  source=begin(path);
  FILE *edit=fopen(path,"ab"); assert(edit);
  assert(fputc(0,edit)!=EOF); assert(!fclose(edit));
  finish(source);
  assert(!imv_image_origin(displayed)->stable);
  imv_image_free(displayed); imv_source_free(source);
  puts("real decoder: stable descriptor, replacement/reload, during-load mutation passed");
  return 0;
}
