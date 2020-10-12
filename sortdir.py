"""Sort a directory's contents by name.

Moves contents to a temporary directory first, and then copies them back in
in the correct order.

Useful for devices that rely on file creation time to sort contents.
"""
import logging
import os

_LOGGER = logging.getLogger(__name__)


def sortdir(path: str) -> None:
    assert os.path.isdir(path)

    temp_path = os.path.join(path, 'sortdir')
    assert not os.path.isdir(temp_path)

    subdirs = [
        x.name for x in os.scandir(path)
        if x.is_dir() and not x.name.startswith('.')
    ]
    by_name = sorted(subdirs)

    #
    # Unfortunately, using pathlib.Path(...).touch() is not enough.
    # TODO: determine if subdir is already sorted, and exit early.
    # Not sure what my device uses to sort, it appears to not ctime, mtime or atime.
    #

    renamed = []
    os.mkdir(temp_path)
    try:
        for f in by_name:
            src = os.path.join(path, f)
            dst = os.path.join(temp_path, f)
            os.rename(src, dst)
            renamed.append((src, dst))
    finally:
        for src, dst in renamed:
            _LOGGER.info('processed: %r', src)
            os.rename(dst, src)

        os.rmdir(temp_path)


def main():
    import sys
    logging.basicConfig(level=logging.INFO)
    sortdir(sys.argv[1])


if __name__ == '__main__':
    main()
