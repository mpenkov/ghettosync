import argparse
import contextlib
import json
import os
import shutil
import subprocess

import fs

from typing import (
    Dict,
    IO,
    Iterator,
    Tuple,
)

EXTENSIONS = (
    '.flac',
    '.m4a',
    '.mp3',
    '.mp4',
    '.opus',
    '.wma',
)

parser = argparse.ArgumentParser()
parser.add_argument('source')
parser.add_argument('destination')
args = parser.parse_args()

myfs = fs.open_fs(args.source)


def getsize(dirpath: str) -> int:
    #
    # ignores subdirectories entirely
    #
    mb = 0
    for f in myfs.scandir(dirpath, namespaces=['details']):
        if not f.is_dir:
            mb += f.size // 1024**2
    return mb


def scan(source: str) -> Iterator[Tuple[str, int]]:
    for topdir in sorted(myfs.scandir('.'), key=lambda de: de.name):
        if not topdir.is_dir:
            continue

        for bottomdir in sorted(myfs.scandir(topdir.name), key=lambda de: de.name):
            if not bottomdir.is_dir:
                continue

            relpath = os.path.join(topdir.name, bottomdir.name)
            yield relpath, getsize(relpath)


def print_buffer(cache: Dict, destination: str) -> None:
    for x in cache['subdirs']:
        bottomdir_dest = os.path.join(destination, x['relpath'])
        bottomdir_check = 'x' if os.path.isdir(bottomdir_dest) else ' '
        print('[%s] (% 6d MB) %s' % (bottomdir_check, x['sizemb'], x['relpath']))


def read_buffer(fin: IO[str]) -> Iterator[str]:
    for i, line in enumerate(fin):
        if not (line.startswith('[ ]') or line.startswith('[x]')):
            raise ValueError('badness on line %d: %r' % (i, line))
        yield line


def add(source_dir, dest_dir, to_add):
    for relpath in to_add:
        dest_path = os.path.join(args.destination, relpath)
        os.makedirs(dest_path, exist_ok=True)
        for f in sorted(myfs.listdir(relpath)):
            name, ext = os.path.splitext(f)
            if f.startswith('._') or ext.lower() not in EXTENSIONS:
                continue
            copyfrom = os.path.join(relpath, f)
            copyto = os.path.join(dest_path, f)
            print('cp %r %r' % (copyfrom, copyto))

            with open(copyto, 'wb') as fout:
                myfs.download(copyfrom, fout)


def remove(root_path, to_remove):
    for relpath in to_remove:
        dest_path = os.path.join(root_path, relpath)
        print('rm -rf %r' % dest_path)
        shutil.rmtree(dest_path)

        parent_path = os.path.dirname(dest_path)
        if not os.listdir(parent_path):
            os.rmdir(parent_path)
            print('rm -rf %r' % parent_path)


cache_name = 'ghettosync.json'

with open(cache_name) as fin:
    cache = json.load(fin)

if cache['source'] != args.source:
    #
    # Cache is invalid, repopulate.
    #
    cache = {
        'source': args.source,
        'subdirs': [{'relpath': r, 'sizemb': s} for (r, s) in scan(args.source)],
    }
    with open(cache_name, 'w') as fout:
        json.dump(cache, fout, sort_keys=True, ensure_ascii=False)

#
# TODO: use tempfile here
#
fname = 'ghettosync.tmp'
with open(fname, 'w') as fout:
    with contextlib.redirect_stdout(fout):
        print_buffer(cache, args.destination)

subprocess.check_call([os.environ.get('EDITOR', 'vim'), fname])

with open(fname, 'r') as fin:
    lines = list(read_buffer(fin))

assert len(lines) == len(cache['subdirs']), 'number of lines has changed'

to_remove = []
to_add = []

for line, subdir in zip(lines, cache['subdirs']):
    relpath = subdir['relpath']
    source_path = os.path.join(args.source, relpath)
    dest_path = os.path.join(args.destination, relpath)
    dest_exists = os.path.isdir(dest_path)
    if dest_exists and line.startswith('[ ]'):
        to_remove.append(relpath)
    elif not dest_exists and line.startswith('[x]'):
        to_add.append(relpath)

#
# TODO:
#
# - check for enough disk space (net transfer)
# - sort top-level directory after adding files
# - rollback after incomplete directory copy
# - parallelize copying
#
remove(args.destination, to_remove)
add(args.source, args.destination, to_add)
