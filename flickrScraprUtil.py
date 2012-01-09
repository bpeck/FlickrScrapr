import flickrapi
import datetime
import os
from datetime import datetime

baseDir = 'YOUR BASE PATH'
dbPath = baseDir + 'PATH TO SQLITE DB'

# from your flickr api account
api_key = 'YOUR API KEY'
api_secret = 'YOUR API SECRET'

def unixTimeToMySQLTime(unixTimeStamp):
    ''' unix timestamps are number of ms since 1970 or something. MySQL uses the
        format YYYY-MM-DD SS-MS-NS'''
    dt = datetime.fromtimestamp(float(unixTimeStamp))
    mysqlTime = str(dt.year)
    if len(str(dt.month)) == 1:
        mysqlTime = mysqlTime + '-0' + str(dt.month)
    else:
        mysqlTime = mysqlTime + '-' + str(dt.month)
    if len(str(dt.day)) == 1:
        mysqlTime = mysqlTime + '-0' + str(dt.day)
    else:
        mysqlTime = mysqlTime + '-' + str(dt.day)
    mysqlTime = mysqlTime + ' 00:00:00'
    return mysqlTime

def checkStr(str):
    ''' if the string can be encoded to utf-8, return the tuple True, and the
        contents of the string. If not, return tuple False and empty string'''
    if str == None:
        return [False, '']
    try:
        str = str.decode('utf-8', 'ignore')
        return [True, str]
    except UnicodeEncodeError:
        return [False, '']

def makeQuotesSafeForSQL(str, quoteChar='"\''):
    safeStr = ''
    for c in str:
        if c in quoteChar:
            safeStr += '\\'
        safeStr += c
    return safeStr

def getPhotoURL(photo, size='s') :
    """ Creates a URL for a flickr photo using the given info gathered from the api
        photo       - a photo element from the flickr api
        size        - the size of the photo (optional)
                        s small square 75x75
                        t thumbnail, 100 on longest side
                        m small, 240 on longest side
                        - medium, 500 on longest side
                        b large, 1024 on longest side (only exists for very large original images)
                        o original image, either a jpg, gif or png, depending on source format
    """
    
    return "http://farm" + photo.get('farm') + ".static.flickr.com/" + photo.get('server') + \
            "/" + photo.get('id') + "_"+photo.get('secret')+"_"+size+".jpg"

def findAttrib(photo, info, key):
    ''' Searches a photo and corresponding info xml nodes and their children for
        a specific key
        photo - xml node of photo
        info - xml node of photo's info grabbed via flickr.photos_getInfo
        key - attribute string to retreive value for'''
    if key == None or key == '':
        return None
    if key in photo.attrib:
        return photo.attrib[key]
    if key in info.attrib:
        return info.attrib[key]
    for c in info:
        if key in c.attrib:
            return c.attrib[key]
    return None

def getPhotoInfo(photo, info,
                 attribsToRetreive=['license','username','realname','taken','posted'],
                 verbose=False):
    '''Collects pertinent information of the photo, checking for non-utf-8
        characters'''
    
    photoInfo = {}
    
    for attr in attribsToRetreive:
        str = checkStr(findAttrib(photo, info, attr))
        if str[0]:
            photoInfo[attr] = str[1]
        else:
            return None
    
    return photoInfo

def getPhotoTags(info, maxlen=300, dictionary='/usr/share/dict/words'):
    ''' returns a string of comma separated strings of a photo's valid utf-8
        tags that appear in the linux dictionary
        info - an xml node retrieved from a photo node via flickr.photos_getInfo
        maxlen - maximum length of string to return
        dictionary - location of dictionary to grep tags against'''
    tags = info.find('tags')
    tagstring = ''
    for tag in tags:
        # make sure the tag contains text, and that it won't push us over the limit
        if tag.text != None and len(tagstring) + len(tag.text) <= maxlen:
            
            # try to decode the string into utf-8. If not, then skip the tag
            decoded = ''
            try:
                decoded = tag.text.decode('utf-8','ignore')
            except UnicodeEncodeError:
                pass
            
            # remove all common punctuation and symbols
            decoded = decoded.lower().replace('\"\'!@#$%^&*()-_+=[{]}|\\/?*+,<.>;:~`', '')
            # if the tag is multiple words, we need to check each individual word
            for stub in sorted(decoded.split(' ')):
                # grep against the dictionary file
                if len(stub) > 0 and os.system('grep -q ^' + stub + '$ /usr/share/dict/words') == 0:
                    tagstring += stub + ','                 
                    
    # remove leading and trailing commas
    tags = tagstring.strip(',')
    
    return tags

def genRandomLocalURL() :
	"""Generates a random local url to place a downloaded image inside of"""
	random.seed()
	a = str(random.randint(1,16))
	b = str(random.randint(1,4))
	c = str(random.randint(1,2))
	return 'img/' + str(a) + '/' + str(a) + str(b) + '/' + str(a) + str(b) + str(c)

def download(url, destination_url) :
    """Copy the contents of a file from a given URL to a local file."""
    webFile = urllib.urlopen(url)
    localFile = open(destination_url, "w")
    localFile.write(webFile.read())
    webFile.close()
    localFile.close()

def analyzePhoto(local_url):
    """ Calculate the average color and std deviation of a photo. Deletes
    the photo if the file is corrupt. Returns a tuple of (averageColor, stdDev)
    """
    # open the image
    im = None
    try:
        im = Image.open(baseDir + '/' + local_url)
    except IOError:
        if os.path.isfile(local_url):
            os.unlink(local_url)
        return None
    
    # first make sure the image is valid. If it isn't recognized as a
    # JPEG, then something is wrong
    if not im or im.format != 'JPEG':
        if os.path.isfile(local_url):
            os.unlink(local_url)
        return None

    # generate a histogram so we can calcuate the average color and std
    # deviations
    h = im.histogram()
    
    # calculate an rgb tuple representing the average color
    avgC = [0.0,0.0,0.0]
    
    numPixels = float(im.size[0] * im.size[1])
    
    for i,j in zip(h[0:255],range(0,256)):
        avgC[0] += float(i*j) / numPixels
    for i,j in zip(h[256:511],range(0,256)):
        avgC[1] += float(i*j) / numPixels
    for i,j in zip(h[512:767],range(0,256)):
        avgC[2] += float(i*j) / numPixels
    # round and cast to int
    avgC[0] = int(round(avgC[0]))
    avgC[1] = int(round(avgC[1]))
    avgC[2] = int(round(avgC[2]))
    # encode the color into an integer for storing in the db
    avg = int(avgC[0] * math.pow(256.0,2) + avgC[1] * 256.0 + avgC[2])
        
    # calculate the standard deviation in the image for each channel
    sd = [0.0,0.0,0.0]
    data = im.getdata()
    for pixel in data:
        sd[0] += (1.0/numPixels) * math.pow((float(pixel[0]) - avgC[0]), 2.0)
        sd[1] += (1.0/numPixels) * math.pow((float(pixel[1]) - avgC[1]), 2.0)
        sd[2] += (1.0/numPixels) * math.pow((float(pixel[2]) - avgC[2]), 2.0)
    sd[0] = math.sqrt(sd[0])
    sd[1] = math.sqrt(sd[1])
    sd[2] = math.sqrt(sd[2])
    # take max as the std dev over all 3 channels
    stdDev = max(sd)
    # round and cast to int
    stdDev = int(round(stdDev))
    
    return (avg, stdDev)
