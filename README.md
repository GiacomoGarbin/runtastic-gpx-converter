# runtastic-gpx-converter

This Python script converts Adidas Running (formerly Runtastic) account data exports to Garmin-friendly activity archives.

It supports older and newer adidas exports, including exports that:

- store GPS timestamps as Unix milliseconds instead of formatted strings
- omit `Sport-sessions/Elevation-data`
- include pre-generated GPX files next to the GPS JSON payload
- keep distance inside nested `features` objects instead of a top-level field

The converter generates both:

- `*_GPX.zip`: preserves the source GPX activity type where available
- `*_TCX.zip`: better suited for Garmin Connect imports because TCX carries an explicit sport field (`Running`, `Biking`, or `Other`)

## Instructions

1. Export your account data in a ZIP file from Runtastic, as shown [here](https://help.runtastic.com/hc/en-us/articles/360000953365-Export-Account-Data)
2. Convert your data with runtastic-gpx-converter as follows

```sh
> py runtastic-gpx-converter.py YOUR-ACCOUNT-DATA.zip
```

This command will create two new ZIP files in the same folder as the original export:

- `YOUR-ACCOUNT-DATA_GPX.zip`
- `YOUR-ACCOUNT-DATA_TCX.zip`

3. Import your fitness data into Garmin Connect, as shown [here](https://support.garmin.com/en-IE/?faq=ACgfZF717vAeVfhHgPrFv6)

If Garmin Connect classifies GPX uploads as `Other`, prefer the generated TCX archive. Garmin Connect generally respects the TCX sport field for `Running` and `Biking`.
