#!/usr/bin/python

""" This script crawls flickr for interesting photos,
downloading them, and analyzing them, and saving the results to a sqlite database 
"""

import os
import math
# we update a database to keep track of all this shit
import sqlite3
# btw we're scraping flickr
import flickrapi
# sqlite3 wrapper uses datetime for timestamps
import datetime
from datetime import datetime
import time
# we analyze the scraped images using python image library
from PIL import Image
# download the images off flickr's server using urllib
import urllib

# some utility functions
from flickrScraprUtil import unixTimeToMySQLTime, checkStr, makeQuotesSafeForSQL, getPhotoURL, findAttrib, getPhotoInfo, getPhotoTags, analyzePhoto, genRandomLocalURL, download
# some important strings you need to fill in
from flickrScraprUtil import baseDir, dbPath, api_key, api_secret

# we crawl by searching for interesting images on flickr from a 
# a list of search terms
words = [line.strip() for line in open('searchTerms.txt', 'r').readlines()]

def isTimeToQuit():
    """ to provide for graceful quitting. Open up a new terminal and running
    touch __scrapr_quit__ 
    will cause this script to stop running in a safe manner that leaves the
    db in a good state. """
    if os.path.isfile('__scrapr_quit__'):
        return True
    return False

def getPhotoList(sql):
    """ returns every single photo in some sql database """
    q = 'SELECT id, remote_url FROM palette'
    result = sql.execute(q)
    picList = []
    for r in result.fetchall():
        picList.append(r[1])
    return picList

def getDBHistogram(sql):
    """ Returns a color histogram of some sql database """
    q = 'SELECT ALL id, color_mean FROM palette ORDER BY color_mean ASC'
    result = sql.execute(q)
    histo = {}
    for r in result.fetchall():
        if r[1] not in histo.keys():
            histo[r[1]] = 1
        else:
            histo[r[1]] += 1
    return histo

def downloadPhoto(remote_url):
    # Generate a directory to store image in.
    # make the directory if needed
    rel_local = genRandomLocalURL()
    abs_local = os.path.join(baseDir, rel_local)
    if not(os.path.isdir(abs_local)):
        os.makedirs(abs_local)
    
    # download the image
    file_url = os.path.join(abs_local, remote_url.split('/')[-1])
    download(remote_url, file_url)
    
    # update the database with this image's local url
    # store relative urls just to keep things portable
    rel_file_url = os.path.join(rel_local, remote_url.split('/')[-1])
    
    return rel_file_url

def main() :
    # connect to database
    db = sqlite3.connect(dbPath)
    cursor = db.cursor()
    print 'Connected to sqlite'
    
    # connect to flickr api account
    flickr = flickrapi.FlickrAPI(api_key, api_secret)
    (token, frob) = flickr.get_token_part_one(perms='read')
    if not token:
        raw_input("Press ENTER after you authorized this program")
    flickr.get_token_part_two((token, frob))
    print "Authenticated with Flickr!"
    
    maxTagLen = 200
    
    # these will get us around 700 photos per word, with a total around 12800
    perPage = 200
    numPages = 3
    
    # 4 = CC attribution, 7 = "no known copyright", aka a commons image
    licenses = '4,7'
    
    print 'Crawling ' + str(perPage) + ' photos per page, for a maximum of ' + \
                        str(numPages) + ' pages'
    
    sortType = 'interestingness-desc'
    photosRetreived = 0
    
    photoList = getPhotoList(cursor)
    DBHistogram = getDBHistogram(cursor)
    done = False
    
    for word in words:
        
        photosRetrievedForWord = 0
        
        # skip all this if we're done
        if done:
            break
        
        page = 1
        # send the search out to flickr
        photoSet = flickr.photos_search(license=licenses, tags=word, \
                        sort=sortType, per_page=str(perPage), page=str(page))
        # while we have a valid photoSet and there are pages in the set to crawl
        while photoSet.attrib['stat'] and len(photoSet) > 0 and page <= numPages:
            # check if Ben's girlfriend wants him to shut off the computer
            # and go to bed
            if isTimeToQuit():
                print 'Quitting at page ' + str(page) + ' of word ' + word
                print str(photosRetreived) + ' photos retrieved.'
                done = True 
                break
            
            print '\tCrawling page ' + str(page) + ' of search: ' + word
            for photo in photoSet[0]:
                # get the detailed info on the photo (tags, author, url, license)
                info = flickr.photos_getInfo(photo_id=photo.attrib['id'], \
                                             secret=photo.attrib['secret'])[0]
                
                remoteURL = getPhotoURL(photo)
                
                # check for duplicates
                if remoteURL in photoList:
                    continue
                else:
                    photoList.append(remoteURL)
                
                tags = getPhotoTags(info)
                
                # Try to encode the info from flickr into ascii
                # skip photos with raunchy encoding in their information strings
                myInfo = getPhotoInfo(photo, info)
                if myInfo == None:
                    continue
                
                localURL = downloadPhoto(remoteURL)
                
                analysis = analyzePhoto(localURL)
                # analyzePhoto returns None if the photo was corrupt in some way
                if not analysis:
                    if os.path.isfile(localURL):
                        os.unlink(localURL)
                    continue
                
                # extract the relevant values from the tuple
                avgC, stdDev = analysis
                
                # skip photos who's avg color we have a ton of, ie if the 
                # histogram says we already have > 10 photos with this avg color
                if avgC in DBHistogram.keys() and DBHistogram[avgC] > 10:
                    if os.path.isfile(localURL):
                        os.unlink(localURL)
                        continue
                else:
                    if avgC in DBHistogram.keys():
                        DBHistogram[avgC] += 1
                    else:
                        DBHistogram[avgC] = 1
                
                # make the info we grabbed from flickr safe for sql by adding a
                # backslash in front of any " characters
                safeInfo = {}
                for k in myInfo.keys():
                    if type(myInfo[k]) == str:
                        safeInfo[k] = makeQuotesSafeForSQL(myInfo[k])
                    else:
                        safeInfo[k] = myInfo[k]
                
                # big ass query to add the photo to our db
                cmd = 'INSERT INTO palette (tags, license, user, user_fullname, date_taken, date_uploaded, width, height, remote_url, query_pool, color_mean, color_stddev, file_url)'
                cmd += ' VALUES("' + tags + '",' + safeInfo['license'] + \
                    ',"' + safeInfo['username'] + '","' + safeInfo['realname'] + '","' \
                    + safeInfo['taken'] + '", "' + \
                    unixTimeToMySQLTime(safeInfo['posted']) + '" , 75, 75, "' \
                    + remoteURL + '", "' + word + '", ' + str(avgC) + ', ' + str(stdDev) + ', "' + localURL.replace(baseDir+'/','') +'");'
                
                # run the sql query in a try block, because it will fail occasionally
                try:
                    #print cmd
                    cursor.execute(cmd)
                    photosRetreived += 1
                    photosRetrievedForWord +=1
                except:
                    try:
                        # 99% of the time it's a jackass with trademark symbol
                        # in their photo tags or account name
                        print "Error : " + cmd  in their username
                        if os.path.isfile(localURL):
                            os.unlink(localURL)
                            continue
                    except:
                        print 'Well shit.'
                
            # grab next page of the photoSet, commit changes to the db
            page = page + 1
            db.commit()
            
            # sleep for a minute so flickr doesn't ban me
            time.sleep(60)
        
        print "Got " + str(photosRetrievedForWord) + " from word " + word
    
    # close the sqlite db
    cursor.close()
    
if __name__ == '__main__': 
    main()
