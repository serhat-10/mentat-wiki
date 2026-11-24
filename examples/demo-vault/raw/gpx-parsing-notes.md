<!-- Fictional source. Written for the mentat-wiki demo vault. Not a real article. -->

# Reading a GPX track without a map library

A note from a fictional hiking club's tooling evening.

GPX is XML. The root element holds one or more tracks, each track holds segments, and each segment
holds trackpoints in order. A trackpoint carries latitude and longitude as attributes. Elevation and
time are child elements, and both are optional.

The walkthrough starts with the smallest possible reader: walk the document, remember the current
track and segment, and append a point when a trackpoint closes. That is enough for a profile. No map
tiles, no projection, no geometry library.

Two details matter more than they look.

First, elevation is optional. Route exports often drop it, and consumer apps write an empty element
instead of a number. Treat both as missing. Do not substitute zero, or the profile gains a cliff at
sea level.

Second, keep memory flat. A long ride can hold tens of thousands of points, and a parser that keeps
the whole XML tree costs more than the numbers are worth. A streaming reader returns points one at a
time, so the profile code can sum as it goes.

The note also suggests a small test folder: one clean file, one file with no elevation, one file
with a single-point segment. Those three cover most breakage seen in practice.

Fictional. No real article, person or organisation is described.
