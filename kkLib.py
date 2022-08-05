# -*- coding: utf-8 -*-
# Copyright: Kyle, Hwang <upday7@163.com>
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import sys

IS_PY3K = sys.version[0] == '3'

if IS_PY3K:
    from http import client as httplib
    from urllib import request as web
    from urllib.request import urlretrieve

    unicode = str
else:
    import httplib
    import urllib2 as web
    from urllib import urlretrieve

import json
from datetime import datetime
from functools import partial
from operator import itemgetter
from threading import Thread
from uuid import uuid4

import aqt
from anki.lang import current_lang
from aqt import *
# from aqt.downloader import download
from aqt.utils import showInfo, openLink

ASYNC_HOOKS = []
CACHED_VALUES = []

# region Consts
trans_dict = {
    "ASK UPDATE NEW VERSION": {'zh_CN': u'新版本可用，是否更新？',
                               'en': "There's new version available, please confirm to update."},
    "UPDATE OK": {'zh_CN': u'更新完毕，请重启Anki。', 'en': "Completed! Please restart Anki."},
    "CONFIGURATION": {'zh_CN': u'设置', 'en': "Configuration"},
    "WECHAT CHANNEL": {'zh_CN': u'微信公众号', 'en': "WeChat Channel"},
    "MORE ADDON": {'zh_CN': u'更多插件', 'en': "More Addon"},
    "NEW VERSION ALERT": {'zh_CN': u'新版本可用', 'en': "New Version Available"},
    "VOTE ADDON": {'zh_CN': u"赞！", 'en': "UpVote！"},

}
# endregion

trans = lambda s: getTrans(s, trans_dict)


# region Meta Classes

class MetaConfigObj(type):
    """
    Meta class for reading/saving config.json for anki addon
    """
    metas = {}

    class StoreLocation:
        Profile = 0
        AddonFolder = 1
        MediaFolder = 3

    # noinspection PyArgumentList
    def __new__(mcs, name, bases, attributes):

        config_dict = {k: attributes[k] for k in attributes.keys() if not k.startswith("_") and k != "Meta"}
        attributes['config_dict'] = config_dict

        for k in config_dict.keys():
            attributes.pop(k)
        c = super(MetaConfigObj, mcs).__new__(mcs, name, bases, attributes)

        # region Meta properties
        # meta class
        meta = attributes.get('Meta', type("Meta", (), {}))
        # meta values
        setattr(meta, "config_dict", config_dict)
        setattr(meta, "__store_location__", getattr(meta, "__store_location__", 0))
        setattr(meta, "__config_file__", getattr(meta, "__config_file__", None))

        MetaConfigObj.metas[c.__name__] = meta
        # endregion

        if not config_dict:
            return c

        mcs.attributes = attributes  # attributes that is the configuration items

        if MetaConfigObj.metas[name].__store_location__ == MetaConfigObj.StoreLocation.MediaFolder:
            if not MetaConfigObj.metas[name].__config_file__:
                raise Exception("If StoreLocation is Media Folder, __config_file__ must be provided!")
            setattr(c, "media_json_file",
                    mcs.MediaConfigJsonFile("_{}".format(MetaConfigObj.metas[name].__config_file__).lower()))

        return c

    def __getattr__(cls, item):
        if item == "meta":
            return MetaConfigObj.metas[cls.__name__]
        else:
            load_config = lambda: cls.get_config(cls.metas[cls.__name__].__store_location__)
            config_obj = load_config()
            return config_obj.get(item)

    def __setattr__(cls, key, value):
        """
        when user set values to addon config obj class, will be passed to anki's addon manager and be saved.
        :param key:
        :param value:
        :return:
        """
        try:
            config_obj = cls.get_config(cls.metas[cls.__name__].__store_location__)
            config_obj[key] = value
            store_location = cls.metas[cls.__name__].__store_location__
            if store_location == cls.StoreLocation.AddonFolder:
                if cls.IsAnki21:
                    mw.addonManager.writeConfig(cls.AddonModelName, config_obj)
                else:
                    with open(cls.ConfigJsonFile(), "w") as f:
                        json.dump(config_obj, f)
            elif store_location == cls.StoreLocation.MediaFolder:
                with open(cls.media_json_file, "w") as f:
                    json.dump(config_obj, f)
            elif store_location == MetaConfigObj.StoreLocation.Profile:
                mw.pm.profile.update({mw.pm.name: config_obj})
        except:
            super(MetaConfigObj, cls).__setattr__(key, value)

    def get_config(cls, store_location):
        """

        :param store_location:
        :rtype: dict
        """

        def _get_json_dict(json_file):
            if not os.path.isfile(json_file):
                with open(json_file, "w") as f:
                    json.dump(cls.config_dict, f)
            with open(json_file, 'r') as ff:
                return json.load(ff)

        if store_location == MetaConfigObj.StoreLocation.Profile:
            disk_config_obj = mw.pm.profile.get(mw.pm.name, {})
            cls.config_dict.update(disk_config_obj)
        elif store_location == MetaConfigObj.StoreLocation.AddonFolder:
            # ensure json file
            obj = _get_json_dict(MetaConfigObj.ConfigJsonFile())

            if MetaConfigObj.IsAnki21():
                disk_config_obj = mw.addonManager.getConfig(MetaConfigObj.AddonModelName())
            else:
                disk_config_obj = obj
            cls.config_dict.update(disk_config_obj)
        elif store_location == MetaConfigObj.StoreLocation.MediaFolder:
            disk_config_obj = _get_json_dict(cls.media_json_file)
            cls.config_dict.update(disk_config_obj)
            with open(cls.media_json_file, "w") as f:
                json.dump(cls.config_dict, f)
        return cls.config_dict

    @staticmethod
    def IsAnki21():
        from anki import version
        return eval(version[:3]) >= 2.1

    @staticmethod
    def ConfigJsonFile():
        return os.path.join(MetaConfigObj.AddonsFolder(), "config.json")

    @staticmethod
    def MediaConfigJsonFile(file_nm):
        return os.path.join(MetaConfigObj.MediaFolder(), file_nm)

    @staticmethod
    def AddonsFolder():
        if MetaConfigObj.IsAnki21():
            _ = os.path.join(mw.addonManager.addonsFolder(), MetaConfigObj.AddonModelName())
        else:
            _ = mw.pm.addonFolder()
        if aqt.isWin:
            _ = _.encode(aqt.sys.getfilesystemencoding()).decode("utf-8")
        return _.lower()

    @staticmethod
    def AddonModelName():
        return __name__.split(".")[0]

    @staticmethod
    def MediaFolder():
        try:
            return os.path.join(mw.pm.profileFolder(), "collection.media")
        except:
            return ""


# endregion


# region Decorators

def decCache(function):
    def wrapping_function(*args):
        if args not in CACHED_VALUES:
            # Call the function only if we haven't already done it for those parameters
            CACHED_VALUES[args] = function(*args)
        return CACHED_VALUES[args]

    return wrapping_function


def decEnsureRUnicode(func):
    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        if isinstance(ret, (str, unicode)):
            return ensureUnicode(ret)
        return ret

    return wrapper


# endregion

# region Functions


def getTrans(key, trans_map, lang=current_lang):
    """

    :param key:
    :param trans_map: {'ANKINDLE': {'zh_CN': u'AnKindle', 'en': u'AnKindle'},}
    :param lang:
    :return:
    """
    key = key.upper().strip()
    if lang != 'zh_CN' and lang != 'en' and lang != 'fr':
        lang = 'en'  # fallback

    def disp(s):
        return s.capitalize()

    if key not in trans_map or lang not in trans_map[key]:
        return disp(key)
    return trans_map[key][lang]


def chunkByCount(arr, n):
    return [arr[i:i + n] for i in range(0, len(arr), n)]


def getDesktopPath():
    return os.path.join(os.path.expanduser("~"), 'Desktop')


def ensureDir(name):
    if not os.path.isdir(name):
        os.makedirs(name)
    return name


def ensureUnicode(_str):
    try:
        _str = unicode(_str)
    except UnicodeError:
        _str = unicode(_str, 'gbk')
    return _str


def getCreationDate(path_to_file):
    """

    :param path_to_file:
    :rtype: datetime
    """
    if aqt.isWin:
        return os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            return datetime.fromtimestamp(stat.st_birthtime)
        except AttributeError:
            return datetime.fromtimestamp(stat.st_mtime)


def addAsyncHook(hook, func):
    "Add a function to hook. Ignore if already on hook."
    if not ASYNC_HOOKS.get(hook, None):
        ASYNC_HOOKS[hook] = []
    if func not in ASYNC_HOOKS[hook]:
        ASYNC_HOOKS[hook].append(func)


def runAsyncHook(hook, *args):
    hook = ASYNC_HOOKS.get(hook, None)
    if hook:
        for func in hook:
            Thread(target=func, args=args).start()


def getWebGMT():
    """

    :rtype: datetime
    """
    conn = httplib.HTTPConnection("www.baidu.com")
    conn.request("GET", "/")
    r = conn.getresponse()
    ts = r.getheader('date')
    try:
        locale.setlocale(locale.LC_ALL, locale.locale_alias.get('universal.utf8@ucs4'))
    except locale.Error:
        locale.setlocale(locale.LC_ALL, "US")
    return datetime.strptime(ts[:-4].strip(), "%a, %d %b %Y %H:%M:%S")


# endregion


# region GUI


class AddonUpdater(QThread):
    """
    Class for auto-check and upgrade source codes, uses part of the source codes from ankiconnect.py
    example:

    AddonUpdater(
            self,
            "Web Query",
            "https://raw.githubusercontent.com/upday7/WebQuery/master/2.0/webquery.py",
            "https://github.com/upday7/WebQuery/blob/master/2.0.zip?raw=true",
            mw.pm.addonFolder(),
            WebQryAddon.version
        )

    """
    update_success = pyqtSignal(bool)
    new_version = pyqtSignal(bool)

    def __init__(self, parent,
                 addon_name,
                 addon_code,
                 version_py,
                 source_zip,
                 local_dir, current_version, version_key_word="__version__"):
        """
        :param parent: QWidget
        :param addon_name: addon name
        :param version_key_word: version variable name, should be in format "X.X.X", this keyword should be stated in the first lines of the file
        :param version_py: remote *.py file possibly on github where hosted __version__ variable
        :param source_zip: zip file to be downloaded for upgrading
        :param local_dir: directory for extractions from source zip file
        :param current_version: current version string in format "X.X.X"

        :type parent: QWidget
        :type addon_name: str
        :type version_key_word: str
        :type version_py: str
        :type source_zip: str
        :type local_dir: str
        :type current_version: str
        """
        super(AddonUpdater, self).__init__(parent)
        self.source_zip = source_zip
        self.version_py = version_py
        self.local_dir = local_dir
        self.version_key_word = version_key_word
        self.addon_name = addon_name
        self.current_version = current_version
        self.addon_code = addon_code

    @property
    def has_new_version(self):
        try:
            cur_ver = self._make_version_int(self.current_version)
            remote_ver = self._make_version_int(
                [l for l in self._download(self.version_py).split("\n") if l.startswith(self.version_key_word)][
                    0].split("=")[1])
            return cur_ver < remote_ver
        except:
            return False

    @staticmethod
    def _download(url):
        if url.lower().endswith(".py"):
            try:
                resp = web.urlopen(url, timeout=10)
            except web.URLError:
                return None

            if resp.code != 200:
                return None
            if sys.version[0] == '2':
                return resp.read()
            else:
                return resp.read().decode()
        else:
            with open(urlretrieve(url)[0], "rb") as f:
                if sys.version[0] == '2':
                    return f.read()
                else:
                    return f.read().decode()

    @staticmethod
    def _make_version_int(ver_string):
        ver_str = "".join([n for n in str(ver_string) if n in "1234567890"])
        return int(ver_str)

    @staticmethod
    def _make_data_string(data):
        return data.decode('utf-8')

    def ask_update(self):
        return QMessageBox.question(
            self.parent(),
            self.addon_name,
            trans("ASK UPDATE NEW VERSION"),
            QMessageBox.Yes | QMessageBox.No
        )

    def alert_update_failed(self):
        QMessageBox.critical(self.parent(),
                             self.addon_name, 'Failed to download latest version.')

    def alert_update_success(self):
        QMessageBox.information(self.parent(), self.addon_name,
                                trans("UPDATE OK"))

    def upgrade_using_anki(self):
        if MetaConfigObj.IsAnki21():
            ret = download(mw, self.addon_code)
            if ret[0] == "error":
                # err = "Error downloading %(id)s: %(error)s" % dict(id=addon_code, error=ret[1])
                return
            else:
                # err = ''
                data, fname = ret
                fname = fname.replace("_", " ")
                mw.addonManager.install(str(self.addon_code), data, fname)
                # name = os.path.splitext(fname)[0]
                mw.progress.finish()

            # mw.addonManager.downloadIds([addon_code, ])
        else:
            ret = download(mw, self.addon_code)
            if not ret:
                return
            data, fname = ret
            mw.addonManager.install(data, fname)
            mw.progress.finish()

    def upgrade(self):
        try:
            self.upgrade_using_anki()
            self.update_success.emit(True)
        except:
            try:
                data = self._download(self.source_zip)
                if data is None:
                    QMessageBox.critical(self.parent(),
                                         self.addon_name, 'Failed to download latest version.')
                else:
                    zip_path = os.path.join(self.local_dir,
                                            uuid4().hex + ".zip")
                    with open(zip_path, 'wb') as fp:
                        fp.write(data)

                    # unzip
                    from zipfile import ZipFile
                    zip_file = ZipFile(zip_path)
                    if not os.path.isdir(self.local_dir):
                        os.makedirs(self.local_dir, exist_ok=True)
                    for names in zip_file.namelist():
                        zip_file.extract(names, self.local_dir)
                    zip_file.close()

                    # remove zip file
                    os.remove(zip_path)

                    self.update_success.emit(True)
            except:
                self.update_success.emit(False)

    def run(self):
        if self.has_new_version:
            self.new_version.emit(True)
        else:
            self.new_version.emit(False)


class ClickCloseDialog(QDialog):
    def __init__(self, parent, img_file):
        super(ClickCloseDialog, self).__init__(parent)
        self.l = QVBoxLayout(self)
        self.image_label = QLabel(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        self.l.addWidget(self.image_label)

        self.setToolTip(trans("CLICK CLOSE"))
        self.set_qr(img_file)

    def set_qr(self, qr_file):
        pix = QPixmap()
        pix.load(qr_file)
        self.image_label.setPixmap(pix)

    def mousePressEvent(self, evt):
        self.accept()


class JsonConfigEditor(QDialog):
    class Ui_Dialog(object):
        def setupUi(self, Dialog):
            Dialog.setObjectName("Dialog")
            Dialog.setWindowModality(Qt.ApplicationModal)
            Dialog.resize(631, 521)
            self.verticalLayout = QVBoxLayout(Dialog)
            self.verticalLayout.setObjectName("verticalLayout")
            self.editor = QPlainTextEdit(Dialog)
            sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            sizePolicy.setHorizontalStretch(0)
            sizePolicy.setVerticalStretch(3)
            sizePolicy.setHeightForWidth(self.editor.sizePolicy().hasHeightForWidth())
            self.editor.setSizePolicy(sizePolicy)
            self.editor.setObjectName("editor")
            self.verticalLayout.addWidget(self.editor)
            self.buttonBox = QDialogButtonBox(Dialog)
            self.buttonBox.setOrientation(Qt.Horizontal)
            self.buttonBox.setStandardButtons(
                QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            self.buttonBox.setObjectName("buttonBox")
            self.verticalLayout.addWidget(self.buttonBox)

            self.retranslateUi(Dialog)
            self.buttonBox.accepted.connect(Dialog.accept)
            self.buttonBox.rejected.connect(Dialog.reject)
            QMetaObject.connectSlotsByName(Dialog)

        def retranslateUi(self, Dialog):
            _translate = QCoreApplication.translate
            Dialog.setWindowTitle(trans("CONFIGURATION"))

    def __init__(self, dlg, json_file):
        super(JsonConfigEditor, self).__init__(dlg)
        self.json = json_file
        self.conf = None
        self.form = self.Ui_Dialog()
        self.form.setupUi(self)

    def updateText(self):
        with open(self.json, "r") as f:
            self.conf = json.load(f)
        self.form.editor.setPlainText(
            json.dumps(self.conf, sort_keys=True, indent=4, separators=(',', ': ')))

    def exec_(self):
        self.updateText()
        super(JsonConfigEditor, self).exec_()

    def accept(self):
        txt = self.form.editor.toPlainText()
        try:
            self.conf = json.loads(txt)
        except Exception as e:
            showInfo(trans("Invalid configuration: ") + repr(e))
            return

        with open(self.json, "w") as f:
            json.dump(self.conf, f)

        super(JsonConfigEditor, self).accept()


class _ImageButton(QPushButton):
    def __init__(self, parent, icon_url):
        super(_ImageButton, self).__init__(parent)
        self.setIcon(icon_url)
        self.set_size(30, 30)

    def set_size(self, width, height):
        self.setFixedSize(QSize(width, height))

    def setIcon(self, icon_url):
        super(_ImageButton, self).setIcon(QIcon(icon_url))


class WeChatButton(_ImageButton):
    def __init__(self, parent, qr_file):
        super(WeChatButton, self).__init__(parent, ":/icon/wechat.png")
        self.setObjectName("btn_wechat")
        self.setToolTip(trans("WECHAT CHANNEL"))
        self.setWhatsThis(self.toolTip())
        self.clicked.connect(self.on_clicked)
        self._qr_file_nm = qr_file

    def on_clicked(self):
        self.parent().hide()
        ClickCloseDialog(self, self._qr_file_nm).exec_()
        self.parent().show()


class VoteButton(_ImageButton):

    def __init__(self, parent, addon_cd):
        super(VoteButton, self).__init__(parent, ":/icon/vote.png")
        self.addon_cd = addon_cd
        self.clicked.connect(self.on_clicked)
        self.setObjectName("btn_vote")
        self.setToolTip(trans("VOTE ADDON"))

    def on_clicked(self):
        openLink("https://ankiweb.net/shared/review/%s" % self.addon_cd)


class MoreAddonButton(_ImageButton):
    class _download_json(QThread):
        def __init__(self, parent, json_file):
            super(MoreAddonButton._download_json, self).__init__(parent)
            self.json_file = json_file

        def run(self):
            try:
                urlretrieve("https://raw.githubusercontent.com/upday7/LiveCodeHub/master/more_addons.json",
                            self.json_file)
            except:
                pass

    def __init__(self, parent):
        super(MoreAddonButton, self).__init__(parent, ":/icon/more.png")
        self.setObjectName("btn_more_addon")
        self.setToolTip(trans("MORE ADDON"))
        self.json_file = "_more_addons.json"
        self._thr_download_json = MoreAddonButton._download_json(self, self.json_file)
        self._thr_download_json.finished.connect(self.setup_menu)
        self.m = None
        self._thr_download_json.start()

    def setup_menu(self):
        if not os.path.isfile(self.json_file):
            self.setVisible(False)
        else:
            self.m = MoreAddonMenu(self, self.json_file)
            self.m.setObjectName("mmr")
            self.setVisible(True)

            if IS_PY3K:
                def _show_menu():
                    self.m.move(QCursor.pos())
                    self.m.show()

                self.clicked.connect(lambda clicked: _show_menu())
            else:
                self.setMenu(self.m)


class UpgradeButton(_ImageButton):
    def __init__(self, parent, updater):
        super(UpgradeButton, self).__init__(parent, ":/icon/alert.png")
        self.setObjectName("btn_updater")
        self.setToolTip(trans("NEW VERSION ALERT"))
        self.updater = updater
        self.updater.new_version.connect(self.on_addon_new_version)
        self.updater.update_success.connect(self.on_addon_updated)
        self.setVisible(False)
        self.clicked.connect(self.on_clicked)

    def on_addon_new_version(self, new_version_available):
        self.setVisible(new_version_available)

    def on_addon_updated(self, success):
        if success:
            self.updater.alert_update_success()
            self.setVisible(False)
        else:
            self.updater.alert_update_failed()

    def on_clicked(self):
        if self.updater.ask_update() == QMessageBox.Yes:
            self.updater.upgrade()


class MoreAddonMenu(QMenu):
    def __init__(self, parent, config_json=r"F:\PyProjects\AnkiProjects\TomatoClock\AnkiMoreAddons.json"):
        super(MoreAddonMenu, self).__init__(parent)
        self.setObjectName("more_addon_menu")
        with open(config_json, "r") as f:
            try:
                self.config_json = json.load(f, encoding="utf-8")
            except:
                return
        self.parse()

    def parse(self):
        for index, addon_data in sorted(self.config_json.items(), key=itemgetter(0)):
            addon_nm = addon_data.get(current_lang, "en")
            anki_versions = addon_data.get("anki_versions")
            urls = addon_data.get("urls")
            tip_data = addon_data.get("tip")

            if not urls:
                return

            if len(urls) == 1:
                addon_menu = QAction(addon_nm, self)
            else:
                addon_menu = QMenu(addon_nm, self)

            addon_menu.setToolTip(tip_data.get(current_lang, "en"))
            addon_menu.setWhatsThis(self.toolTip())

            for url_nm, url_data in sorted(urls.items(), key=itemgetter(0)):
                if len(urls) == 1:
                    addon_menu.triggered.connect(partial(openLink, (url_data['url'])))
                else:
                    url_action = QAction(url_data.get(current_lang, "en"), addon_menu)
                    url_action.triggered.connect(partial(openLink, (url_data['url'])))
                    addon_menu.addAction(url_action)

            if isinstance(addon_menu, QAction):
                self.addAction(addon_menu)
            else:
                self.addMenu(addon_menu)


def HLine():
    toto = QFrame()
    toto.setFrameShape(QFrame.Shape.HLine)
    toto.setFrameShadow(QFrame.Shadow.Sunken)
    return toto


def VLine():
    toto = QFrame()
    toto.setFrameShape(QFrame.Shape.VLine)
    toto.setFrameShadow(QFrame.Shadow.Sunken)
    return toto


# endregion

if __name__ == '__main__':
    from sys import version
