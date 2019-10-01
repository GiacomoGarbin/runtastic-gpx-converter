# runtastic-gpx-converter

This Python script converts Adidas Running (formerly Runtastic) account data exports to GPX format, ready to be imported into Garmin Connect.

## Instructions

1. Export your account data in a ZIP file from Runtastic, as shown [here](https://help.runtastic.com/hc/en-us/articles/360000953365-Export-Account-Data)
2. Convert your data with runtastic-gpx-converter as follows

```sh
> py runtastic-gpx-converter.py YOUR-ACCOUNT-DATA.zip
```
  this command will create a new ZIP file in the same folder as the original with all your account data converted to GPX format

3. Import your fitness data in GPX format into Garmin Connect, as shown [here](https://support.garmin.com/en-IE/?faq=ACgfZF717vAeVfhHgPrFv6)
