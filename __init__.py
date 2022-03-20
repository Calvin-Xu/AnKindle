# -*- coding: utf-8 -*-
# Created: 3/27/2018
# Project : AnKindle
from functools import partial

from aqt import QAction, QMenu
from aqt import mw
from aqt.importing import importFile
from .const import MUST_IMPLEMENT_FIELDS, DEFAULT_TEMPLATE, __version__
from .const import get_api_client as plus_api
from .gui import VocabWin
from .gui_clippings import RegisterConf, _bind_qt_slots, call_purchase_dialog, SNRegDialog, start_ankindle_plus
from .lang import _trans


class ActionShow(QAction):
    def __init__(self, parent):
        super(ActionShow, self).__init__(parent)
        self.setText(_trans("AnKindle"))


class AnKindleAddon:

    def __init__(self):
        self.on_start()
        # variables
        self.main_menu = None
        self.action_show_vocab_dialog = None
        self.action_show_clipping_dialog = None
        # self.main_menu_action = None

        if not self.avl_col_model_names:
            importFile(mw, DEFAULT_TEMPLATE)

#         if plus_api() and not self.ext_unlocked:
#             self.sn_register_dlg = SNRegDialog(mw, "ANKINDLE_PLUS")
#         else:
#             self.sn_register_dlg = None

    def perform_hooks(self, func):
        # func('reviewCleanup', self.on_review_cleanup)
        func('profileLoaded', self.on_profile_loaded)
        # func('afterStateChange', self.after_anki_state_change)

    def on_profile_loaded(self):
        self.init_menu()

    def on_start(self):
        if plus_api():
            start_ankindle_plus()

    def init_menu(self):
        # init actions

        if not self.main_menu:
            self.main_menu = QMenu(_trans("AnKindle") + u" +"
                                   if self.ext_unlocked else _trans("AnKindle"), mw.form.menuTools, )
            mw.form.menuTools.addMenu(self.main_menu)

            self.action_show_vocab_dialog = QAction(_trans("SHOW VOCAB IMPORT"), self.main_menu)
            self.action_show_vocab_dialog.triggered.connect(self.on_show_vocab_dialog)
            self.action_show_vocab_dialog.setShortcut("CTRL+K")
            self.main_menu.addAction(self.action_show_vocab_dialog)

            if plus_api():
                self.action_show_clipping_dialog = QAction(_trans("SHOW CLIPPING IMPORT"), self.main_menu)
                self.action_show_clipping_dialog.triggered.connect(self.on_show_clipping_dialog)
                self.action_show_clipping_dialog.setShortcut("CTRL+L")
                self.main_menu.addAction(self.action_show_clipping_dialog)

            self.main_menu.addSeparator()
#             if plus_api():
#                 if not self.ext_unlocked:
#                     action_upgrade = QAction(_trans("UPGRADE TO PLUS"), self.main_menu)
#                     action_upgrade.triggered.connect(partial(call_purchase_dialog, mw))
#                     self.main_menu.addAction(action_upgrade)
#                 if self.sn_register_dlg:
#                     action_upgrade = QAction(_trans("REGISTER PLUS"), self.main_menu)
#                     _bind_qt_slots(action_upgrade.triggered, self.on_show_enter_sn_dialog)
#                     self.main_menu.addAction(action_upgrade)

    @property
    def ext_unlocked(self):
        # if plus_api():
        #     return plus_api().is_unlocked(
        #         RegisterConf.kk_sn_dict.get("ANKINDLE_PLUS", ''),
        #         mw.pm.profile.get('syncUser', ''), "ANKINDLE_PLUS")
        # return False
        return True

    def on_show_enter_sn_dialog(self, *args):
        self.sn_register_dlg.exec()

    def on_show_clipping_dialog(self):
        mw.onAddCard()

    def on_show_vocab_dialog(self):
        self.vocab_dlg = VocabWin(mw, self.avl_col_model_names, self.avl_decks, )
        if self.ext_unlocked:
            title = "{} Plus - {}".format(_trans("AnKindle"), __version__)
            self.vocab_dlg.setWindowTitle(title)
        else:
            self.vocab_dlg.setWindowTitle("{} - {}".format(_trans("AnKindle"), __version__))
        self.vocab_dlg.exec()

    def avl_col_model_names(self):
        _ = []
        for mid, m_values in self.collection.models.models.items():
            if not set([f.lower() for f in MUST_IMPLEMENT_FIELDS]).difference(
                    set([f[u'name'] for f in m_values[u'flds']])):
                _.append(mid)
        return [v for k, v in self.collection.models.models.items() if k in _]

    def avl_decks(self):
        _ = []
        for did, d_values in self.collection.decks.decks.items():
            _.append(did)
        return [v for k, v in self.collection.decks.decks.items() if k in _]

    @property
    def collection(self):
        """

        :rtype: _Collection
        """

        return mw.col


# region Main Entry
from anki.hooks import addHook


def start():
    # noinspection PyBroadException
    if const.HAS_SET_UP:
        return
    rr = AnKindleAddon()
    rr.perform_hooks(addHook)
    const.HAS_SET_UP = True


addHook("profileLoaded", start)
# endregion
