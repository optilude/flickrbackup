#! /usr/bin/python
#
# requires flickrapi, threadpool
# Baesd on http://nathanvangheem.com/scripts/migrateflickrtopicasanokeyresize.py

from __future__ import print_function

import os
import os.path
import shutil
import datetime
import argparse
import urllib
import flickrapi
import threadpool
import threading
import sys
import logging
import tempfile

FLICKR_API_KEY = "39b564af2057a7d014875e4939a292db"
FLICKR_API_SECRET = "32cb192e3b9c43e6"

METADATA_EXTENSION = 'txt'
STAMP_FILENAME = '.stamp'

THREADED = True  # Turn off for easier debugging
dirlock = threading.RLock()


def retrieve_flickr_token():
    flickr_api = flickrapi.FlickrAPI(FLICKR_API_KEY, secret=FLICKR_API_SECRET)

    (token, frob) = flickr_api.get_token_part_one(perms='write')
    if not token:
        raw_input("Press ENTER after you authorized this program")
    flickr_api.get_token_part_two((token, frob))

    flickr_usernsid = flickr_api.auth_checkToken(auth_token=token).find('auth').find('user').get('nsid')

    return (flickr_api, flickr_usernsid)


#
# Run
#


def run(destination, min_date, store_once=False, keep_existing=False, verbose=False, threadpoolsize=7):
    if not os.path.exists(destination):
        os.mkdir(destination)

    if verbose:
        print('Authenticating with Flickr.')
    flickr_api, flickr_usernsid = retrieve_flickr_token()
    if verbose:
        print("Done")

    def get_photo_url(info):
        if info.get('media') == 'video':
            return "http://www.flickr.com/photos/%s/%s/play/orig/%s" % (flickr_usernsid, info.get('id'), info.get('originalsecret'))
        else:
            return info.get('url_o')

    def get_photo_sets(info):
        return flickr_api.photos_getAllContexts(photo_id=info.get('id')).findall('set')

    def get_set_directory(set_info):
        dirname = os.path.join(destination, set_info.get('title'))
        with dirlock:
            if not os.path.exists(dirname):
                os.mkdir(dirname)
        return dirname

    def get_date_directory(parent, info):
        date_taken = info.get('datetaken').split(' ')[0]
        year, month, day = date_taken.split('-')
        dirname = os.path.join(parent, year, month, day)
        with dirlock:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
        return dirname

    def write_metadata(photo_filepath, photo):
        filename = photo_filepath + "." + METADATA_EXTENSION
        with open(filename, 'w') as f:
            f.write("[Information]\n")
            f.write((u"id = %s\n" % photo.get('id')).encode('utf-8'))
            f.write((u"title = %s\n" % photo.get('title')).encode('utf-8'))
            f.write((u"description = %s\n" % (photo.find('description').text or "")).encode('utf-8'))
            f.write((u"public = %s\n" % ("yes" if photo.get('ispublic') == "1" else "no")).encode('utf-8'))
            f.write((u"friends = %s\n" % ("yes" if photo.get('isfriend') == "1" else "no")).encode('utf-8'))
            f.write((u"family = %s\n" % ("yes" if photo.get('isfamily') == "1" else "no")).encode('utf-8'))
            f.write((u"taken = %s\n" % photo.get('datetaken')).encode('utf-8'))
            f.write((u"tags = %s\n" % photo.get('tags')).encode('utf-8'))

    thread_pool = threadpool.ThreadPool(threadpoolsize)

    def download_photo(photo):

        try:

            def download_callback(count, blocksize, totalsize):
                if not verbose:
                    return

                download_stat_print = set((0.0, .25, .5, 1.0))
                downloaded = float(count * blocksize)
                res = int((downloaded / totalsize) * 100.0)

                for st in download_stat_print:
                    dl = totalsize * st
                    diff = downloaded - dl
                    if diff >= -(blocksize / 2) and diff <= (blocksize / 2):
                        downloaded_so_far = float(count * blocksize) / 1024.0 / 1024.0
                        total_size_in_mb = float(totalsize) / 1024.0 / 1024.0
                        print("Photo: %s --- %i%% - %.1f/%.1fmb" % (photo.get('title'), res, downloaded_so_far, total_size_in_mb))

            photo_url = get_photo_url(photo)

            dirname = destination

            if photo.get('media') == 'video':
                # XXX: There doesn't seem to be a way to discover original file extension (?)
                filename = photo.get('id') + ".mov"
            else:
                filename = photo.get('id') + "." + photo.get('originalformat')

            # Create a photo set directory from the first set the photo is a member of
            photo_sets = get_photo_sets(photo)
            if len(photo_sets) > 0:
                dirname = get_set_directory(photo_sets[0])

            dirname = get_date_directory(dirname, photo)

            # Download
            if verbose:
                print('Processing photo "%s" at url "%s".' % (photo.get('title'), photo_url))

            filepath = os.path.join(dirname, filename)

            if keep_existing and os.path.exists(filepath):
                if verbose:
                    print('Image "%s" at %s already exists.' % (photo.get('title'), filepath))
            else:
                tmp_fd, tmp_filename = tempfile.mkstemp()
                tmp_filename, headers = urllib.urlretrieve(photo_url, tmp_filename, download_callback)
                shutil.move(tmp_filename, filepath)
                os.close(tmp_fd)

                write_metadata(filepath, photo)
                if verbose:
                    print('Download of "%s" at %s to %s finished.' % (photo.get('title'), photo_url, filepath))

            # Copy to additional set directories
            if not store_once:
                for photo_set in photo_sets[1:]:
                    copy_dirname = get_set_directory(photo_set)
                    copy_dirname = get_date_directory(copy_dirname, photo)
                    copy_filepath = os.path.join(copy_dirname, filename)

                    if keep_existing and os.path.exists(filepath):
                        if verbose:
                            print('Image "%s" at %s already exists.' % (photo.get('title'), filepath))
                    else:
                        shutil.copyfile(filepath, copy_filepath)
                        shutil.copyfile(filepath + "." + METADATA_EXTENSION, copy_filepath + "." + METADATA_EXTENSION)
                        if verbose:
                            print('Photo "%s" also copied to %s' % (photo.get('title'), copy_filepath,))

            if not verbose:
                print(".")
        except Exception:
            logging.exception("An unexpected error occurred downloading %s (%s)" % (photo.get('title'), photo.get('id'),))
            raise

    page = 1
    has_more_pages = True
    total_printed = False

    while has_more_pages:
        recently_updated = flickr_api.photos_recentlyUpdated(
            min_date=min_date,
            extras="description,url_o,media,original_format,date_upload,date_taken,tags,machine_tags",
            per_page=500,
            page=page
        ).find('photos')

        if page >= int(recently_updated.get('pages')):
            has_more_pages = False
        else:
            page += 1

        if not total_printed:
            print("Processing %s photos" % recently_updated.get('total'))
            total_printed = True

        for photo in recently_updated.findall('photo'):
            if THREADED:
                req = threadpool.WorkRequest(download_photo, [photo], {})
                thread_pool.putRequest(req)
            else:
                download_photo(photo)

    thread_pool.wait()

#
# CLI
#


def parse_args():
    parser = argparse.ArgumentParser(description='Incremental Flickr backup')
    parser.add_argument('-f', '--from', dest='from_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Log progress information')
    parser.add_argument('-o', '--store-once', action='store_true', help='Only store photos once, even if they appear in multiple sets')
    parser.add_argument('-k', '--keep-existing', action='store_true', help='Keep existing photos (default is to replace in case they have changed)')
    parser.add_argument('destination', help='Destination directory')

    return parser.parse_args()

if __name__ == '__main__':
    arguments = parse_args()

    destination = arguments.destination
    from_date = arguments.from_date

    # Figure out the start date
    stamp_filename = os.path.join(destination, STAMP_FILENAME)
    if not from_date:
        if os.path.exists(stamp_filename):
            with open(stamp_filename, 'r') as stamp:
                from_date = stamp.read().strip()
    if not from_date:
        logging.error("No start date specified and no previous time stamp found in %s." % stamp_filename)
        sys.exit(1)

    # Capture today's date (the script may run for more than one day)
    today = datetime.date.today().isoformat()

    # Run the backup
    print("Running backup of images updated since %s" % from_date)
    run(destination, from_date, arguments.store_once, arguments.keep_existing, arguments.verbose)

    # Store today's date
    with open(stamp_filename, 'w') as stamp:
        stamp.write(today)
