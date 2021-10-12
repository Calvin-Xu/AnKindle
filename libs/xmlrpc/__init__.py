import sys

isPY3 = sys.version_info[0] == 3
if isPY3:
    from . import client as xmlclient3
    client = xmlclient3
else:
    from . import xmlrpclib

    client = xmlrpclib
