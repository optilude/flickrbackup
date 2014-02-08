import flickrapi
from unidecode import unidecode
import json
import csv
import time
import datetime
import sys

api_key = "bb5df1eaa8b3fed046b9d3185b67f375"
api_secret = "82f4f3eb073d7bb3"

keys = ['photo_id', 'tags', 'geolocation', 'date_taken', 'date_posted', 'views', 'locale', 'county', 'region', 'url']

class Photo(object):

    def __init__(self, id, original_secret=None, original_format=None, media='photo', farm=None, server=None, title=None, description=None,
                    date_taken=None, date_posted=None, views=None, geolocation=None, locale=None, county=None, region=None, is_public=None,
                    is_friend=None, is_family=None, tags=None, tags_machine=None, url2=None, flickr_usernsid=None):
        self.id = id
        self.original_secret = original_secret
        self.original_format = original_format
        self.media = media
        self.farm = farm
        self.server = server
        self.title = title
        self.description = description
        self.date_taken = date_taken
        self.date_posted = date_posted
        self.views = views
        self.geolocation = geolocation
        self.locale = locale
        self.county = county
        self.region = region
        self.is_public = is_public
        self.is_friend = is_friend
        self.is_family = is_family
        self.tags = tags
        self.tags_machine = tags_machine
        self.url2 = url2
        self.flickr_usernsid = flickr_usernsid

    @property
    def url(self):
        if self.original_secret is None or self.original_format is None:
            return self.url2
        else:
            return "http://farm%s.staticflickr.com/%s/%s_%s_o.%s" % (self.farm, self.server, self.id, self.original_secret, self.original_format)

    @classmethod
    def fromSearchResult(cls, info, flickr_usernsid=None):

        geolocation, locale, county, region = [None] * 4
        if 'location' in info:
            geolocation = [info.get('location').get('latitude'), info.get('location').get('longitude')]
            if 'locality' in info.get('location'):
                locale = [info.get('location').get('locality').get('_content'), info.get('location').get('locality').get('place_id')]
            if 'county' in info.get('location'):
                county = [info.get('location').get('county').get('_content'), info.get('location').get('county').get('place_id')]
            if 'region' in info.get('location'):
                region = [info.get('location').get('region').get('_content'), info.get('location').get('region').get('place_id')]

        tags = []
        tags_machine = []
        for t in info.get('tags').get('tag'):
            if t.get('machine_tag') == 1:
                tags_machine.append(t.get('raw'))
            else:
                tags.append(t.get('raw'))

        return Photo(
                id=info.get('id'),
                original_secret=info.get('originalsecret'),
                original_format=info.get('originalformat'),
                media=info.get('media'),
                farm=info.get('farm'),
                server=info.get('server'),
                title=info.get('title'),
                description=info.get('description'),
                date_taken=info.get('dates').get('taken'),
                date_posted=info.get('dates').get('posted'),
                views=info.get('views'),
                geolocation=geolocation,
                locale=locale,
                county=county,
                region=region,
                is_public=info.get('visibility').get('ispublic') == '1',
                is_friend=info.get('visibility').get('isfriend') == '1',
                is_family=info.get('visibility').get('isfamily') == '1',
                tags=tags,
                tags_machine=tags_machine,
                url2 = info.get('urls').get('url')[0].get('_content'),
                flickr_usernsid=flickr_usernsid,
            )

class FlickrCrawl(object):

    def __init__(self):
        # Initialize connection to Flickr
        self.flickr = self.auth_flickr()

    def retrieve_flickr_token(self):
        flickr_api = flickrapi.FlickrAPI(api_key, secret=api_secret, store_token=False)

        (token, frob) = flickr_api.get_token_part_one(perms='write')
        if not token:
            raw_input("Press ENTER after you authorized this program")
        flickr_api.get_token_part_two((token, frob))
        print token

        flickr_usernsid = flickr_api.auth_checkToken(auth_token=token).find('auth').find('user').get('nsid')

        return (flickr_api, flickr_usernsid)

    def auth_flickr(self):
        flickr = flickrapi.FlickrAPI(api_key, api_secret)
        return flickr

    def run(self, min_date, max_date):

        page = 1
        has_more_pages = True

        while has_more_pages:
            search_results = self.flickr.photos_search(min_taken_date=min_date, max_taken_date=max_date, 
                has_geo=1, media='photos', bbox='-124.7625, 24.5210, -66.9326, 49.3845', per_page='250', page=page).find('photos')

            print "Number of pages: ", search_results.get('pages')
            print "Current page: ", page
            if page >= int(search_results.get('pages')):
                has_more_pages = False
            else:
                page += 1

            photo_set = []

            # print len(search_results1)
            # print len(search_results2)
            # print len(search_results3)
            # print len(search_results4)
            # print len(search_results5)

            # if len(search_results5) > 249:
            #     print "Choose a smaller date range."
            #     sys.exit(0)
            for item in search_results.findall('photo'):
                photo_id = item.get('id')
                print photo_id
                if photo_id is not None:
                    photo = self.flickr.photos_getInfo(photo_id=photo_id, format='json')
                    if 'jsonFlickrApi(' in photo:
                        photo = json.loads(photo[14:-1])
                    if 'photo' in photo:
                        p = Photo.fromSearchResult(photo['photo'])
                        if p.tags == []:
                            continue
                photo = {'photo_id' : p.id, 'tags' : p.tags, 'geolocation' : p.geolocation, 'date_taken' : p.date_taken, 'date_posted' : p.date_posted,
                                'views' : p.views, 'locale' : p.locale, 'county' : p.county, 'region' : p.region, 'url' : p.url}
                photo_set.append(photo)
                print photo
                self.writeOut(photo)
            # for item in search_results2.findall('photo'):
            #     photo_id = item.get('id')
            #     print photo_id
            #     if photo_id is not None:
            #         photo = self.flickr.photos_getInfo(photo_id=photo_id, format='json')
            #         if 'jsonFlickrApi(' in photo:
            #             photo = json.loads(photo[14:-1])
            #         p = Photo.fromSearchResult(photo['photo'])
            #         if p.tags == []:
            #             continue
            #     photo = {'photo_id' : p.id, 'tags' : p.tags, 'geolocation' : p.geolocation, 'date_taken' : p.date_taken, 'date_posted' : p.date_posted,
            #                     'views' : p.views, 'locale' : p.locale, 'county' : p.county, 'region' : p.region, 'url' : p.url}
            #     photo_set.append(photo)
            #     print photo
            #     self.writeOut(photo)
            # for item in search_results3.findall('photo'):
            #     photo_id = item.get('id')
            #     print photo_id
            #     if photo_id is not None:
            #         photo = self.flickr.photos_getInfo(photo_id=photo_id, format='json')
            #         if 'jsonFlickrApi(' in photo:
            #             photo = json.loads(photo[14:-1])
            #         p = Photo.fromSearchResult(photo['photo'])
            #         if p.tags == []:
            #             continue
            #     photo = {'photo_id' : p.id, 'tags' : p.tags, 'geolocation' : p.geolocation, 'date_taken' : p.date_taken, 'date_posted' : p.date_posted,
            #                     'views' : p.views, 'locale' : p.locale, 'county' : p.county, 'region' : p.region, 'url' : p.url}
            #     photo_set.append(photo)
            #     print photo
            #     self.writeOut(photo)
            # for item in search_results4.findall('photo'):
            #     photo_id = item.get('id')
            #     print photo_id
            #     if photo_id is not None:
            #         photo = self.flickr.photos_getInfo(photo_id=photo_id, format='json')
            #         if 'jsonFlickrApi(' in photo:
            #             photo = json.loads(photo[14:-1])
            #         p = Photo.fromSearchResult(photo['photo'])
            #         if p.tags == []:
            #             continue
            #     photo = {'photo_id' : p.id, 'tags' : p.tags, 'geolocation' : p.geolocation, 'date_taken' : p.date_taken, 'date_posted' : p.date_posted,
            #                     'views' : p.views, 'locale' : p.locale, 'county' : p.county, 'region' : p.region, 'url' : p.url}
            #     photo_set.append(photo)
            #     print photo
            #     self.writeOut(photo)
            # for item in search_results5.findall('photo'):
            #     photo_id = item.get('id')
            #     print photo_id
            #     if photo_id is not None:
            #         photo = self.flickr.photos_getInfo(photo_id=photo_id, format='json')
            #         if 'jsonFlickrApi(' in photo:
            #             photo = json.loads(photo[14:-1])
            #         p = Photo.fromSearchResult(photo['photo'])
            #         if p.tags == []:
            #             continue
            #     photo = {'photo_id' : p.id, 'tags' : p.tags, 'geolocation' : p.geolocation, 'date_taken' : p.date_taken, 'date_posted' : p.date_posted,
            #                     'views' : p.views, 'locale' : p.locale, 'county' : p.county, 'region' : p.region, 'url' : p.url}
            #     photo_set.append(photo)
            #     print photo
            #     self.writeOut(photo)

    def writeOut(self, photo):
        with open('flickrdump.csv', 'ab') as f:
            dict_writer = csv.DictWriter(f, delimiter=',', fieldnames=keys)
            dict_writer.writerow(photo)

def main():

    ts = time.time()
    st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    print st

    min_taken_date='2013-01-02'
    max_taken_date='2013-02-01'

    crawl = FlickrCrawl()

    photo_set = []
    # only do this once because it creates a new flie and writes a header row
    with open('flickrdump.csv', 'ab') as f:
        dict_writer = csv.DictWriter(f, keys, dialect='excel')
        dict_writer.writer.writerow(keys)

    crawl.run(min_taken_date, max_taken_date)

    ts = time.time()
    st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    print st

if __name__ == '__main__':
    main()
