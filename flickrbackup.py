#! /usr/bin/python
#
# requires flickrapi, threadpool

from urllib import urlretrieve

from threadpool import WorkRequest
from threadpool import ThreadPool
from threading import RLock

import os
import os.path
import shutil

import ConfigParser
import argparse
import flickrapi

flickr_api_key = "39b564af2057a7d014875e4939a292db"
flickr_api_secret = "32cb192e3b9c43e6"

METADATA_EXTENSION = 'txt'

threaded = True
dirlock = RLock()

flickr_api_key = "39b564af2057a7d014875e4939a292db"
flickr_api_secret = "32cb192e3b9c43e6"


def retrieve_flickr_token(username):
    flickr_api = flickrapi.FlickrAPI(flickr_api_key, secret=flickr_api_secret, username=username)

    (token, frob) = flickr_api.get_token_part_one(perms='write')

    if not token:
        raw_input("Press ENTER after you authorized this program")

    flickr_api.get_token_part_two((token, frob))

    flickr_usernsid = flickr_api.auth_checkToken(auth_token=token).find('auth').find('user').get('nsid')

    return (flickr_api, flickr_usernsid)

#
# Run
#


def run(destination, min_date, username=None, threadpoolsize=7):
    if not os.path.exists(destination):
        os.mkdir(destination)

    print 'Authenticating with Flickr..'
    flickr_api, flickr_usernsid = retrieve_flickr_token(username)

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
        parser = ConfigParser.SafeConfigParser()
        parser.add_section("Photo")
        parser.set("Photo", "id", photo.get('id'))
        parser.set("Photo", "title", photo.get('title'))
        parser.set("Photo", "description", photo.find('description').text or "")
        parser.set("Photo", "public", photo.get('ispublic'))
        parser.set("Photo", "friends", photo.get('isfriend'))
        parser.set("Photo", "family", photo.get('isfamily'))
        parser.set("Photo", "taken", photo.get('datetaken'))
        parser.set("Photo", "tags", photo.get('tags'))

        with open(filename, 'w') as f:
            parser.write(f)

    threadpool = ThreadPool(threadpoolsize)

    def download_photo(photo):
        def download_callback(count, blocksize, totalsize):

            download_stat_print = set((0.0, .25, .5, 1.0))
            downloaded = float(count * blocksize)
            res = int((downloaded / totalsize) * 100.0)

            for st in download_stat_print:
                dl = totalsize * st
                diff = downloaded - dl
                if diff >= -(blocksize / 2) and diff <= (blocksize / 2):
                    downloaded_so_far = float(count * blocksize) / 1024.0 / 1024.0
                    total_size_in_mb = float(totalsize) / 1024.0 / 1024.0
                    print "Photo: %s --- %i%% - %.1f/%.1fmb" % (photo.get('title'), res, downloaded_so_far, total_size_in_mb)

        photo_url = get_photo_url(photo)

        dirname = destination

        if photo.get('media') == 'video':
            # XXX: Doesn't seem to be a way to discover original file extension (?)
            filename = photo.get('id') + ".mov"
        else:
            filename = photo.get('id') + "." + photo.get('originalformat')

        # Create a photo set directory from the first set the photo is a member of
        photo_sets = get_photo_sets(photo)
        if len(photo_sets) > 0:
            dirname = get_set_directory(photo_sets[0])

        dirname = get_date_directory(dirname, photo)

        # Download
        print '* Processing photo "%s" at url "%s".' % (photo.get('title'), photo_url)

        filepath = os.path.join(dirname, filename)
        (filepath, headers) = urlretrieve(photo_url, filepath, download_callback)
        write_metadata(filepath, photo)
        print 'Download of %s at %s to %s finished.' % (photo.get('title'), photo_url, filepath)

        # Copy to additional set directories
        for photo_set in photo_sets[1:]:
            copy_dirname = get_set_directory(photo_set)
            copy_dirname = get_date_directory(copy_dirname, photo)
            copy_filepath = os.path.join(copy_dirname, filename)

            shutil.copyfile(filepath, copy_filepath)
            shutil.copyfile(filepath + "." + METADATA_EXTENSION, copy_filepath + "." + METADATA_EXTENSION)
            print "Photo %s also copied to %s" % (photo.get('title'), copy_filepath,)

    page = 1
    has_more_pages = True

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

        for photo in recently_updated.findall('photo'):
            if threaded:
                req = WorkRequest(download_photo, [photo], {})
                threadpool.putRequest(req)
            else:
                download_photo(photo)

    threadpool.wait()

#
# CLI
#


def parse_args():
    parser = argparse.ArgumentParser(description='Incremental Flickr backup')
    parser.add_argument('-u', '--username', help='Start date')
    parser.add_argument('from_date', help='Start date')
    parser.add_argument('destination', help='Destination directory')

    return parser.parse_args()

if __name__ == '__main__':
    arguments = parse_args()
    run(arguments.destination, arguments.from_date, arguments.username)
