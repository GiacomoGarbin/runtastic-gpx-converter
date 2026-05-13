import datetime
import json
import os.path
import sys
import xml.etree.ElementTree as ET
import zipfile

USAGE_MESSAGE = "RUNTASTIC-GPX-CONVERTER: bad command line"
STARTED_MESSAGE = "conversion started, please wait ..."
SUCCESS_MESSAGE = "conversion completed"

GPX_NAMESPACE = {"gpx": "http://www.topografix.com/GPX/1/1"}
TCX_NAMESPACE = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
GPX_DIRECTORY = "Sport-sessions/GPS-data"
ELEVATION_DIRECTORY = "Sport-sessions/Elevation-data"
SESSION_DIRECTORY = "Sport-sessions"

SOURCE_TYPE_TO_TCX_SPORT = {
    "running": "Running",
    "cycling": "Biking",
}

# Fallback mapping for known adidas/runtastic sport_type_id values.
# Prefer the activity type from the source GPX when it is available, because
# that is the most precise type bundled with the export. This table is only
# used when a readable source GPX type is missing.
SPORT_TYPE_ID_TO_SOURCE_TYPE = {
    "1": "running",
    "3": "cycling",
    "7": "hiking",
    "19": "strolling",
    "44": "kayaking",
    "54": "ice_skating",
}


class Activity:
    def __init__(self):
        self.id = None
        self.datetime = None
        self.distance_km = None
        self.distance_m = None
        self.duration_display = None
        self.duration_ms = None
        self.calories = None
        self.source_type = None
        self.gpx = None
        self.tcx = None


def iter_sorted(items, key):
    for item in sorted(items, key=key):
        yield item


def transformdate(value):
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(
            value / 1000, tz=datetime.timezone.utc
        ).isoformat(timespec="milliseconds")

    parts = value.split()
    iso_value = parts[0] + "T" + parts[1] + parts[2][0:3] + ":" + parts[2][3:]
    parsed = datetime.datetime.fromisoformat(iso_value)
    return parsed.astimezone(datetime.timezone.utc).isoformat(timespec="milliseconds")


def getfeatureattributes(sessiondata, featuretype):
    for feature in sessiondata.get("features", []):
        if feature.get("type") == featuretype:
            return feature.get("attributes", {})
    return {}


def readjsonfromzip(archive, path, default=None):
    try:
        with archive.open(path, "r") as handle:
            return json.load(handle)
    except KeyError:
        return default


def getdistance(sessiondata):
    distance = sessiondata.get("distance")
    if distance is not None:
        return distance

    distance = getfeatureattributes(sessiondata, "track_metrics").get("distance")
    if distance is not None:
        return distance

    return getfeatureattributes(sessiondata, "initial_values").get("distance", 0)


def getsourcetype(archive, basename, sessiondata):
    source_gpx_path = os.path.join(
        GPX_DIRECTORY, os.path.splitext(basename)[0] + ".gpx"
    )

    try:
        source_xml = ET.fromstring(archive.read(source_gpx_path))
        source_type = source_xml.find("./gpx:trk/gpx:type", GPX_NAMESPACE)
        if source_type is not None and source_type.text:
            return source_type.text
    except (KeyError, ET.ParseError):
        pass

    return SPORT_TYPE_ID_TO_SOURCE_TYPE.get(sessiondata.get("sport_type_id"), "other")


def gettcxsport(source_type):
    return SOURCE_TYPE_TO_TCX_SPORT.get(source_type, "Other")


def getactivitysummary(activity):
    return [
        activity.id,
        activity.datetime.strftime("%d-%m-%Y %H:%M"),
        activity.distance_km,
        activity.duration_display,
    ]


def buildgpx(activity, gpsdata, eledata):
    attributes = {
        "creator": "Garmin Connect",
        "version": "1.1",
        "xsi:schemaLocation": (
            "http://www.topografix.com/GPX/1/1 "
            "http://www.topografix.com/GPX/1/1/gpx.xsd "
            "http://www.garmin.com/xmlschemas/GpxExtensions/v3 "
            "http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd "
            "http://www.garmin.com/xmlschemas/TrackPointExtension/v1 "
            "http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd"
        ),
        "xmlns:gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
        "xmlns": "http://www.topografix.com/GPX/1/1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:gpxx": "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
    }

    gpx = ET.Element("gpx", attributes)
    metadata = ET.SubElement(gpx, "metadata")
    link = ET.SubElement(metadata, "link", {"href": "connect.garmin.com"})
    link_text = ET.SubElement(link, "text")
    link_text.text = "Garmin Connect"
    metadata_time = ET.SubElement(metadata, "time")
    metadata_time.text = transformdate(gpsdata[0]["timestamp"])

    track = ET.SubElement(gpx, "trk")
    track_name = ET.SubElement(track, "name")
    track_name.text = activity.id
    track_type = ET.SubElement(track, "type")
    track_type.text = activity.source_type
    track_segment = ET.SubElement(track, "trkseg")

    same_length = len(gpsdata) == len(eledata)

    for index, point in enumerate(gpsdata):
        track_point = ET.SubElement(
            track_segment,
            "trkpt",
            {"lat": str(point["latitude"]), "lon": str(point["longitude"])},
        )

        elevation = ET.SubElement(track_point, "ele")
        if same_length and point["timestamp"] == eledata[index]["timestamp"]:
            elevation.text = str(eledata[index]["elevation"])
        else:
            elevation.text = str(point["altitude"])

        point_time = ET.SubElement(track_point, "time")
        point_time.text = transformdate(point["timestamp"])

        extensions = ET.SubElement(track_point, "extensions")
        ET.SubElement(extensions, "gpxtpx:TrackPointExtension")

    return ET.tostring(gpx, encoding="UTF-8")


def buildtcx(activity, gpsdata, eledata):
    attributes = {
        "xmlns": TCX_NAMESPACE,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": (
            TCX_NAMESPACE
            + " http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
        ),
    }

    tcx = ET.Element("TrainingCenterDatabase", attributes)
    activities = ET.SubElement(tcx, "Activities")
    tcx_activity = ET.SubElement(
        activities, "Activity", {"Sport": gettcxsport(activity.source_type)}
    )

    activity_id = ET.SubElement(tcx_activity, "Id")
    activity_id.text = transformdate(gpsdata[0]["timestamp"])

    lap = ET.SubElement(
        tcx_activity, "Lap", {"StartTime": transformdate(gpsdata[0]["timestamp"])}
    )

    total_time = ET.SubElement(lap, "TotalTimeSeconds")
    total_time.text = "%.3f" % (activity.duration_ms * 0.001)

    distance = ET.SubElement(lap, "DistanceMeters")
    distance.text = str(activity.distance_m)

    maximum_speed = ET.SubElement(lap, "MaximumSpeed")
    maximum_speed.text = str(max(point.get("speed", 0) for point in gpsdata))

    calories = ET.SubElement(lap, "Calories")
    calories.text = str(activity.calories)

    intensity = ET.SubElement(lap, "Intensity")
    intensity.text = "Active"

    trigger_method = ET.SubElement(lap, "TriggerMethod")
    trigger_method.text = "Manual"

    track = ET.SubElement(lap, "Track")
    same_length = len(gpsdata) == len(eledata)

    for index, point in enumerate(gpsdata):
        trackpoint = ET.SubElement(track, "Trackpoint")

        point_time = ET.SubElement(trackpoint, "Time")
        point_time.text = transformdate(point["timestamp"])

        position = ET.SubElement(trackpoint, "Position")
        latitude = ET.SubElement(position, "LatitudeDegrees")
        latitude.text = str(point["latitude"])
        longitude = ET.SubElement(position, "LongitudeDegrees")
        longitude.text = str(point["longitude"])

        altitude = ET.SubElement(trackpoint, "AltitudeMeters")
        if same_length and point["timestamp"] == eledata[index]["timestamp"]:
            altitude.text = str(eledata[index]["elevation"])
        else:
            altitude.text = str(point["altitude"])

        point_distance = ET.SubElement(trackpoint, "DistanceMeters")
        point_distance.text = str(point.get("distance", 0))

    return ET.tostring(tcx, encoding="UTF-8", xml_declaration=True)


def loadactivity(archive, basename):
    sessiondata = readjsonfromzip(archive, os.path.join(SESSION_DIRECTORY, basename))
    gpsdata = readjsonfromzip(archive, os.path.join(GPX_DIRECTORY, basename))
    eledata = readjsonfromzip(
        archive, os.path.join(ELEVATION_DIRECTORY, basename), default=[]
    )

    activity = Activity()
    activity.id = sessiondata["id"]
    activity.datetime = datetime.datetime.fromisoformat(
        transformdate(gpsdata[0]["timestamp"])
    )
    activity.distance_m = getdistance(sessiondata)
    activity.distance_km = "%.2f" % (activity.distance_m * 0.001)
    activity.duration_ms = sessiondata["duration"]

    seconds = activity.duration_ms * 0.001
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    activity.duration_display = "%02d:%02d:%02d" % (hours, minutes, seconds)
    activity.calories = sessiondata.get("calories", 0)
    activity.source_type = getsourcetype(archive, basename, sessiondata)
    activity.gpx = buildgpx(activity, gpsdata, eledata)
    activity.tcx = buildtcx(activity, gpsdata, eledata)
    return activity


def buildactivityindex(activities):
    html = ET.Element("html")
    body = ET.SubElement(html, "body")
    table = ET.SubElement(body, "table", {"style": "border-collapse: collapse;"})
    header_row = ET.SubElement(table, "tr")

    for value in ["session id", "datetime", "distance (km)", "duration"]:
        header = ET.SubElement(
            header_row,
            "th",
            {"style": "border: 1px solid black; padding: 2px 10px;"},
        )
        header.text = value

    for activity in iter_sorted(activities, key=lambda item: item.datetime):
        row = ET.SubElement(table, "tr")
        for value in getactivitysummary(activity):
            cell = ET.SubElement(
                row,
                "td",
                {"style": "border: 1px solid black; padding: 2px 10px;"},
            )
            cell.text = value

    return ET.tostring(html, encoding="UTF-8", method="html")


def getsessionbasenames(archive):
    for filename in archive.namelist():
        if os.path.dirname(filename) == GPX_DIRECTORY and filename.endswith(".json"):
            yield os.path.basename(filename)


def getoutputzipnames(input_path):
    base_path = os.path.join(
        os.path.dirname(input_path), os.path.basename(input_path).rstrip(".zip")
    )
    return base_path + "_GPX.zip", base_path + "_TCX.zip"


def main():
    if len(sys.argv) < 2:
        print(USAGE_MESSAGE)
        sys.exit()

    gpx_zip_name, tcx_zip_name = getoutputzipnames(sys.argv[1])

    with zipfile.ZipFile(sys.argv[1], "r") as input_zip:
        with zipfile.ZipFile(gpx_zip_name, "w", zipfile.ZIP_DEFLATED) as gpx_zip:
            with zipfile.ZipFile(tcx_zip_name, "w", zipfile.ZIP_DEFLATED) as tcx_zip:
                print(STARTED_MESSAGE)

                activities = []
                for basename in getsessionbasenames(input_zip):
                    activity = loadactivity(input_zip, basename)
                    gpx_zip.writestr(activity.id + ".gpx", activity.gpx)
                    tcx_zip.writestr(activity.id + ".tcx", activity.tcx)
                    activities.append(activity)

                activity_index = buildactivityindex(activities)
                gpx_zip.writestr("activities.html", activity_index)
                tcx_zip.writestr("activities.html", activity_index)

                print(SUCCESS_MESSAGE)


if __name__ == "__main__":
    main()
