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

from getpass import getpass

CONFIG_FILENAME = "config.ini"
CONFIG_SECTION = "settings"

flickrAPI = None
configParser = None

threaded = False
dirlock = RLock()


#
# Management of settings
#


def clear_input_retriever(setting):
    return raw_input(setting.name + ":")


def passwd_input_retriever(setting):
    return getpass(setting.name + ':')


def config_retriever(setting):
    global configParser
    if configParser is None:
        configParser = ConfigParser.SafeConfigParser()
        configParser.read(CONFIG_FILENAME)
    return configParser.get(CONFIG_SECTION, setting.name)


class Setting(object):

    def __init__(self, name, default=None, input_retriever=clear_input_retriever, empty_value=None):
        self.name = name
        self._value = default
        self.input_retriever = input_retriever
        self.empty_value = empty_value

    @property
    def value(self):
        while self._value == self.empty_value:
            self._value = self.input_retriever(self)

        return self._value

#
# Settings
#

flickr_api_key = Setting('api-key', input_retriever=config_retriever)
flickr_api_secret = Setting('api-secret', input_retriever=config_retriever)

flickr_usernsid = None


def flickr_token_retriever(setting):
    global flickrAPI
    global flickr_usernsid

    if flickrAPI is None:
        flickrAPI = flickrapi.FlickrAPI(flickr_api_key.value, flickr_api_secret.value)

    (token, frob) = flickrAPI.get_token_part_one(perms='write')

    if not token:
        raw_input("Press ENTER after you authorized this program")

    flickrAPI.get_token_part_two((token, frob))

    flickr_usernsid = flickrAPI.auth_checkToken(auth_token=token).find('auth').find('user').get('nsid')

    return True

#
# Run
#


def run(destination, min_upload_date, max_upload_date=None, threadpoolsize=7):
    if not os.path.exists(destination):
        os.mkdir(destination)

    print 'Authenticating with Flickr..'
    flickr_token = Setting('Flickr Token', input_retriever=flickr_token_retriever)

    flickr_token.value  # force retrieval of authentication information...

    def get_photo_url(info):
        if info.get('media') == 'video':
            return "http://www.flickr.com/photos/%s/%s/play/orig/%s" % (flickr_usernsid, info.get('id'), info.get('originalsecret'))
        else:
            return "http://farm%s.staticflickr.com/%s/%s_%s_o.%s" % (info.get('farm'), info.get('server'), info.get('id'), info.get('originalsecret'), info.get('originalformat'))

    def get_photo_sets(info):
        return flickrAPI.photos_getAllContexts(photo_id=info.get('id')).findall('set')

    def get_set_directory(set_info):
        dirname = os.path.join(destination, set_info.get('title'))
        with dirlock:
            if not os.path.exists(dirname):
                os.mkdir(dirname)
        return dirname

    threadpool = ThreadPool(threadpoolsize)

    def download_photo(flickr_photo):
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
                    print "Photo: %s --- %i%% - %.1f/%.1fmb" % (flickr_photo.get('title'), res, downloaded_so_far, total_size_in_mb)

        photo_info = flickrAPI.photos_getInfo(photo_id=flickr_photo.get('id')).find('photo')
        photo_url = get_photo_url(photo_info)

        dirname = destination

        if photo_info.get('media') == 'video':
            # XXX: Doesn't seem to be a way to discover original file extension (?)
            filename = flickr_photo.get('id') + ".mov"
        else:
            filename = flickr_photo.get('id') + "." + photo_info.get('originalformat')

        # Create a photo set directory from the first set the photo is a member of
        photo_sets = get_photo_sets(photo_info)
        if len(photo_sets) > 0:
            dirname = get_set_directory(photo_sets[0])

        # TODO: Subdivide by year/month/day

        # Download
        print '* Processing photo "%s" at url "%s".' % (flickr_photo.get('title'), photo_url)

        filepath = os.path.join(dirname, filename)
        if os.path.exists(filepath):
            print "%s already exists" % filepath
        else:
            (filepath, headers) = urlretrieve(photo_url, filepath, download_callback)
            print 'Download of %s at %s to %s finished.' % (flickr_photo.get('title'), photo_url, filepath)

        # Copy to additional set directories
        for photo_set in photo_sets[1:]:
            copy_dirname = get_set_directory(photo_set)
            copy_filepath = os.path.join(copy_dirname, filename)
            if os.path.exists(copy_filepath):
                print "%s already exists" % copy_filepath
            else:
                shutil.copyfile(filepath, copy_filepath)
                print "Photo %s also copied to %s" % (flickr_photo.get('title'), copy_filepath,)

        # TODO: Write photo metadata (title, description, permissions, taken date, tags)

    # XXX: Use recentlyUpdated instead. Need to implement pagination. Can do away with getInfo() since we can ask for required parameters
    for photo in flickrAPI.walk(user_id="me", min_upload_date=min_upload_date, max_upload_date=max_upload_date, sort="date-posted-asc"):

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
    parser.add_argument('-c', '--config', help='Configuration file')
    parser.add_argument('-f', '--from', dest='from_date', help='From date/time')
    parser.add_argument('-t', '--to', dest='to_date', help='To date/time')
    parser.add_argument('destination', help='Destination directory')

    return parser.parse_args()

if __name__ == '__main__':
    arguments = parse_args()

    if arguments.config:
        CONFIG_FILENAME = arguments.config

    run(arguments.destination, arguments.from_date, arguments.to_date)
