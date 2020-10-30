import argparse
import contextlib
import json
import logging
import os
import shutil
import subprocess
import unicodedata

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
parser.add_argument('--cleanup', action='store_true')
parser.add_argument('--loglevel', default=logging.INFO)
args = parser.parse_args()

logging.basicConfig(level=args.loglevel)
logging.getLogger('paramiko.transport').setLevel(logging.ERROR)

myfs = fs.open_fs(args.source)


#
# Scan the destination instead of checking each artist/album later with
# isdir - that's slow when the source contains a lot of music.
#
destdirs = set()
try:
    for top in os.scandir(args.destination):
        if top.is_dir():
            for bottom in os.scandir(top.path):
                if bottom.is_dir():
                    #
                    # Some devices do weird things to Unicode pathnames.
                    #
                    relpath = os.path.join(top.name, bottom.name)
                    destdirs.add(relpath)
except FileNotFoundError:
    #
    # If the destination does not exist at all.
    #
    pass


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


def print_buffer(cache: Dict, destination: str) -> Iterator[str]:
    normdestdirs = {unicodedata.normalize('NFC', d) for d in destdirs}
    for x in cache['subdirs']:
        exists_in_dest = unicodedata.normalize('NFC', x['relpath']) in normdestdirs
        if args.cleanup and not exists_in_dest:
            continue

        bottomdir_check = 'x' if exists_in_dest else ' '
        print('[%s] (% 6d MB) %s' % (bottomdir_check, x['sizemb'], x['relpath']))
        yield x['relpath']


def read_buffer(fin: IO[str]) -> Iterator[str]:
    for i, line in enumerate(fin):
        if not (line.startswith('[ ]') or line.startswith('[x]')):
            raise ValueError('badness on line %d: %r' % (i, line))
        yield line


def add(source_dir, dest_dir, to_add):
    for relpath in to_add:
        dest_path = os.path.join(args.destination, relpath)
        os.makedirs(dest_path, exist_ok=True)
        try:
            contents = myfs.listdir(relpath)
        except Exception as err:
            logging.error('unable to copy: %r err: %r', relpath, err)
            continue

        for f in sorted(contents):
            name, ext = os.path.splitext(f)
            if f.startswith('._') or ext.lower() not in EXTENSIONS:
                continue
            copyfrom = os.path.join(relpath, f)
            copyto = os.path.join(dest_path, f)
            logging.info('cp %r %r', copyfrom, copyto)

            with open(copyto, 'wb') as fout:
                myfs.download(copyfrom, fout)


def remove(root_path, to_remove):
    for relpath in to_remove:
        dest_path = os.path.join(root_path, relpath)
        assert dest_path.startswith(args.destination)
        print('rm -rf %r' % dest_path)
        shutil.rmtree(dest_path)

        parent_path = os.path.dirname(dest_path)
        assert parent_path.startswith(args.destination)
        if not os.listdir(parent_path):
            os.rmdir(parent_path)
            print('rm -rf %r' % parent_path)


cache_name = 'ghettosync.json'

try:
    with open(cache_name) as fin:
        cache = json.load(fin)
except FileNotFoundError:
    cache = {}

if cache.get('source') != args.source:
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
        subdirs = list(print_buffer(cache, args.destination))

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
    if relpath in destdirs and line.startswith('[ ]'):
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
if to_remove:
    print('The following subdirectories will be removed:')
    for x in to_remove:
        print(x)
    print('Is this OK? yes / [no]')
    if input().lower() in ('y', 'yes'):
        remove(args.destination, to_remove)

add(args.source, args.destination, to_add)
