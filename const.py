# -*- coding: utf-8 -*-
# Created: 3/27/2018
# Project : AnKindle
import atexit
import os
from threading import Thread
from time import sleep

from anki.utils import is_win
from aqt import mw
from aqt.utils import showInfo
from .libs import six
from .libs.xmlrpc import client

__version__ = "0.8.1"
HAS_SET_UP = False
ADDON_CD = 1016931132
DEBUG = False
ONLINE_DOC_URL = "https://github.com/upday7/AnKindle/blob/master/docs/DOC.md"
DEFAULT_TEMPLATE = six.ensure_text(os.path.join(os.path.dirname(__file__), u"resource", u"AnKindle.apkg"))
CLIPPINGS_DEFAULT_TEMPLATE_NAME = u"AnKindleClipping-Default"
CLIPPINGS_DEFUALT_TEMPLATE = six.ensure_text(os.path.join(os.path.dirname(__file__), u"resource",
                                                          CLIPPINGS_DEFAULT_TEMPLATE_NAME + ".apkg"))
CLIPPING_DEFAULT_MODULE_NAMES = ["AnKindleClipping-Basic", "AnKindleClipping-Cloze"]
SQL_SELECT_WORDS = """
SELECT
  ws.id,
  ws.word,
  ws.stem,
  ws.lang,
  datetime(ws.timestamp * 0.001, 'unixepoch', 'localtime') added_tm,
  lus.usage,
  bi.title,
  bi.authors
FROM words AS ws LEFT JOIN lookups AS lus ON ws.id = lus.word_key
  LEFT JOIN book_info AS bi ON lus.book_key = bi.id
"""

# MUST_IMPLEMENT_FIELDS = ("STEM", "WORD", "LANG", "CREATION_TM", "USAGE", "TITLE", "AUTHORS", "ID")
MUST_IMPLEMENT_FIELDS = ("WORD", "ORIGINAL", "LANG", "CREATION_TM", "USAGE", "TITLE", "AUTHORS", "ID")
addon_dir = os.path.split(__file__)[0]

global _RPC_CLIENT


# noinspection PyBroadException

class _client_proxy:

    def __init__(self):
        self._client = None

    @property
    def api_client(self):
        if not self._client:
            self._client = self.try_server()
        return self._client

    def try_server(self):
        _rpc_client = client.ServerProxy("http://localhost:8632", allow_none=True)
        arpc_file = os.path.join(addon_dir, 'ARPC{}'.format(".exe" if is_win else ""))
        try:
            media_folder = os.path.join(mw.pm.profileFolder(), "collection.media")
        except:
            return None
        try:
            _rpc_client.ping()
        except Exception:
            try:
                from . import ARPC
                from multiprocessing import Process
                Process(target=ARPC.AnKindlePlusAPI().start).start()
            except:
                if not os.path.isfile(arpc_file):
                    return None
                if is_win:
                    from anki.utils import call
                    try:
                        call([six.ensure_text(arpc_file), six.ensure_text(media_folder)], wait=False,
                             shell=False)
                    except UnicodeError:
                        showInfo('Cannot start AnKindle, please migrate Anki client to version 2.1 or above')
                else:
                    os.system('chmod +x "' + arpc_file + '"')
                    Thread(target=os.system, args=('"{}" "{}"'.format(arpc_file, media_folder),)).start()
            wait_secs = 50
            while wait_secs:
                try:
                    _rpc_client.ping()
                    break
                except:
                    print("Waiting for next ping of rpc server")
                    sleep(1)
                    wait_secs -= 1
                    continue
            else:
                return None
            atexit.register(_rpc_client.shutdown)
        return _rpc_client


_proxy = _client_proxy()


def get_api_client():
    return _proxy.api_client
