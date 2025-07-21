#!/usr/bin/env python3
# requires flickrapi, threadpool, requests, selenium (for web session capture)
# Based on http://nathanvangheem.com/scripts/migrateflickrtopicasanokeyresize.py

import os
import os.path
from pathlib import Path
import re
import shutil
import datetime
import dateutil.parser
import argparse
import requests
import flickrapi
import flickrapi.exceptions
import threadpool
import threading
import sys
import logging
import tempfile
import json
import csv
import configparser


FLICKR_API_KEY = "39b564af2057a7d014875e4939a292db"
FLICKR_API_SECRET = "32cb192e3b9c43e6"

METADATA_EXTENSION = 'txt'
STAMP_FILENAME = '.stamp'

dirlock = threading.RLock()

logger = logging.getLogger('flickrbackup')

# Configure default logging format - keep root logger at INFO to avoid debug spam from libraries
logging.basicConfig(
    format='%(message)s',
    level=logging.INFO
)

# Prevent our logger from propagating to avoid duplicate messages
logger.propagate = False

# Suppress noisy logging from flickrapi
logging.getLogger('flickrapi').setLevel(logging.WARNING)

# TODO: Some video download links redirect to the CDN with a signed request but respond with a 404 Not Found
# - It's unclear why this happens to some but not all videos
# - The same base URLs (pre-redirect) seem to work in the browser when authenticated
# - Need to test with a larger set of images and videos

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
                url = f"http://www.flickr.com/photos/{flickr_usernsid}/{info.get('id')}/play/orig/{info.get('originalsecret')}"
        else:
            url = info.get('url_o') or f"http://farm{info.get('farm')}.staticflickr.com/{info.get('server')}/{info.get('id')}_{info.get('originalsecret')}_o.{info.get('originalformat') or 'jpg'}"

        return url


def find_missing_files(directory, output_file, verbose=False):
    """Search for metadata files that are missing their corresponding media files.
    Writes results to a CSV file.
    
    Args:
        directory: Base directory to search for missing files
        output_file: Path to CSV file to write results to
        verbose: Whether to output verbose logging
    """
    missing_files = []
    
    # Walk through directory
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(f".{METADATA_EXTENSION}"):
                metadata_path = os.path.join(root, file)
                media_path = metadata_path[:-len(f".{METADATA_EXTENSION}")]
                
                if not os.path.exists(media_path):
                    # Parse metadata file to get id and url
                    config = configparser.ConfigParser()
                    try:
                        config.read(metadata_path, encoding='utf-8')
                        if 'Information' in config:
                            photo_id = config['Information'].get('id', '')
                            photo_url = config['Information'].get('url', '')
                            missing_files.append([photo_id, photo_url, root])
                    except Exception as e:
                        logger.warning(f"Could not parse metadata file {metadata_path}: {str(e)}")
    
    # Write CSV file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Photo ID', 'URL', 'Directory'])
        writer.writerows(missing_files)
    
    logger.info(f"Found {len(missing_files)} missing files. Results written to {output_file}")
    return True


def obtain_web_session(output_file, browser='chrome', verbose=False):
    """Launch a browser to get authenticated Flickr session data.
    Waits for user to log in manually, then saves the session data.
    
    Args:
        output_file: Path to file where session data will be saved
        browser: Browser to use ('chrome' or 'firefox')
        verbose: Whether to output verbose logging
    """

    from selenium import webdriver

    # Initialize the web driver
    options = None
    driver = None
    
    if browser == 'firefox':
        options = webdriver.FirefoxOptions()
        driver = webdriver.Firefox(options=options)
    else:
        options = webdriver.ChromeOptions()
        driver = webdriver.Chrome(options=options)
    
    try:
        # Go to Flickr login page
        driver.get('https://www.flickr.com/signin')
        logger.info("Browser opened. Please log in to Flickr and then press Enter in this console to continue...")
        input()

        # Get all cookies and local storage
        cookies = driver.get_cookies()
        local_storage = driver.execute_script("return Object.assign({}, window.localStorage);")
        
        # Save session data
        session_data = {
            'cookies': cookies,
            'localStorage': local_storage,
            'url': driver.current_url
        }
        
        with open(output_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        logger.info(f"Session data saved to {output_file}")
        return True
        
    finally:
        driver.quit()


class FlickrBackup(object):

    def __init__(self, destination, store_once=False, keep_existing=False, favorites=False, retry=1, verbose=False, token_cache=None, web_session=None, threaded=True, threadpoolsize=7):
        self.destination = destination
        self.store_once = store_once
        self.keep_existing = keep_existing
        self.favorites = favorites
        self.max_retries = retry
        self.verbose = verbose
        self.threadpoolsize = threadpoolsize
        self.token_cache = token_cache
        self.threaded = threaded
        self.web_session = web_session

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
                    print(f"Photo: {photo.title} --- {res}% - {downloaded_so_far:.1f}/{total_size_in_mb:.1f}mb")

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
        logger.debug(f'Processing photo "{photo.title}" at url "{photo.url}"')

        filepath = os.path.join(dirname, filename)

        if self.keep_existing and os.path.exists(filepath):
            logger.debug('Image "%s" at %s already exists.', photo.title, filepath)
        else:
            tmp_fd, tmp_filename = tempfile.mkstemp()
            download_404 = False
            try:
                # Set up session with cookies if available
                session = requests.Session()
                if self.web_session and 'cookies' in self.web_session:
                    # Add Flickr cookies to the session
                    for cookie in self.web_session['cookies']:
                        if 'flickr' in cookie['domain']:
                            session.cookies.set(
                                cookie['name'], 
                                cookie['value'], 
                                domain=cookie['domain'],
                                path=cookie.get('path', '/')
                            )
                
                # Download file with progress callback if verbose
                response = session.get(photo.url, stream=True)
                response.raise_for_status()
                
                os.close(tmp_fd)
                with open(tmp_filename, 'wb') as f:
                    downloaded = 0
                    total_size = int(response.headers.get('content-length', 0))
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Call progress callback if verbose
                            if self.verbose and total_size > 0:
                                download_callback(downloaded // 8192, 8192, total_size)
                
                shutil.move(tmp_filename, filepath)
                logger.debug(f'Download of "{photo.title}" at {photo.url} to {filepath} finished')
            except requests.exceptions.HTTPError as e:
                if tmp_fd is not None:
                    try:
                        os.close(tmp_fd)
                    except:
                        pass
                if os.path.exists(tmp_filename):
                    os.unlink(tmp_filename)
                if e.response.status_code == 404:
                    # For 404 errors, just set the flag and continue
                    download_404 = True
                else:
                    raise
            except Exception:
                if tmp_fd is not None:
                    try:
                        os.close(tmp_fd)
                    except:
                        pass
                if os.path.exists(tmp_filename):
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
                    logger.debug(f'Photo "{photo.title}" metadata{" and image" if image_exists else ""} copied to {copy_filepath}')

        # Give visual feedback in the console, but don't log
        if not self.verbose:
            print(photo.id)

        if download_404:
            raise requests.exceptions.HTTPError(f"404 Not Found: {photo.url}")

        return True

    def run(self, min_date, error_file=None):
        """Run a backup of all photos taken since min_date
        """

        dest_path = Path(self.destination)
        dest_path.mkdir(exist_ok=True)

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

        dest_path = Path(self.destination)
        dest_path.mkdir(exist_ok=True)

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

            print(f"No token found. You must visit this URL and get the verifier code: {authorize_url}")
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
        dirname = Path(self.destination) / self.normalize_filename(set_info.get('title'))
        with dirlock:
            if not dirname.exists():
                logger.debug(f"Creating directory {dirname}")
            dirname.mkdir(exist_ok=True)
        return str(dirname)

    def get_date_directory(self, parent, photo):
        date_taken = photo.date_taken.split(' ')[0]
        year, month, day = date_taken.split('-')
        dirname = Path(parent) / year / month / day
        with dirlock:
            dirname.mkdir(parents=True, exist_ok=True)
        return str(dirname)

    def write_metadata(self, photo_filepath, photo):
        filename = f"{photo_filepath}.{METADATA_EXTENSION}"
        with open(filename, 'w', encoding='utf-8') as f:
            print("[Information]", file=f)
            print(f"id = {photo.id}", file=f)
            print(f"title = {photo.title}", file=f)
            print(f"description = {photo.description or ''}", file=f)
            print(f"public = {'yes' if photo.is_public else 'no'}", file=f)
            print(f"friends = {'yes' if photo.is_friend else 'no'}", file=f)
            print(f"family = {'yes' if photo.is_family else 'no'}", file=f)
            print(f"taken = {photo.date_taken}", file=f)
            print(f"tags = {' '.join(photo.tags)}", file=f)
            print(f"url = {photo.url}", file=f)

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
        except requests.exceptions.HTTPError as e:
            if "404" in str(e):
                logger.warning(f"Photo {photo.title} ({photo.id}) not found at {photo.url}. Normally this means Flickr will not allow it to be downloaded. The metadata file ({photo.id}.{METADATA_EXTENSION}) has been written and contains a record of the URL")
            else:
                logger.exception(f"An unexpected HTTP error occurred downloading {photo.title} ({photo.id}) from {photo.url}")
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
    
    # Create mutually exclusive group for operation mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('-d', '--download', metavar='FILE',
                           help='Attempt to download the photos with the ids in the given file, one per line (usually saved by the --error-file option). Can be combined with --favorites to preserve favorites behavior.')
    mode_group.add_argument('--find-missing', metavar='FILE',
                           help='Search for metadata files without corresponding media files and write results to the specified CSV file')
    mode_group.add_argument('--obtain-web-session', metavar='FILE',
                           help='Launch a browser to obtain authenticated Flickr session data. Wait for manual login, then save session data to the specified file')
    mode_group.add_argument('-f', '--from', dest='from_date',
                            help='Start date (YYYY-MM-DD) for backup. If not specified, uses the last backup date stored in .stamp file in the destination directory')

    parser.add_argument('--favorites', action='store_true',
                       help='Download favorites instead of own photos. Requires --from when used alone and no previous backup timestamp exists. When combined with --download, implies --store-once and does not organise photos into folders based on sets.')

    parser.add_argument('-o', '--store-once', action='store_true', help='Only store photos once, even if they appear in multiple sets')
    parser.add_argument('-k', '--keep-existing', action='store_true', help='Keep existing photos (default is to replace in case they have changed)')
    parser.add_argument('-r', '--retry', type=int, default=1, help='Retry download of failed images N times (default is to retry once)')
    
    parser.add_argument('-e', '--error-file', help='Append ids of erroneous items to this file, to allow retry later')
    parser.add_argument('-l', '--log-file', help='Log warnings and errors to the given file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Log progress information')
    
    parser.add_argument('--token-cache', dest='token_cache', help="Path to a directory where the login token data will be stored. Must be secure. Defaults to ~/.flickr")
    parser.add_argument('--web-session', help='Path to a session file created by --obtain-web-session to enable authenticated downloads')
    parser.add_argument('--single-threaded', action='store_false', dest='threaded', help='Run in single-threaded mode (for debugging purposes)')
    parser.add_argument('--browser', choices=['chrome', 'firefox'], default='chrome', help='Browser to use for web session capture (default: chrome)')
    
    parser.add_argument('destination', nargs='?', help='Destination directory (not required for --obtain-web-session)')

    arguments = parser.parse_args()

    # Validate that destination is provided for operations that need it
    if not arguments.obtain_web_session and not arguments.destination:
        parser.error("destination is required except when using --obtain-web-session")

    destination = arguments.destination or ""
    
    # Validate that --from or .stamp file is required for modes other than --download
    if not arguments.download and not arguments.from_date and destination:
        stamp_path = Path(destination) / STAMP_FILENAME
        if not stamp_path.exists():
            parser.error("--from is required when no previous backup timestamp is found")
    
    success = False
    web_session_data = None

    # Load web session if provided
    if arguments.web_session:
        try:
            with open(arguments.web_session, 'r') as f:
                web_session_data = json.load(f)
            logger.info(f"Loaded web session from {arguments.web_session}")
        except Exception as e:
            logger.error(f"Could not load web session from {arguments.web_session}: {str(e)}")
            sys.exit(1)

    # Setup logging
    log_level = logging.DEBUG if arguments.verbose else logging.INFO
    logger.setLevel(log_level)

    # Configure handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    handlers.append(console_handler)
    
    # File handler if requested
    if arguments.log_file:
        file_handler = logging.FileHandler(arguments.log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s %(levelname)s %(message)s', "%Y-%m-%d %H:%M:%S")
        )
        handlers.append(file_handler)
    
    # Clear any existing handlers and add new ones
    logger.handlers.clear()
    for handler in handlers:
        logger.addHandler(handler)

    # Run
    if arguments.obtain_web_session:
        logger.info("Launching browser to obtain Flickr session data...")
        success = obtain_web_session(arguments.obtain_web_session, arguments.browser, arguments.verbose)

    elif arguments.find_missing:
        logger.info("Searching for missing media files...")
        success = find_missing_files(destination, arguments.find_missing, arguments.verbose)
    
    elif arguments.download:
        if not os.path.exists(arguments.download):
            logger.error("Download directory %s does not exist.", arguments.download)
            sys.exit(1)

        logger.info("Running backup of images found in %s", arguments.download)
        with open(arguments.download, 'r') as f:
            ids = [id.strip() for id in f.readlines() if id.strip() and not id.strip().startswith('#')]

        backup = FlickrBackup(destination,
                store_once=True if arguments.favorites else arguments.store_once,  # favorites mode always uses store_once
                keep_existing=arguments.keep_existing,
                favorites=arguments.favorites,  # Pass favorites flag to maintain consistent behavior
                retry=arguments.retry,
                verbose=arguments.verbose,
                token_cache=arguments.token_cache,
                web_session=web_session_data,
                threaded=arguments.threaded
            )
        success = backup.download(ids, arguments.error_file)
    else:

        # Figure out the start date
        from_date = arguments.from_date
        stamp_path = Path(destination) / STAMP_FILENAME
        if not from_date and stamp_path.exists():
            from_date = stamp_path.read_text().strip()
        if not from_date:
            logger.error(f"No start date specified and no previous time stamp found in {stamp_path}")
            sys.exit(1)

        if arguments.favorites:        
            logger.info(f"Running backup of favorites added since {from_date}")
        else:
            logger.info(f"Running backup of images updated since {from_date}")

        backup = FlickrBackup(destination,
                store_once=True if arguments.favorites else arguments.store_once,  # favorites mode always uses store_once
                keep_existing=arguments.keep_existing,
                favorites=arguments.favorites,
                retry=arguments.retry,
                verbose=arguments.verbose,
                token_cache=arguments.token_cache,
                web_session=web_session_data,
                threaded=arguments.threaded,
            )

        today = datetime.date.today().isoformat() # do this before running the backup in case it spans more than one day!
        success = backup.run(from_date, arguments.error_file)
        stamp_path.write_text(today)

    if not success:
        logger.info("Done, with errors.")
        sys.exit(2)

    logger.info("Done")

if __name__ == '__main__':
    main()