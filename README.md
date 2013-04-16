twit2gml
========

Collection of Python scripts that export Twitter network to a GML format. The
GML file can be used to visualize the network in Gephi or other network visualization
tools.

Dependencies
============
In order to use the code you need to install the following Python libraries:
* Twython, available from [Ryan McGrath's Github Project](https://github.com/ryanmcgrath/twython
"Twython on GitHub")

Usage
=====
$ python twit2gml --key [[API_Key]] --secret [[API_Secret]] --screen_name [[Twitter_screen_name]]