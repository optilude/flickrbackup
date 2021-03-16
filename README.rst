Flickr Incremental Backup
=========================

A tool to incrementally backup your photos from `Flickr <http://flickr.com>`_.

Note: As of version 0.9, this now uses Python 3!

Installation
-------------

Reqiures Python 3 and `pip`.

    $ pip install flickrbackup

Usage
-----

Note: You must have a Flickr Pro account to use this tool, since Flickr only
allows access to original-scale images for Pro members.

The first time you run flickrbackup, you should specify a start date, using the
format ``YYYY-MM-DD``::

    $ flickrbackup.py -f 2012-02-28 photos

This will ask you to visit a URL to authorize flickrbackup with your
Flickr account, if you haven't already. You will then be given a short token
by Flickr, which you must type into the console. This token is saved for future
use so you shouldn't need any manual intervention again, unless you or Flickr
revoke the token.

Once authorised, flickrbackup will download all photos and videos for the
authorised account that have been created or updated on or after the "from" date
(February 28th, 2012 in this case) into the directory specified (``photos`` in
this case). Items are organised into subfolders by set and the year, month and
day they were taken. If an item appears in multiple sets, it will be copied into
both set directories. Metadata such as the title, description, tags and other
information will be placed in a file with a ``.txt`` extension next to the image
file. The image file name is based on the Flickr id of the image.

After the first successful run, a special file named ``.stamp`` will be placed
in the download directory, containing the date of the last backup. This allows
flickrbackup to be run again without the ``-f`` argument, for example in a
scheduled nightly "cron" job, picking up from where it left off::

    $ flickrbackup.py /path/to/photos

Here, we have also omitted the "-v" (verbose) flag, which means only errors and
important messages are output to the console, as well as a log of the ids of the
photos that have been processed (mostly as a progress indicator).

It may be useful to log important messages to a file. In this case, use the
``--log-file`` (``-l``) option (with or without the ``-v`` flag to control the
amount of information output)::

    $ flickrbackup.py -l /var/log/flickrbackup.log /path/to/photos

The log file will contain the type of message (e.g. ``INFO`` for informational
messages or ``WARN`` for warnings) and the date and time of the message as well.

What if there are errors, e.g. due to a temporary conneciton problem?
flickrbackup will attempt to download them again (you can control how many times
or turn this off using the ``--retry`` option; the default is to retry once),
but if there are still errors they will be printed to the console/log file.

We can store a list of the ids of the photos and videos that were not correctly
processed by using the ``--error-file`` (``-e``) flag::

    $ flickrbackup.py -e /path/to/photos/errors.txt /path/to/photos

Later, we can attempt to manually re-process just these photos using the
``--download`` (``-d``) option::

    $ flickrbackup.py --download /path/to/photos/errors.txt /path/to/photos

If this succeeds, you should delete ``errors.txt``, since the ``-e`` option
will always append to, not replace, this file.

As of version 0.10 it is also possible to download the authenticated user'
favorite photos (which could be uploaded by another user). In this case,
files are always organised by date and not set::

    $ flickrbackup.py --favorites /path/to/faves

To see further help, run::

    $ flickrbackup.py --help

Known limitations
-----------------

* Movie files will always get the extension ``.mov``, even if originally
  uploaded as e.g. ``.avi`` or ``.mpg``, because Flickr doesn't provide a
  means of discovering the original file extension.
* Photos that are deleted or moved between sets after being backed up will
  remain in the backup.

Logging out
-----------

OAuth tokens are stored in a database in `~/.flickr/oauth-tokens.sqlite`. If
you need to, you can delete this file to force re-authorization.

Changelog
---------

Version 0.9.1, released 2019-08-15
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Make metadata files use UTF-8 by default

Version 0.9.0, released 2019-08-15
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Migrate to Python 3 and new `flickrapi` library
* Make use of new command line solution for getting the auth token, thereby
  making it easier to run on a remote server.

Version 0.8.4, released 2019-01-08
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Fix README to stop referring to a defunct website in the installation instructions

Version 0.8.3, released 2018-10-03
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Fix encoding error with set names


Version 0.8.2, released 2013-07-29
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Attempt to fix missing README.rst issue in tarball

Version 0.8.1, released 2013-06-01
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Fixed potential issue with copying directories to sets they are already in

Version 0.7, released 2013-01-01
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Added ``--log-file`` option
* Added ``-download`` option
* Added ``--retry`` and ``--error-file`` options

Version 0.6, released 2012-12-31
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Exit with a nonzero return code on failure

Version 0.5, released 2012-12-31
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Allow set names with characters that are not valid directory names
* Print erroneous items at the end of the run

Version 0.4, released 2012-12-31
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* In non-verbose mode, print photo id instead of just "." for each completed
  download.

Version 0.3, released 2012-12-31
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Added ``--store-once`` and ``--keep-existing`` options
* Removed ``--username`` option - you must authenticate as the user to use
