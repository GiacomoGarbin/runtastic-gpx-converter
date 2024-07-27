import sys
import zipfile
import os.path
import json
import xml.etree.ElementTree as ET
import datetime

usage_message = 'Usage: python runtastic-gpx-converter.py <path_to_runtastic_export_zip>'
started_message = 'conversion started, please wait ...'
success_message = 'conversion completed'

class Node:
    def __init__(self, data, left=None, right=None):
        self.data = data
        self.left = left
        self.right = right

class BST:
    def __init__(self, node=None, func=None):
        self.root = node
        self.func = func

    def insert(self, data):
        if self.root == None:
            self.root = Node(data)
        else:
            node = self.root
            parent = None
            while node != None:
                parent = node
                if self.func != None:
                    node = node.left if self.func(data, node.data) else node.right
                else:
                    node = node.left if data < node.data else node.right
            if self.func != None:
                if self.func(data, parent.data):
                    parent.left = Node(data)
                else:
                    parent.right = Node(data)
            else:
                if data < parent.data:
                    parent.left = Node(data)
                else:
                    parent.right = Node(data)

def traversal(node):
    if node != None:
        yield from traversal(node.left)
        yield node.data
        yield from traversal(node.right)

def transformdate(timestamp_utc_millis):
    # change date string into ISO format
    timestamp = datetime.datetime.fromtimestamp(timestamp_utc_millis / 1000, tz = datetime.timezone.utc)
    return timestamp.isoformat(timespec='milliseconds')

class activity:
    def __init__(self):
        self.id = None
        self.datetime = None
        self.distance = None # metres
        self.duration = None # milliseconds
        self.gpx = None

def getactivity(zip, basename):
    # session data
    sesdata = json.load(zip.open('Sport-sessions/' + basename, 'r'))
    # gps data
    gpsdata = json.load(zip.open('Sport-sessions/GPS-data/' + basename, 'r'))
    # elevation data
    eledata = json.load(zip.open('Sport-sessions/Elevation-data/' + basename, 'r'))

    act = activity()
    act.id = sesdata['id']
    # act.datetime = gpsdata[0]['timestamp']

    # change timestamp string into ISO format
    timestamp = transformdate(gpsdata[0]['timestamp'])
    # build datetime object from ISO format
    act.datetime = datetime.datetime.fromisoformat(timestamp)

    distance = next(a['attributes']['distance'] for a in sesdata['features'] if 'track_metrics' == a['type'])
    act.distance = '%.2f' % (distance * 0.001) # from metres to kilometres

    SS = (sesdata['duration'] * 0.001) # from milliseconds to seconds
    MM, SS = divmod(SS, 60)
    HH, MM = divmod(MM, 60)
    act.duration = '%02d:%02d:%02d' % (HH, MM, SS)  # from seconds to HH:MM:SS

    attr = {
        'creator': 'Garmin Connect',
        'version': '1.1',
        'xsi:schemaLocation': 'http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/11.xsd',
        'xmlns:ns3': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1',
        'xmlns': 'http://www.topografix.com/GPX/1/1',
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xmlns:ns2': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3'
    }

    gpx = ET.Element('gpx', attr)

    meta = ET.SubElement(gpx, 'metadata')
    link = ET.SubElement(meta, 'link', {'href': 'connect.garmin.com'})
    text = ET.Element('text')
    text.text = 'Garmin Connect'
    link.append(text)
    time = ET.Element('time')
    # change timezone from local to UTC and use ISO format
    # time.text = act.datetime.astimezone(datetime.timezone.utc).isoformat(timespec='milliseconds')
    time.text = transformdate(gpsdata[0]['timestamp'])
    meta.append(time)

    trk = ET.SubElement(gpx, 'trk')

    trkname = ET.Element('name')
    trkname.text = act.id
    trk.append(trkname)
    trktype = ET.Element('type')
    trktype.text = 'running' # sesdata['sport_type_id']
    trk.append(trktype)

    trkseg = ET.SubElement(trk, 'trkseg')

    samelen = (len(gpsdata) == len(eledata))

    for i in range(len(gpsdata)):
        lat = str(gpsdata[i]['latitude'])
        lon = str(gpsdata[i]['longitude'])
        trkpt = ET.SubElement(trkseg, 'trkpt', {'lat' : lat, 'lon': lon})

        ele = ET.Element('ele')
        if samelen and (gpsdata[i]['timestamp'] == eledata[i]['timestamp']):
            ele.text = str(eledata[i]['elevation'])
        else:
            ele.text = str(gpsdata[i]['altitude'])
        trkpt.append(ele)

        time = ET.Element('time')
        time.text = transformdate(gpsdata[i]['timestamp'])
        trkpt.append(time)

        exts = ET.SubElement(trkpt, 'extensions')
        ET.SubElement(exts, 'ns3:TrackPointExtension')

    act.gpx = ET.tostring(gpx, encoding="UTF-8")

    return act

def main():

    if len(sys.argv) < 2:
        print(usage_message)
        sys.exit()

    runtastic_export_zip_path = sys.argv[1]

    gpxzipname = os.path.join(runtastic_export_zip_path.rstrip('.zip') + '_GPX.zip')

    with zipfile.ZipFile(runtastic_export_zip_path, 'r') as userzip:
        with zipfile.ZipFile(gpxzipname, 'w', zipfile.ZIP_DEFLATED) as gpxzip:

            print(started_message)

            activities = BST(func=(lambda a, b : a.datetime < b.datetime))

            for filename in userzip.namelist():
                try:
                    # Sport-sessions/GPS-data contains 2 files per activity. One .json and one .gpx.
                    # We want the .json file only - it should be available in all folders:
                    # Sport-sessions
                    # Sport-sessions/GPS-data
                    # Sport-sessions/Elevation-data
                    if os.path.dirname(filename) == 'Sport-sessions/GPS-data' \
                            and filename.endswith('.json'): # Ignore .gpx files in the same folder
                        act = getactivity(userzip, os.path.basename(filename))
                        gpxzip.writestr(act.id + '.gpx', act.gpx)
                        activities.insert(act)
                except KeyError as e:
                    print(f"KeyError: {e} - Skipping file {filename}")

            html = ET.Element('html')
            body = ET.SubElement(html, 'body')

            table = ET.SubElement(body, 'table', {'style': 'border-collapse: collapse;'})

            header = ['session id', 'datetime', 'distance (km)', 'duration']
            tr = ET.SubElement(table, 'tr')

            for item in header:
                th = ET.SubElement(tr, 'th', {'style': 'border: 1px solid black; padding: 2px 10px;'})
                th.text = item

            for act in traversal(activities.root):
                row = [act.id, act.datetime.strftime('%d-%m-%Y %H:%M'), act.distance, act.duration]
                tr = ET.SubElement(table, 'tr')

                for value in row:
                    td = ET.SubElement(tr, 'td', {'style': 'border: 1px solid black; padding: 2px 10px;'})
                    td.text = value

            gpxzip.writestr('activities.html', ET.tostring(html, encoding="UTF-8", method="html"))

            print(success_message)

main()
