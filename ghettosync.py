import argparse
import contextlib
import os
import shutil
import subprocess

from typing import (
    IO,
    Iterator,
)

parser = argparse.ArgumentParser()
parser.add_argument('source')
parser.add_argument('destination')
args = parser.parse_args()


def getsize(dirpath: str) -> int:
    #
    # ignores subdirectories entirely
    #
    mb = 0
    for f in os.listdir(dirpath):
        fpath = os.path.join(dirpath, f)
        if os.path.isfile(fpath):
            mb += os.path.getsize(fpath) // 1024**2
    return mb


def print_buffer(source: str, destination: str) -> Iterator[str]:
    for topdir in sorted(os.listdir(source)):
        topdir_path = os.path.join(source, topdir)
        if not os.path.isdir(topdir_path):
            continue

        for bottomdir in sorted(os.listdir(topdir_path)):
            bottomdir_path = os.path.join(source, topdir, bottomdir)
            if not os.path.isdir(bottomdir_path):
                continue

            bottomdir_dest = os.path.join(destination, topdir, bottomdir)
            bottomdir_check = 'x' if os.path.isdir(bottomdir_dest) else ' '
            size = getsize(bottomdir_path)
            print('[%s] (% 6d MB) %s / %s' % (bottomdir_check, size, topdir, bottomdir))

            yield os.path.join(topdir, bottomdir)


def read_buffer(fin: IO[str]) -> Iterator[str]:
    for i, line in enumerate(fin):
        if not (line.startswith('[ ]') or line.startswith('[x]')):
            raise ValueError('badness on line %d: %r' % (i, line))

        yield line


def add(source_dir, dest_dir, to_add, extensions=('.mp3', '.mp4', '.wma', '.opus')):
    for relpath in to_add:
        source_path = os.path.join(args.source, relpath)
        dest_path = os.path.join(args.destination, relpath)
        os.makedirs(dest_path, exist_ok=True)
        for f in sorted(os.listdir(source_path)):
            name, ext = os.path.splitext(f)
            if f.startswith('._') or ext.lower() not in extensions:
                continue
            copyfrom = os.path.join(source_path, f)
            copyto = os.path.join(dest_path, f)
            print('cp %r %r' % (copyfrom, copyto))
            shutil.copy(copyfrom, copyto)


def remove(root_path, to_remove):
    for relpath in to_remove:
        dest_path = os.path.join(root_path, relpath)
        shutil.rmtree(dest_path)

        parent_path = os.path.dirname(dest_path)
        if not os.listdir(parent_path):
            os.rmdir(parent_path)


fname = 'ghettosync.tmp'
with open(fname, 'w') as fout:
    with contextlib.redirect_stdout(fout):
        subdirs = list(print_buffer(args.source, args.destination))

subprocess.check_call([os.environ.get('EDITOR', 'vim'), fname])

with open(fname, 'r') as fin:
    lines = list(read_buffer(fin))

assert len(lines) == len(subdirs), 'number of lines has changed'

to_remove = []
to_add = []

for line, relpath in zip(lines, subdirs):
    source_path = os.path.join(args.source, relpath)
    dest_path = os.path.join(args.destination, relpath)
    dest_exists = os.path.isdir(dest_path)
    if dest_exists and line.startswith('[ ]'):
        to_remove.append(relpath)
    elif not dest_exists and line.startswith('[x]'):
        to_add.append(relpath)


#
# TODO: check for enough disk space (net transfer)
#
remove(args.destination, to_remove)
add(args.source, args.destination, to_add)
