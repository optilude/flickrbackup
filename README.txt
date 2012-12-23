Flickr backup
=============

A tool to incrementally backup your photos from Flickr.

Installation
-------------

1. Install Python 2.7 (http://python.org) if you don't have it already:

2. Install pip::

    $ wget http://python-distribute.org/distribute_setup.py
    $ python2.7 distribute_setup.py
    $ easy_install pip

3. Install package from PyPI::

    $ pip install flickrbackup

Usage
-----

Note: You must have a Flickr Pro account to use this tool, since Flickr only
allows access to original-scale images for Pro members.

The first time you run flickrbackup, you should specify a start date, using the
format YYYY-MM-DD::

    $ flickrbackup -u bob -f 2012-02-28 -v photos

This will launch a web browser and ask you to authorize flickrbackup with your
Flickr account, if you haven't already. You may need to restart the script
after this step.

Once authorised, flickrbackup will download all photos and videos for the user
specified ("bob" in this case) that have been created or updated on or after the
"from" date (February 28th, 2012 in this case) into the directory specified
("photos" in this case). Items are organised into subfolders by set and the
year, month and day they were taken. If an item appears in multiple sets, it
will be copied into both set directories. Metadata such as the title,
description, tags and other information will be placed in a file with a ".txt"
extension next to the image file. The image file name is based on the Flickr id
of the image.

After the first successful run, a special file named ".stamp" will be placed in
the download directory, containing the date of the last backup. This allows
flickrbackup to be run again without the "-f" argument, for example in a
scheduled nightly "cron" job::

    flickrbackup -u bob /path/to/photos

Here, we have also omitted the "-v" (verbose) flag, which means only errors and
important messages are output to the console.

To see further help, run::

    $ flickrbackup --help
