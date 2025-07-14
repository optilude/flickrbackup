#!/usr/bin/env python3
# requires flickrapi, threadpool
# Baesd on http://nathanvangheem.com/scripts/migrateflickrtopicasanokeyresize.py

import os
import os.path
import re
import shutil
import datetime
import dateutil.parser
import argparse
import urllib.request
import flickrapi
import flickrapi.exceptions
import threadpool
import threading
import sys
import logging
import tempfile

FLICKR_API_KEY = "39b564af2057a7d014875e4939a292db"
FLICKR_API_SECRET = "32cb192e3b9c43e6"

METADATA_EXTENSION = 'txt'
STAMP_FILENAME = '.stamp'

dirlock = threading.RLock()

logger = logging.getLogger('flickrbackup')

# TODO: Some video download links redirect to the CDN with a signed request but respond with a 404 Not Found
# - It's unclear why this happens to some but not all videos
# - The same base URLs (pre-redirect) seem to work in the browser when authenticated
# - Need to test with a larger set of images and videos

# XXX: This hack causes urllib to log all headers, which helps debug redirects
# http_handler = urllib.request.HTTPHandler(debuglevel=1)
# https_handler = urllib.request.HTTPSHandler(debuglevel=1)
# opener = urllib.request.build_opener(http_handler, https_handler)
# urllib.request.install_opener(opener)
# /XXX

class Photo(object):

    def __init__(self,
        id,
        url,
        media='photo',
        original_format='jpg',
        title=None,
        description=None,
        date_taken=None,
        is_public=None,
        is_friend=None,
        is_family=None,
        tags=None,
        flickr_usernsid=None,
    ):
        self.id = id
        self.url = url
        self.media = media
        self.original_format = original_format
        self.title = title
        self.description = description
        self.date_taken = date_taken
        self.is_public = is_public
        self.is_friend = is_friend
        self.is_family = is_family
        self.tags = tags
        self.flickr_usernsid = flickr_usernsid

    @classmethod
    def fromInfo(cls, info, sizes, flickr_usernsid):
        return Photo(
                id=info.get('id'),
                url=cls.findOriginalImageURL(info, sizes, flickr_usernsid),
                media=info.get('media'),
                original_format=info.get('originalformat') or "jpg",
                title=info.find('title').text,
                description=info.find('description').text,
                date_taken=info.find('dates').get('taken'),
                is_public=info.find('visibility').get('ispublic') == '1',
                is_friend=info.find('visibility').get('isfriend') == '1',
                is_family=info.find('visibility').get('isfamily') == '1',
                tags=[t.text for t in info.find('tags').findall('tag')],
                flickr_usernsid=flickr_usernsid,
            )

    @classmethod
    def fromSearchResult(cls, info, sizes, flickr_usernsid=None):
        return Photo(
                id=info.get('id'),
                url=cls.findOriginalImageURL(info, sizes, flickr_usernsid),
                media=info.get('media'),
                original_format=info.get('originalformat') or "jpg",
                title=info.get('title'),
                description=info.find('description').text,
                date_taken=info.get('datetaken'),
                is_public=info.get('ispublic') == '1',
                is_friend=info.get('isfriend') == '1',
                is_family=info.get('isfamily') == '1',
                tags=info.get('tags').split(' '),
                flickr_usernsid=info.get('owner') or flickr_usernsid,
            )

    @classmethod
    def findOriginalImageURL(cls, info, sizes, flickr_usernsid):
        """Find the URL of the original image for downloading
        """

        media = info.get('media', 'photo')
        url = None

        if media == 'video':
            for size in sizes.findall('size'):
                if size.get('label') == 'Video Original':
                    url = size.get('source')
            if url is None:
                url = "http://www.flickr.com/photos/%s/%s/play/orig/%s" % (flickr_usernsid, info.get('id'), info.get('originalsecret'),)
        else:
            url = info.get('url_o') or "http://farm%s.staticflickr.com/%s/%s_%s_o.%s" % (info.get('farm'), info.get('server'), info.get('id'), info.get('originalsecret'), info.get('originalformat') or 'jpg',)

        return url


class FlickrBackup(object):

    def __init__(self, destination, store_once=False, keep_existing=False, favorites=False, retry=1, verbose=False, token_cache=None, threaded=True, threadpoolsize=7):
        self.destination = destination
        self.store_once = store_once
        self.keep_existing = keep_existing
        self.favorites = favorites
        self.max_retries = retry
        self.verbose = verbose
        self.threadpoolsize = threadpoolsize
        self.token_cache = token_cache
        self.threaded = threaded

        # Initialise connection to Flickr
        self.flickr_api, self.flickr_usernsid = self.retrieve_flickr_token()

    # Operations

    def download_photo(self, photo):
        """Download a single Photo
        """

        def download_callback(count, blocksize, totalsize):
            if not self.verbose:
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
                    print("Photo: %s --- %i%% - %.1f/%.1fmb" % (photo.title, res, downloaded_so_far, total_size_in_mb))

        dirname = self.destination
        photo_sets = []

        if photo.media == 'video':
            # XXX: There doesn't seem to be a way to discover original file extension (?)
            filename = photo.id + ".mov"
        else:
            filename = photo.id + "." + photo.original_format

        if not self.favorites:
            # Create a photo set directory from the first set the photo is a member of
            photo_sets = self.get_photo_sets(photo)
            if len(photo_sets) > 0:
                dirname = self.get_set_directory(photo_sets[0])

        dirname = self.get_date_directory(dirname, photo)

        # Download
        logger.debug('Processing photo "%s" at url "%s".', photo.title, photo.url)

        filepath = os.path.join(dirname, filename)

        if self.keep_existing and os.path.exists(filepath):
            logger.debug('Image "%s" at %s already exists.', photo.title, filepath)
        else:
            tmp_fd, tmp_filename = tempfile.mkstemp()
            download_404 = False
            try:
                tmp_filename, _ = urllib.request.urlretrieve(photo.url, tmp_filename, download_callback)
                os.close(tmp_fd)
                shutil.move(tmp_filename, filepath)
                logger.debug('Download of "%s" at %s to %s finished.', photo.title, photo.url, filepath)
            except urllib.error.HTTPError as e:
                os.close(tmp_fd)
                os.unlink(tmp_filename)
                if e.code == 404:
                    # For 404 errors, just set the flag and continue
                    download_404 = True
                    logger.warning("Photo %s (%s) not found at %s. Will write metadata only.", photo.title, photo.id, photo.url)
                else:
                    raise
            except:
                os.close(tmp_fd)
                os.unlink(tmp_filename)
                raise
            
            # Write metadata for both successful downloads and 404s
            self.write_metadata(filepath, photo)

        # Copy to additional set directories
        if not self.store_once and not self.favorites:
            metadata_exists = os.path.exists(filepath + "." + METADATA_EXTENSION)
            image_exists = os.path.exists(filepath)
            
            for photo_set in photo_sets[1:]:
                copy_dirname = self.get_set_directory(photo_set)
                copy_dirname = self.get_date_directory(copy_dirname, photo)
                copy_filepath = os.path.join(copy_dirname, filename)

                if self.keep_existing and os.path.exists(copy_filepath):
                    logger.debug('Image "%s" at %s already exists.', photo.title, filepath)
                elif filepath != copy_filepath:
                    if image_exists:
                        shutil.copyfile(filepath, copy_filepath)
                    if metadata_exists:
                        shutil.copyfile(filepath + "." + METADATA_EXTENSION, copy_filepath + "." + METADATA_EXTENSION)
                    logger.debug('Photo "%s" metadata%s copied to %s', 
                               photo.title,
                               " and image" if image_exists else "",
                               copy_filepath)

        # Give visual feedback in the console, but don't log
        if not self.verbose:
            print(photo.id)

        if download_404:
            raise urllib.error.HTTPError(photo.url, 404, "Not Found", None, None)

        return True

    def run(self, min_date, error_file=None):
        """Run a backup of all photos taken since min_date
        """

        if not os.path.exists(self.destination):
            os.mkdir(self.destination)

        items_with_errors = []
        thread_pool = threadpool.ThreadPool(self.threadpoolsize)

        page = 1
        has_more_pages = True
        total_printed = False


        while has_more_pages:
            recently_updated = self.flickr_api.favorites_getList(
                min_fave_date=dateutil.parser.parse(min_date).strftime('%s'),
                extras="description,url_o,media,original_format,date_upload,date_taken,tags,machine_tags",
                per_page=500,
                page=page
            ).find('photos') if self.favorites else self.flickr_api.photos_recentlyUpdated(
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
                logger.info("Processing %s photos", recently_updated.get('total'))
                total_printed = True

            for item in recently_updated.findall('photo'):
                # Decorate with the Photo class
                sizes = self.flickr_api.photos_getSizes(photo_id=item.get('id'))
                photo = Photo.fromSearchResult(item, sizes, flickr_usernsid=self.flickr_usernsid)

                if self.threaded:
                    req = threadpool.WorkRequest(
                        lambda p: self._initiate_download(p, items_with_errors),
                        [photo],
                        {}
                    )
                    thread_pool.putRequest(req)
                else:
                    self._initiate_download(photo, items_with_errors)

        thread_pool.wait()

        if items_with_errors:
            logger.warning("%d items could not be downloaded. Retrying %d times.", len(items_with_errors), self.max_retries)
            return self.retry(items_with_errors, error_file=error_file)

        return True

    def download(self, ids, error_file=None):
        """Download photos with the given ids
        """

        if not os.path.exists(self.destination):
            os.mkdir(self.destination)

        items_with_errors = []
        thread_pool = threadpool.ThreadPool(self.threadpoolsize)

        logger.info("Processing %d photos", len(ids))

        for id in ids:
            item = None

            try:
                item = self.flickr_api.photos_getInfo(photo_id=id)
                sizes = self.flickr_api.photos_getSizes(photo_id=id)
            except:
                logger.exception("An unexpected error occurred getting info for photo id %s", id)
                items_with_errors.append((id, None,))
                continue
            
            photo = Photo.fromInfo(item.find('photo'), sizes.find('sizes'), flickr_usernsid=self.flickr_usernsid)

            if self.threaded:
                req = threadpool.WorkRequest(
                    lambda p: self._initiate_download(p, items_with_errors),
                    [photo],
                    {}
                )
                thread_pool.putRequest(req)
            else:
                self._initiate_download(photo, items_with_errors)

        thread_pool.wait()

        if items_with_errors:
            if self.verbose:
                logger.warning("%d items could not be downloaded. Retrying %d times", len(items_with_errors), self.max_retries)
            return self.retry(items_with_errors, error_file=error_file)

        return True

    # Helpers

    def retrieve_flickr_token(self):
        flickr_api = flickrapi.FlickrAPI(FLICKR_API_KEY, FLICKR_API_SECRET, token_cache_location=self.token_cache)

        # Make sure the token is still valid if we have one
        if flickr_api.token_cache.token:
            try:
                flickr_api.test.login()
            except flickrapi.exceptions.FlickrError:
                flickr_api.flickr_oauth.token = None
                del flickr_api.token_cache.token

        # Get a new token via the user if we don't have one
        if not flickr_api.token_cache.token:
            flickr_api.get_request_token(oauth_callback='oob')  
            authorize_url = flickr_api.auth_url(perms='read')

            print("No token found. You must visit this URL and get the verifier code: %s" % authorize_url)
            verifier = input('Enter code: ')
            flickr_api.get_access_token(verifier)

        # Return token information
        flickr_usernsid = flickr_api.token_cache.token.user_nsid
        return (flickr_api, flickr_usernsid)

    def get_photo_sets(self, photo):
        return self.flickr_api.photos_getAllContexts(photo_id=photo.id).findall('set')

    def normalize_filename(self, filename):
        # Take a rather liberal approach to what's an allowable filename
        return re.sub(r'[^\w\-_\. \?\'!]', '_', filename)
        #return filename.replace(os.path.sep, '').encode('ascii', 'xmlcharrefreplace').decode('ascii')

    def get_set_directory(self, set_info):
        dirname = os.path.join(self.destination, self.normalize_filename(set_info.get('title')))
        with dirlock:
            if not os.path.exists(dirname):
                logger.debug("Creating directory %s", dirname)
                os.mkdir(dirname)
        return dirname

    def get_date_directory(self, parent, photo):
        date_taken = photo.date_taken.split(' ')[0]
        year, month, day = date_taken.split('-')
        dirname = os.path.join(parent, year, month, day)
        with dirlock:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
        return dirname

    def write_metadata(self, photo_filepath, photo):
        filename = photo_filepath + "." + METADATA_EXTENSION
        with open(filename, 'w', encoding='utf-8') as f:
            print("[Information]", file=f)
            print("id = %s" % photo.id, file=f)
            print("title = %s" % photo.title, file=f)
            print("description = %s" % (photo.description or ""), file=f)
            print("public = %s" % ("yes" if photo.is_public else "no"), file=f)
            print("friends = %s" % ("yes" if photo.is_friend else "no"), file=f)
            print("family = %s" % ("yes" if photo.is_family else "no"), file=f)
            print("taken = %s" % photo.date_taken, file=f)
            print("tags = %s" % ' '.join(photo.tags), file=f)
            print("url = %s" % photo.url, file=f)

    def retry(self, items_with_errors, error_file=None):
        retry_count = 0
        while retry_count < self.max_retries:
            # Retry, this time without threading
            retry_count += 1

            still_in_error = []
            for id, photo in items_with_errors:
                if photo is not None:
                    self._initiate_download(photo, still_in_error)
            items_with_errors = still_in_error

            if not items_with_errors:
                break

        if items_with_errors:
            logger.error(
                "Download of the following items did not succeed, even after %d retries: %s",
                self.max_retries,
                ' '.join([str(id) for id, _ in items_with_errors])
            )
            if error_file:
                with open(error_file, 'a') as ef:
                    for id, _ in items_with_errors:
                        print(id, file=ef)

            return False

        return True

    def _initiate_download(self, photo, items_with_errors):
        """Helper method to handle threaded downloads of photos.
        
        Args:
            photo: Photo object to download
            items_with_errors: List to append errors to
        """
        try:
            self.download_photo(photo)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.warning("Photo %s (%s) not found at %s. Normally this means Flickr will not allow it to be downloaded.", photo.title, photo.id, photo.url)
            else:
                logger.exception("An unexpected HTTP error occurred downloading %s (%s) from %s", photo.title, photo.id, photo.url)
            items_with_errors.append((photo.id, photo,))
        except Exception:
            logger.exception("An unexpected error occurred downloading %s (%s)", photo.title, photo.id)
            items_with_errors.append((photo.id, photo,))

#
# CLI
#


def main():

    # Process command line arguments

    parser = argparse.ArgumentParser(description='Incremental Flickr backup')
    parser.add_argument('-f', '--from', dest='from_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Log progress information')
    parser.add_argument('-o', '--store-once', action='store_true', help='Only store photos once, even if they appear in multiple sets')
    parser.add_argument('--favorites', action='store_true', help='Download favorites instead of own photos. Implies --store-once and does not organise photos into folders based on sets.')
    parser.add_argument('-k', '--keep-existing', action='store_true', help='Keep existing photos (default is to replace in case they have changed)')
    parser.add_argument('-r', '--retry', type=int, default=1, help='Retry download of failed images N times (default is to retry once)')
    parser.add_argument('-e', '--error-file', help='Append ids of erroneous items to this file, to allow retry later')
    parser.add_argument('-d', '--download', metavar='FILE', help='Attempt to download the photos with the ids in the given file, one per line (usually saved by the --error-file option)')
    parser.add_argument('-l', '--log-file', help='Log warnings and errors to the given file')
    parser.add_argument('--token-cache', dest='token_cache', help="Path to a directory where the login token data will be stored. Must be secure. Defaults to ~/.flickr")
    parser.add_argument('--single-threaded', action='store_false', dest='threaded', help='Run in single-threaded mode (for debugging purposes)')
    parser.add_argument('destination', help='Destination directory')

    arguments = parser.parse_args()

    destination = arguments.destination
    success = False

    # Setup logging

    if arguments.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    logger.propagate = False

    # Console logging
    console_log_handler = logging.StreamHandler()
    console_log_formatter = logging.Formatter('%(message)s')
    console_log_handler.setFormatter(console_log_formatter)
    logger.addHandler(console_log_handler)

    # File logging
    if arguments.log_file:
        file_log_handler = logging.FileHandler(arguments.log_file)
        file_log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', "%Y-%m-%d %H:%M:%S")
        file_log_handler.setFormatter(file_log_formatter)
        logger.addHandler(file_log_handler)

    # Run

    if arguments.download:

        if not os.path.exists(arguments.download):
            logger.error("Download file %s does not exist.", arguments.download)
            sys.exit(2)

        logger.info("Running backup of images found in %s", arguments.download)
        with open(arguments.download, 'r') as f:
            ids = [id.strip() for id in f.readlines() if id.strip() and not id.strip().startswith('#')]

        backup = FlickrBackup(destination,
                store_once=arguments.store_once,
                keep_existing=arguments.keep_existing,
                retry=arguments.retry,
                verbose=arguments.verbose,
                token_cache=arguments.token_cache,
                threaded=arguments.threaded
            )
        success = backup.download(ids, arguments.error_file)

    else:

        from_date = arguments.from_date

        # Figure out the start date
        stamp_filename = os.path.join(destination, STAMP_FILENAME)
        if not from_date:
            if os.path.exists(stamp_filename):
                with open(stamp_filename, 'r') as stamp:
                    from_date = stamp.read().strip()

        if not from_date:
            logger.error("No start date specified and no previous time stamp found in %s.", stamp_filename)
            sys.exit(2)

        # Capture today's date (the script may run for more than one day)
        today = datetime.date.today().isoformat()

        # Run the backup
        logger.info("Running backup of images updated since %s", from_date)
        backup = FlickrBackup(destination,
                store_once=arguments.store_once,
                keep_existing=arguments.keep_existing,
                favorites=arguments.favorites,
                retry=arguments.retry,
                verbose=arguments.verbose,
                token_cache=arguments.token_cache,
                threaded=arguments.threaded,
            )
        success = backup.run(from_date, arguments.error_file)

        # Store today's date
        with open(stamp_filename, 'w') as stamp:
            stamp.write(today)

    if not success:
        logger.info("Done, with errors.")
        sys.exit(2)

    logger.info("Done")

if __name__ == '__main__':
    main()