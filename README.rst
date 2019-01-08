Flickr Incremental Backup
=========================

A tool to incrementally backup your photos from `Flickr <http://flickr.com>`_.

Installation
-------------

Reqiures Python 2.7 and `pip`.

    $ pip install flickrbackup

Usage
-----

Note: You must have a Flickr Pro account to use this tool, since Flickr only
allows access to original-scale images for Pro members.

The first time you run flickrbackup, you should specify a start date, using the
format ``YYYY-MM-DD``::

    $ flickrbackup -f 2012-02-28 -v photos

This will launch a web browser and ask you to authorize flickrbackup with your
Flickr account, if you haven't already. You may need to restart the script
after this step.

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

    flickrbackup /path/to/photos

Here, we have also omitted the "-v" (verbose) flag, which means only errors and
important messages are output to the console, as well as a log of the ids of the
photos that have been processed (mostly as a progress indicator).

It may be useful to log important messages to a file. In this case, use the
``--log-file`` (``-l``) option (with or without the ``-v`` flag to control the
amount of information output)::

    flickrbackup -l /var/log/flickrbackup.log /path/to/photos

The log file will contain the type of message (e.g. ``INFO`` for informational
messages or ``WARN`` for warnings) and the date and time of the message as well.

What if there are errors, e.g. due to a temporary conneciton problem?
flickrbackup will attempt to download them again (you can control how many times
or turn this off using the ``--retry`` option; the default is to retry once),
but if there are still errors they will be printed to the console/log file.

We can store a list of the ids of the photos and videos that were not correctly
processed by using the ``--error-file`` (``-e``) flag::

    flickrbackup -e /path/to/photos/errors.txt /path/to/photos

Later, we can attempt to manually re-process just these photos using the
``--download`` (``-d``) option::

    $ flickrbackup --download /path/to/photos/errors.txt /path/to/photos

If this succeeds, you should delete ``errors.txt``, since the ``-e`` option
will always append to, not replace, this file.

To see further help, run::

    $ flickrbackup --help

Known limitations
-----------------

* Movie files will always get the extension ``.mov``, even if originally
  uploaded as e.g. ``.avi`` or ``.mpg``, because Flickr doesn't provide a
  means of discovering the original file extension.
* Photos that are deleted or moved between sets after being backed up will
  remain in the backup.

Running on a server or NAS device
---------------------------------

You may find it useful to run flickrbackup on a server or a device such as the
Netgear ReadyNAS Duo as a nightly scheduled job (e.g. using ``cron``), to back
up new or changed photos regularly.

In this case, you may find it difficult to authorise the app with Flickr on
its first run, as this requires a web browser. The solution is to run it once
on your local machine, and then copy the authorisation token file that is
stored in ``~/.flickr`` to the server or NAS device::

    $ scp -r ~/.flickr user@server:~/

Usage on a ReadyNAS Duo
~~~~~~~~~~~~~~~~~~~~~~~

flickrbackup should work on any Mac, Linux or Unix-like system, and may work on
Windows (although this is untested). On the ReadyNAS Duo, however, (and possibly
other Netgear ReadyNAS devices) installation is a little more tricky, due to the
limited nature of the system. Some hints follow:

* Enable remote shell access (log in using ``ssh`` as user ``root`` with your
  admin password) and set up email alerting in the ReadyNAS administration
  interface.
* Install Python, e.g. using the (commercial) add-on at
  http://readynasxtras.com/readynas-sparc-add-ons/python-26-sparc
* In theory, this should support Distribute/setuptools and hence the standard
  installation instructions, but the current version has a bug that makes
  any ``easy_install`` installation fail. To solution is to manually copy
  the following files to ``/usr/local/lib/python2.7/dist-packages`` on the
  ReadyNAS:

  * ``threadpool.py`` from the archive at http://pypi.python.org/pypi/threadpool
  * the ``flickrapi`` subdirectory from within the archive at http://pypi.python.org/pypi/flickrapi
  * ``flickrbackup.py`` from the archive at http://pypi.python.org/pypi/flickrbackup

  Then, make ``flickrbackup.py`` executable by running::

    $ chmod +x /usr/local/lib/python2.7/dist-packages/flickrbackup.py
    $ ln -s /usr/local/lib/python2.7/dist-packages/flickrbackup.py /usr/local/bin/flickrbackup.py

* Copy the authentication token to the ReadyNAS device as outlined above
* Run the script once to download the initial set::

    $ flickrbackup.py -k -f 2001-01-01 -e /c/photos/errors.txt /c/photos

  This may take a long time. Put ``nohup`` in front of the command to let it run
  even after you close the ssh session. Output will be placed in ``nohup.out``.
* Create a ``cron`` job to run the incremental backup nightly. For example,
  create ``/etc/cron.daily/flickrbackup`` with::

    #!/bin/sh

    dest=/c/photos
    email=you@example.com

    flickrbackup.py -e ${dest}/errors.txt -l /var/log/flickrbackup.log ${dest}
    rc=$?

    if [[ $rc != 0 ]]; then
        echo "An error occurred. Please check the logs." | mail -s "flickrbackup error" ${email}
    else
        echo "Backup succeeded" | mail -s "flickrbackup success" ${email}
    fi

  Make this executable::

    $ chmod +x /etc/cron.daily/flickrbackup

  This will run an incremental backup to ``/c/photos`` (which you can set up
  as a share), with erroneous items logged to ``/c/photos/errors.txt`` and
  error output logged to ``/var/log/flickrbackup.log``. After the backup is
  complete, an email will be sent to ``you@example.com`` (replace with your own
  email address, obviously).

Changelog
---------

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
