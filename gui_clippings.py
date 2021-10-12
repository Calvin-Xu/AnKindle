# -*- coding: utf-8 -*-
import os
import re
from functools import partial
from itertools import groupby
from operator import itemgetter
from sqlite3 import dbapi2 as sqlite
from warnings import filterwarnings

from anki.hooks import wrap, addHook, runHook, _hooks
from anki.lang import _, currentLang
from aqt import mw, QTreeWidgetItem, QMenu, QAction, QCursor, Qt, QFont, QIcon, isMac, QDialog, QPushButton, \
    QListWidget, QSize, QComboBox, QLineEdit, QLabel, QApplication, QGroupBox, QCheckBox, QScrollArea, QGridLayout
from aqt.addcards import AddCards, \
    QHBoxLayout, QSizePolicy, QVBoxLayout, QFrame, QSpacerItem, QTreeWidget
from aqt.editor import Editor
from aqt.importing import importFile
from aqt.utils import showInfo, getFile, showText, showCritical, showWarning, askUser, openLink

try:
    from . import kkLib, gui, const
except:
    import kkLib, gui, const
from .config import Config
from .const import get_api_client as plus_api
from .lang import _trans
from .libs import six

filterwarnings("ignore")

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

DBError = sqlite.Error
# region Constants
TAOBAO_URL = "https://item.taobao.com/item.htm?spm=0.7095261.0.0.34961debEl0Gr9&id=570184655231"
FASTSPRING_URL = 'https://kuangkuang.onfastspring.com/ankindle-plus'


# endregion


def start_import_default_templates():
    all_module_name = {}
    for mid, m_values in mw.col.models.models.items():
        module_name = m_values['name']
        all_module_name[module_name] = mid

    profiles = {}
    for clipping_temp_index, default_module_name in enumerate(const.CLIPPING_DEFAULT_MODULE_NAMES):
        if default_module_name not in all_module_name.keys() and \
                Cnf.is_ankindle_plus_first_run and os.path.isfile(const.CLIPPINGS_DEFUALT_TEMPLATE):
            importFile(mw, const.CLIPPINGS_DEFUALT_TEMPLATE)
            for mid, m_values in mw.col.models.models.items():
                module_name = m_values['name']
                if module_name != default_module_name:
                    continue
                _ = {
                    _trans("QUICK MENU EXAMPLE") if not clipping_temp_index else _trans("CLOZE") +
                                                                                 u"-" + _trans("QUICK MENU EXAMPLE"):
                        {mid: (0, 1, 1, False, False)}
                }
                if profiles:
                    profiles.update(_)
                else:
                    profiles = _
    if profiles:
        Cnf.user_note_map = profiles
        Cnf.is_ankindle_plus_first_run = False


def start_ankindle_plus():
    start_import_default_templates()
    wrap_editor_for_clippings_import()


# endregion

# region Anki Widgets


# region Adjust Anki
def _add_clipping_tree(self):
    assert isinstance(self, AddCards)
    self.form.verticalLayout.removeWidget(self.form.fieldsArea)
    self.form.verticalLayout.removeWidget(self.form.buttonBox)

    vlayout = QVBoxLayout()
    vlayout.addWidget(self.form.fieldsArea)
    vlayout.addWidget(self.form.buttonBox)

    hlayout = QHBoxLayout()

    self.clipping_frame = _ClippingFrame(self, )
    hlayout.addWidget(self.clipping_frame, )
    hlayout.addWidget(kkLib.VLine())
    hlayout.addItem(vlayout)
    self.form.verticalLayout.addItem(hlayout)


def _add_start_btn(self):
    assert isinstance(self, AddCards)
    self.btn_start = kkLib._ImageButton(self, _png("kindle.png"))
    self.form.horizontalLayout.insertWidget(0, self.btn_start)
    if isMac:
        self.form.horizontalLayout.setSpacing(20)


def _adjust_after_add_cards(self):
    runHook("after_addcards")


def _adjust_before_add_cards(self):
    setattr(self.editor, "last_focused_field", self.editor.currentField)


def _adjust_after_add_cards_model_changed(self):
    assert isinstance(self, AddCards)
    runHook("add_cards_model_changed", self.editor.note)


def _adjust_after_note_loaded(self, *args):
    assert isinstance(self, Editor)
    if hasattr(self, "last_focused_field"):
        try:
            eval = self.web.evalWithCallback
        except AttributeError:
            eval = lambda x, cb: self.web.eval(x)
        eval("focusField(%s)" % self.last_focused_field, lambda x: True)


def wrap_editor_for_clippings_import():
    AddCards.addCards = wrap(AddCards.addCards, _adjust_before_add_cards, "before")
    AddCards.addCards = wrap(AddCards.addCards, _adjust_after_add_cards, "after")
    AddCards.onModelChange = wrap(AddCards.onModelChange, _adjust_after_add_cards_model_changed, "after")
    AddCards.setupEditor = wrap(AddCards.setupEditor, _add_clipping_tree, "before")
    # AddCards.setupChoosers = wrap(AddCards.setupChoosers, _add_start_btn, "before")
    Editor.loadNote = wrap(Editor.loadNote, _adjust_after_note_loaded, "after")


# endregion

def _png(n):
    # return os.path.join(os.path.dirname(os.path.split(__file__)[0]),"resource",n)
    return os.path.join(os.path.dirname(__file__), "resource", n)


class _ItemContextMenu(QMenu):
    def __init__(self, parent, ):
        super(_ItemContextMenu, self).__init__(parent)
        # self.clipping, self.remark = None, None

        self.menu_clipping = QMenu(_trans("CLIPPING"), self, )
        self.menu_remark = QMenu(_trans("remark"), self)

        self.action_mark_complete = QAction(self)
        self.update_complete_action(False)

        self.quick_menu_actions = []
        self.addSeparator()
        self.addMenu(self.menu_clipping)
        self.clipping_separator = self.addSeparator()
        self.addMenu(self.menu_remark)

        self.remark_separator = self.addSeparator()

        self.last_separator = self.addSeparator()
        self.addActions(
            [self.action_mark_complete, ]
        )

        self.note_insert_actions = {
            "remark": [],
            "clipping": []
        }

    def add_note_fields_actions(self, remark_actions=None, clipping_actions=None):
        if clipping_actions:
            existed_actions = self.note_insert_actions.get("clipping", [])
            if not existed_actions: existed_actions = []
            for a in existed_actions:
                self.removeAction(a)
            for a in clipping_actions:
                self.insertAction(self.clipping_separator, a)
            self.note_insert_actions['clipping'] = clipping_actions

        if remark_actions:
            existed_actions = self.note_insert_actions.get("remark", [])
            if not existed_actions: existed_actions = []
            for a in existed_actions:
                self.removeAction(a)
            for a in remark_actions:
                self.insertAction(self.remark_separator, a)
            self.note_insert_actions['remark'] = remark_actions

    def update_complete_action(self, completed, pre_fix=''):
        self.action_mark_complete.setText(u"{} {} '{}'".format(
            u"{} ".format(pre_fix) if pre_fix else "",
            _trans("MARK AS"),
            _trans("INCOMPLETE CLIPPINGS") if completed else
            _trans("COMPLETED CLIPPINGS")
        )
        )

    def enable_note(self, enable):
        # self.clipping, self.remark = clipping, remark
        self.menu_remark.setEnabled(enable)

        if not enable:
            existed_actions = self.note_insert_actions.get("remark", [])
            if not existed_actions: existed_actions = []
            for a in existed_actions:
                a.setVisible(False)
                self.removeAction(a)
            self.note_insert_actions['remark'] = []

        # clippings groups
        clippings_actions = self.note_insert_actions.get("clipping")
        clipping_items_visible = clippings_actions and clippings_actions.__len__() <= 5
        list(map(lambda a: a.setVisible(clipping_items_visible), clippings_actions))
        self.clipping_separator.setVisible(clipping_items_visible)

        self.menu_clipping.setEnabled(not clipping_items_visible)

        if enable:
            # remark groups
            remark_actions = self.note_insert_actions.get("remark")
            remark_items_visible = remark_actions and remark_actions.__len__() <= 5
            list(map(lambda a: a.setVisible(remark_items_visible), remark_actions))
            self.remark_separator.setVisible(remark_items_visible)

            self.menu_remark.setEnabled(not remark_items_visible)

    def show(self, pos=None):
        if not pos:
            pos = QCursor.pos()
        self.move(pos)
        super(_ItemContextMenu, self).show()

    def update_quick_menus(self, pre_fix=""):
        for action in self.quick_menu_actions:
            self.removeAction(action)
        for quick_menu_profile_name in [k for k in Cnf.user_note_map.keys() if k.strip()][::-1]:
            action = QAction(u'{}{}'.format(u"{} ".format(pre_fix) if pre_fix else "", quick_menu_profile_name), self)
            self.quick_menu_actions.append(action)
            self.insertAction(self.actions()[0], action)


def _debug_step(*args):
    showText(
        ";".join(str(arg) for arg in args))


def _bind_qt_slots(signal, hook_func):
    hook = hook_func.__name__
    if hook in _hooks:
        _hooks.pop(hook)
    addHook(hook, getattr(hook_func.__self__, hook))
    signal.connect(partial(runHook, hook))


def move_win_center(win):
    frameGm = win.frameGeometry()
    screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
    centerPoint = QApplication.desktop().screenGeometry(screen).center()
    frameGm.moveCenter(centerPoint)
    win.move(frameGm.topLeft())


# noinspection PyArgumentList
def call_purchase_dialog(parent, triggered=False, type_=1):
    suggestion_msg = _trans("UPGRADE SUGGESTION") if \
        type_ == 1 else _trans("UPGRADE SUGGESTION MORE CLIPPINGS") if type_ == 2 \
        else _trans("UPGRADE SUGGESTION MORE MDX")
    if askUser(suggestion_msg, parent, title=_trans("UPGRADE TO PLUS")):
        openLink(TAOBAO_URL)
        openLink(FASTSPRING_URL)


class _ClippingFrame(QFrame):
    def __init__(self, add_card, ):
        super(_ClippingFrame, self).__init__(add_card)
        assert isinstance(add_card, AddCards)
        self.file_clipping = None

        self.add_card = add_card
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(400)

        self.l = QVBoxLayout(self)

        # buttons
        self.layout_btn = QHBoxLayout()
        if isMac:
            self.layout_btn.setSpacing(20)
        self.btn_select_file = kkLib._ImageButton(self, _png("select_file.png"))

        self.btn_help = gui._HelpBtn(self)  # kkLib._ImageButton(self, _png("help.png"))
        self.btn_setting = kkLib._ImageButton(self, _png("setting.png"))
        self.btn_change_status = kkLib._ImageButton(self, _png("status.png"))
        self.btn_change_status.setCheckable(True)

        self._btns = [
            self.btn_select_file, self.btn_help, self.btn_setting, self.btn_change_status
        ]

        self.layout_btn.addWidget(self.btn_change_status)
        self.layout_btn.addSpacerItem(QSpacerItem(20, 10,
                                                  QSizePolicy.Expanding,
                                                  QSizePolicy.Minimum))
        self.layout_btn.addWidget(self.btn_select_file)
        self.layout_btn.addWidget(self.btn_setting)
        self.layout_btn.addWidget(self.btn_help)
        self.l.addItem(self.layout_btn)

        list(map(lambda c: c.setVisible(False), self._btns))

        # tree
        grp_tree = QGroupBox(self)
        l_tree = QVBoxLayout(grp_tree)
        self.tree_contents = QTreeWidget(self)
        self.tree_contents.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_contents.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.tree_contents.setContextMenuPolicy(Qt.CustomContextMenu)

        l_tree.addWidget(self.tree_contents)
        self.l.addWidget(grp_tree)

        # preview frame
        self.grp_preview = QGroupBox(self)
        self.grp_preview.setVisible(False)
        l_preview = QVBoxLayout(self.grp_preview)
        self.lb_preview = QLabel("", self)
        self.lb_preview.setWordWrap(True)
        self.lb_preview.setAutoFillBackground(True)

        self.scroll_widget = QScrollArea()
        self.scroll_widget.setWidget(self.lb_preview)
        self.scroll_widget.setWidgetResizable(True)
        self.scroll_widget.setAutoFillBackground(True)
        self.scroll_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        l_preview.addWidget(self.scroll_widget)

        self.l.addWidget(self.grp_preview)

        # button start
        self.btn_start = add_card.btn_start
        _bind_qt_slots(self.btn_start.clicked, self.on_start_clicked)

        # other widgets
        self.tree_context_menu = _ItemContextMenu(self.tree_contents)

        # variables

        self.completed_status = False
        self.clipping_item_clipping = ''
        self.clipping_item_remark = ''
        self.clipping_item_id = ''
        self.clipping_item_book = ''
        self.clipping_item_author = ''

        # init properties
        self.setVisible(False)

        # hooks
        addHook("after_addcards", self.on_after_addcards)

        self.bind_slots()

    def on_upgrade_btn_win_clicked(self, clicked):
        showText(_trans("WIN UPDATE") %
                 const.ADDON_CD, self.add_card, title=_trans("ANKINDLE"))

    def on_after_addcards(self):
        if not self.cur_item:
            return
        if Cnf.mark_complete_aft_add_card:
            self.tree_context_menu.action_mark_complete.trigger()

    def on_start_clicked(self, clicked):
        self.setVisible(True)
        list(map(lambda c: c.setVisible(True), self._btns))
        self.btn_start.setVisible(False)
        if self.try_clippings():
            self.load_clippings()

        add_cards_win_min_size = QSize(814, 553)
        if (self.add_card.size().height() < add_cards_win_min_size.height() or
                self.add_card.size().width() < add_cards_win_min_size.width()):
            self.add_card.setMinimumSize(add_cards_win_min_size)
            move_win_center(self.add_card)

    def on_tree_context_menu(self, *args, **kwargs):
        item = self.cur_item
        if not item:
            return

        if self.cur_item_type in (1, 3):  # book item
            self.tree_context_menu.menu_clipping.setEnabled(False)
            self.tree_context_menu.menu_remark.setEnabled(False)
            self.tree_context_menu.update_complete_action(self.btn_change_status.isChecked(), _trans("BATCH"))
        elif self.cur_item_type == 2:
            self.tree_context_menu.update_complete_action(self.btn_change_status.isChecked(), )
            # region add menu actions - clippings
            for menu, trigger, fields_type in [
                (self.tree_context_menu.menu_clipping,
                 self.on_clipping_triggered, "clipping"),
                (self.tree_context_menu.menu_remark,
                 self.on_remark_triggered, "remark")
            ]:
                menu.clear()
                menu.setEnabled(True)

                def _gen_actions(parent_):
                    _actions = [
                        QAction(u"{}: {}".format(fld_dict["ord"], fld_dict["name"]), parent_)
                        for fld_dict in self.note_fld_names
                        if fld_dict['name'].upper() != "BOOK"]
                    list(
                        map(lambda action: action.triggered.connect(partial(trigger, int(action.text().split(":")[0]))),
                            _actions))
                    return _actions

                # actions for grouped sub-menu
                menu.addActions(_gen_actions(menu))

                # context for main menu
                if fields_type == "clipping":
                    self.tree_context_menu.add_note_fields_actions(
                        clipping_actions=_gen_actions(self.tree_context_menu))
                else:
                    self.tree_context_menu.add_note_fields_actions(remark_actions=_gen_actions(self.tree_context_menu))

            # endregion
            note = item.text(1)
            self.tree_context_menu.enable_note(True if note else False)

        # bind quick menu actions every time as which is updated on every shown
        if self.cur_item_type in (1, 3):
            self.tree_context_menu.update_quick_menus(_trans("BATCH"))
        else:
            self.tree_context_menu.update_quick_menus()
        for action in self.tree_context_menu.quick_menu_actions:
            action.triggered.connect(partial(self.on_quick_menu_triggered,
                                             action.text().replace(_trans("BATCH"), "").strip()))
        self.tree_context_menu.show()

    def on_quick_menu_triggered(self, *args):
        profile_name = args[0]
        profile_dict = Cnf.user_note_map.get(profile_name)
        if not profile_dict:
            return
        try:
            mid, (clipping_fld, rmk_fld, did, auto_save, auto_complete) = list(profile_dict.items())[0]
        except ValueError:
            mid, (clipping_fld, rmk_fld, did,) = list(profile_dict.items())[0]
            auto_save = False
            auto_complete = False

        model = mw.col.models.get(mid)
        flds = [f['name'] for f in mw.col.models.get(mid)['flds']]

        # region change model/note
        # copied from addcard.modelchooser.onModelChange
        self.add_card.modelChooser.deck.conf['curModel'] = mid
        cdeck = self.add_card.modelChooser.deck.decks.current()
        cdeck['mid'] = mid
        self.add_card.modelChooser.deck.decks.save(cdeck)
        runHook("currentModelChanged")
        mw.reset()
        # endregion

        # change deck
        deck_name = mw.col.decks.get(did)['name']
        try:
            self.add_card.deckChooser.setDeckName(deck_name)
        except AttributeError:  # if anki27
            self.add_card.deckChooser.deck.setText(deck_name)

        items_count = 0
        for item in self.cur_items:
            if item.childCount():
                continue
            items_count += 1
        notes = []
        confirm_batch_adding = False
        if self.cur_item_type in (1, 3):
            confirm_batch_adding = askUser(_trans("BATCH NOTE ADDING ALERT") % (items_count, deck_name),
                                           self.add_card, title=_trans("ANKINDLE"))
        for item in self.cur_items:
            if item.childCount():
                continue
            if self.cur_item_type == 2:
                self.auto_fill(self.cur_item, clipping_fld, rmk_fld)
                if auto_save:
                    self.add_card.addButton.click()
                    if auto_complete:
                        self.on_mark_complete_triggered(batch_mode=False)
            else:
                if not confirm_batch_adding:
                    continue
                note = mw.col.newNote()
                (clipping_item_clipping, clipping_item_remark,
                 clipping_item_id) = item.text(0), item.text(1), item.text(2)
                clipping_item_book = item.parent().text(0)
                clipping_item_author = item.text(3)

                note.fields[clipping_fld] = clipping_item_clipping
                note.fields[rmk_fld] = clipping_item_remark

                book_index = self._auto_fil_indexes['BOOK']
                author_index = self._auto_fil_indexes['AUTHOR']

                if book_index:
                    note.fields[book_index] = clipping_item_book
                if author_index:
                    note.fields[author_index] = clipping_item_author

                # set tag
                tags = self._get_tags_tobe_set(clipping_item_book, clipping_item_author)
                note.tags.extend(tags)
                self.add_card.addNote(note)
                notes.append((note, clipping_item_id))
        for n, item_id in notes:
            if Cnf.mark_complete_aft_add_card:
                self.on_mark_complete_triggered(item_id=item_id, complete=True, batch_mode=False)
        if not confirm_batch_adding:
            return
        else:
            showInfo(
                _trans("BATCH NOTE ADDED ALERT") % (notes.__len__(), deck_name),
                self.add_card, title=_trans("ANKINDLE")
            )
        self.load_clippings(self.btn_change_status.isChecked())

    def on_btn_status_checked(self, checked):
        self.completed_status = checked
        self.tree_context_menu.update_complete_action(checked)
        self.load_clippings(checked)

    def on_tree_clipping_item_changed(self, old_item, current_item):
        pass

    def on_tree_clipping_item_double_clicked(self, item, index):
        self._get_item_text(item)
        self._set_preview_text()
        self.set_editor_note(self.clipping_item_clipping, 0)
        self.set_editor_note(self.clipping_item_remark, 1)

    def on_tree_clipping_item_pressed(self, item, i):
        self._get_item_text(item)

        self._set_preview_text()

#         if "Upgrade to Plus" in self.clipping_item_clipping:
#             call_purchase_dialog(self.parent(), type_=2)
#             return

        self._fill_book_field(self.clipping_item_book, self.clipping_item_author)

    def on_mark_complete_triggered(self, *args, **kwargs):
        batch_mode = kwargs.get("batch_mode", _trans("BATCH") in self.tree_context_menu.action_mark_complete.text())
        if not batch_mode:
            id_ = kwargs.get("item_id", self.clipping_item_id)
            complete = kwargs.get("complete", not self.completed_status)
            plus_api().mark_item_complete(id_, complete)
            plus_api().db_commit()
        else:
            if self.cur_item_type in (1, 3):
                for item in self.cur_items:
                    if item.childCount():
                        continue
                    (clipping_item_clipping, clipping_item_remark,
                     clipping_item_id) = item.text(0), item.text(1), item.text(2)
                    plus_api().mark_item_complete(clipping_item_id, not self.completed_status)
            plus_api().db_commit()
        self.load_clippings(self.completed_status)

    def _set_preview_text(self):
        def _body(s):
            return """
                <html><head/><body>%s</body></html>
                """ % s

        self.grp_preview.setMaximumHeight(self.parent().height() * 0.20)
        if self.clipping_item_clipping:
            self.grp_preview.setVisible(True)
            text = _body('<p align="left">%s</p>' % self.clipping_item_clipping)
        else:
            self.grp_preview.setVisible(False)
            text = _body('<p align="center">%s</p>' % _trans("PREVIEW"))

        self.lb_preview.setText(text)
        # self.lb_preview.adjustSize()
        # self.lb_preview.setStyleSheet(".QScrollArea{border:1px solid rgb(180, 180, 180);}")
        self.lb_preview.setContentsMargins(5, 5, 5, 5)

    def _get_item_text(self, item):
        self.clipping_item_clipping = ''
        self.clipping_item_remark = ''
        self.clipping_item_id = ''
        self.clipping_item_book = ''
        self.clipping_item_author = ''

        if not item:
            return
        if item.childCount():
            return
        (self.clipping_item_clipping, self.clipping_item_remark,
         self.clipping_item_id) = item.text(0), item.text(1), item.text(2)
        self.clipping_item_book = item.parent().text(0)
        self.clipping_item_author = item.text(3)

    def auto_fill(self, item, *args, **kwargs):
        """

        :type item: QTreeWidgetItem
        :param args:
        :return:
        """
        if item.childCount():
            return
        press_item = kwargs.get("press_item", True)

        indexes = list(range(10))
        for i in self._auto_fil_indexes.values():
            if i in indexes:
                indexes.remove(i)

        if not args:
            index1, index2 = indexes[0], indexes[1]
        else:
            index1, index2 = args

        if press_item:
            self.on_tree_clipping_item_pressed(item, 0)
        self.set_editor_note(self.clipping_item_clipping, index1)
        self.set_editor_note(self.clipping_item_remark, index2)
        self._fill_book_field(self.clipping_item_book, self.clipping_item_author)

    def on_remark_triggered(self, fld, clicked):
        self.set_editor_note(self.clipping_item_remark, fld)

    def on_clipping_triggered(self, fld, clicked):
        self.set_editor_note(self.clipping_item_clipping, fld)

    def set_editor_note(self, text, index=0):
        editor = self.add_card.editor
        editor.note.fields[index] = text
        editor.setNote(editor.note)

    def set_editor_note_tags(self, book, author):
        tags = self._get_tags_tobe_set(book, author)

        editor = self.add_card.editor
        editor.tags.setText(
            six.ensure_text(" ".join(tags))
        )
        editor.updateTags()

    def _get_tags_tobe_set(self, book, author):
        if not Cnf.ankindle_clipping_set_tags:
            return []
        set_ankindle_tag, set_book, set_author = Cnf.ankindle_clipping_set_tags

        tags = []
        if set_ankindle_tag:
            tags.append(_trans("AnKindle"))
        if set_book:
            tags.append(six.ensure_text(book))
        if set_author:
            tags.append(six.ensure_text(author))
        return u" ".join([u"{}".format(t.replace(u" ", u"_")) for t in tags if t]).split(" ")

    def _fill_book_field(self, book_name, author):
        book_index = self._auto_fil_indexes['BOOK']
        author_index = self._auto_fil_indexes['AUTHOR']
        if book_index is not None:
            self.set_editor_note(book_name, book_index)
        if author_index is not None:
            self.set_editor_note(author, author_index)
        self.set_editor_note_tags(book_name, author)

    @property
    def note(self):
        return self.add_card.editor.note

    @property
    def note_fld_names(self):
        return self.note.model()['flds']

    @property
    def cur_item_type(self):
        """
        1 - Book, 2 - Clipping
        :rtype: int
        """
        if self.tree_contents.selectedItems().__len__() > 1:
            return 3
        if self.cur_item.childCount():
            return 1
        else:
            return 2

    @property
    def cur_item(self):
        """

        :rtype: QTreeWidgetItem
        """
        try:
            return self.tree_contents.currentItem()
        except RuntimeError:
            return None

    @property
    def cur_items(self):
        if self.cur_item_type == 1:
            return [self.cur_item.child(i) for i in range(self.cur_item.childCount())]
        elif self.cur_item_type == 2:
            return [self.cur_item, ]
        else:
            return self.tree_contents.selectedItems()

    @property
    def _auto_fil_indexes(self):
        note = self.note
        auto_fill_indx_names = ["BOOK", "AUTHOR"]
        indexes = dict.fromkeys(auto_fill_indx_names)
        for i, auto_fill_index_name in enumerate(auto_fill_indx_names):
            if auto_fill_index_name in [k.upper().strip() for k in note._fmap.keys()]:
                for index, fld_dict in enumerate(self.note_fld_names):
                    if fld_dict["name"].upper().strip() != auto_fill_index_name:
                        continue
                    indexes[auto_fill_index_name] = index
        return indexes

    def bind_slots(self):
        _bind_qt_slots(self.btn_select_file.clicked, self.on_select_file_clicked)
        _bind_qt_slots(self.tree_contents.customContextMenuRequested, self.on_tree_context_menu)
        _bind_qt_slots(self.btn_change_status.toggled, self.on_btn_status_checked)
        # _bind_qt_slots(self.btn_preview.toggled, self.on_btn_preview_checked)
        _bind_qt_slots(self.tree_contents.itemPressed, self.on_tree_clipping_item_pressed)
        _bind_qt_slots(self.tree_contents.itemDoubleClicked, self.on_tree_clipping_item_double_clicked)
        _bind_qt_slots(self.tree_contents.currentItemChanged, self.on_tree_clipping_item_changed)

        # context menu actions
        # _bind_qt_slots(self.tree_context_menu.action_auto_fill.triggered, self.on_clipping_autofill_triggered)
        _bind_qt_slots(self.tree_context_menu.action_mark_complete.triggered, self.on_mark_complete_triggered)

        # buttons
        _bind_qt_slots(self.btn_setting.clicked, self.on_setting_clicked)

    def try_clippings(self, fpath=None, from_user_click=False):
        # region Try Clippiings.txt
        # find My Clippings.txt
        if from_user_click:
            pass
        else:
            if Config.last_used_clips_path and (not fpath):
                fpath = Config.last_used_clips_path

        def _user_click_unavailable():
            self.hide()
            self.btn_start.show()
            showInfo(_trans("MY CLIPPINGS NOT AVAILABLE"), self, title=_trans("ANKINDLE"))
            Config.last_used_clips_path = ''
            self.btn_select_file.setToolTip("")
            self.tree_contents.clear()

        if not fpath:
            if from_user_click:
                _user_click_unavailable()
                return
            else:
                btns = [
                    self.btn_change_status
                ]
                for btn in btns:
                    btn.setEnabled(False)
                else:
                    showInfo(_trans("SELECT MY CLIPPINGS TXT"), self, title=_trans("ANKINDLE"))
            Config.last_used_clips_path = ''
            self.tree_contents.clear()
            self.btn_select_file.setToolTip("")
            return
        # endregion

        list(map(lambda c: c.setEnabled(True), self._btns))
        if not fpath:
            if from_user_click:
                _user_click_unavailable()
                return
            else:
                fpath = os.path.join(plus_api().get_kindle_path(), "documents", "My Clippings.txt")
        try:
            plus_api().set_clippings_txt(fpath)
            self.btn_select_file.setToolTip(fpath)
        except Exception as exc:
            showInfo(_trans("SELECT MY CLIPPINGS TXT"), self, title=_trans("ANKINDLE"))
            return
        Config.last_used_clips_path = fpath
        return True

    def load_clippings(self, completed=False):
        self.tree_contents.clear()

        incomplete_contents = plus_api().get_clippings(completed)
        header_item = self.tree_contents.headerItem()
        header_item.setText(0, u"{} ({})".format(_trans("CLIPPING"),
                                                 _trans("COMPLETED CLIPPINGS")
                                                 if self.completed_status
                                                 else _trans("INCOMPLETE CLIPPINGS")))
        header_item.setText(1, _trans("REMARK"))
        # Group by Book
        book_font = QFont()
        book_font.setBold(True)
        extract_author_re = "(.+).+\((.+)?\)$"

        for book_name, book_contents in groupby(sorted(incomplete_contents,
                                                       key=itemgetter(1)),
                                                itemgetter(1)):
            author = ""
            match = re.match(extract_author_re, book_name)
            if match:
                book_name, author = match.groups()

            book_item = QTreeWidgetItem(self.tree_contents)
            book_item.setText(0, book_name)
            book_item.setFont(0, book_font)
            self.tree_contents.addTopLevelItem(book_item)
            for id_, book_name_, contents, comment in book_contents:
                content_item = QTreeWidgetItem(book_item)
                content_item.setText(0, contents)
                content_item.setText(1, comment if comment else "")
                content_item.setText(2, str(id_))
                content_item.setText(3, six.ensure_text(author))
                toolTip = u"{}{}".format(contents, u"\n=========\n{}".format(comment) if
                comment else u"")
                content_item.setToolTip(0, toolTip.strip())
                if comment:
                    content_item.setIcon(0, QIcon(_png("note.png")))
                if "(Upgrade to Plush ...)" in contents:
                    content_item.setIcon(0, QIcon(_png("lock.png")))
                book_item.addChild(content_item)
        self.tree_contents.hideColumn(1)
        self.tree_contents.expandAll()

    def on_setting_clicked(self, clicked):
        ConfigDialog(self.parent()).exec_()

    def on_select_file_clicked(self, clicked):
        fpath = getFile(mw, _trans("SHOW CLIPPING IMPORT"),
                        lambda x: x, ("Kindle Clippings (*.txt)"),
                        os.path.dirname(
                            Config.last_used_clips_path if
                            os.path.isdir(os.path.dirname(Config.last_used_clips_path))
                            else __file__))
        if self.try_clippings(fpath, True):
            self.load_clippings(self.completed_status)


class ConfigDialog(QDialog):
    def __init__(self, parent):
        super(ConfigDialog, self).__init__(parent)

        self.setWindowTitle(_trans("CONFIGURATION"))
        self.setWindowIcon(QIcon(_png("setting.png")))

        self.setMaximumHeight(300)
        self.setMinimumWidth(300)

        # General settings
        self.ck_complete_after_add_card = QCheckBox(_trans("COMPLETE AFTER ADD CARD"), self)

        self.grp_general = QGroupBox(_trans("GENERAL"), self)
        self.l_grp_general = QGridLayout(self.grp_general)
        self.l_grp_general.addWidget(self.ck_complete_after_add_card, 0, 0)
        _bind_qt_slots(self.ck_complete_after_add_card.clicked, self.on_complete_after_add_card_clicked)

        # group tags setting
        self.grp_tags = QGroupBox(_trans("QUICK FILL TAGS"))
        self.ck_ankindle_clippings = QCheckBox(_trans("AnKindle"), self)
        self.ck_book = QCheckBox(_trans("BOOK"), self)
        self.ck_author = QCheckBox(_trans("AUTHOR"), self)
        _bind_qt_slots(self.ck_ankindle_clippings.clicked, self.update_tag_setting)
        _bind_qt_slots(self.ck_book.clicked, self.update_tag_setting)
        _bind_qt_slots(self.ck_author.clicked, self.update_tag_setting)
        l_tags = QVBoxLayout()
        l_tags.addWidget(self.ck_ankindle_clippings)
        l_tags.addWidget(self.ck_book)
        l_tags.addWidget(self.ck_author)
        l_tags.addSpacerItem(QSpacerItem(10, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        self.grp_tags.setLayout(l_tags)

        # auto fill profile setting
        self.grp_profiles = QGroupBox(_trans("ADD QUICK SET MENU"))
        self.btn_add_new_profile = QPushButton("+", self)
        self.btn_rmv_profile = QPushButton("-", self)
        self.btn_add_new_profile.setFixedSize(QSize(30, 30))
        self.btn_rmv_profile.setFixedSize(QSize(30, 30))
        self.list_profiles = QListWidget(self)
        _bind_qt_slots(self.list_profiles.itemDoubleClicked, self.on_profile_double_clicked)

        # bind_slots
        _bind_qt_slots(self.btn_add_new_profile.clicked, self.on_add_profile_clicked)
        _bind_qt_slots(self.btn_rmv_profile.clicked, self.on_remove_profile_clicked)

        # layouts
        self.profile_layout = QHBoxLayout()
        l = QVBoxLayout()
        l.addWidget(self.btn_add_new_profile)
        l.addWidget(self.btn_rmv_profile)
        l.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        self.profile_layout.addItem(l)
        self.profile_layout.addWidget(self.list_profiles)
        l.setSpacing(20)

        self.l = QVBoxLayout()
        self.profile_layout.setSpacing(20)

        self.l.setSpacing(1)
        self.grp_profiles.setLayout(self.profile_layout)

        self.l.addWidget(self.grp_general)
        l_other_settings = QHBoxLayout()
        l_other_settings.addWidget(self.grp_tags)
        l_other_settings.addWidget(self.grp_profiles)
        self.l.addItem(l_other_settings)

        self.setLayout(self.l)

        self.init_values()

    def init_values(self):
        self.load_profiles()

        set_ankindle_tag, set_book, set_author = Cnf.ankindle_clipping_set_tags
        self.ck_ankindle_clippings.setChecked(set_ankindle_tag)
        self.ck_book.setChecked(set_book)
        self.ck_author.setChecked(set_author)
        self.ck_complete_after_add_card.setChecked(Cnf.mark_complete_aft_add_card)

    def on_complete_after_add_card_clicked(self, checked):
        Cnf.mark_complete_aft_add_card = self.ck_complete_after_add_card.isChecked()

    def update_tag_setting(self, checked):
        Cnf.ankindle_clipping_set_tags = (
            self.ck_ankindle_clippings.isChecked(),
            self.ck_book.isChecked(),
            self.ck_author.isChecked()
        )

    def load_profiles(self):
        self.list_profiles.clear()
        profile_names = [k for k in Cnf.user_note_map.keys() if k.strip()]
        self.list_profiles.addItems(profile_names)

    def on_profile_double_clicked(self, item):
        profile_name = item.text()
        profile_dict = Cnf.user_note_map.get(profile_name, {})
        dlg = AddProfileDialog(self, profile_dict)
        dlg.edit_profile_name.setText(profile_name)
        if dlg.exec_():
            self.update_profile(dlg, profile_name)

    def on_add_profile_clicked(self, clicked):
        dlg = AddProfileDialog(self)
        if dlg.exec_():
            self.update_profile(dlg)

    def update_profile(self, dlg, old_profile_name=''):
        profiles = Cnf.user_note_map
        (current_profile_name, mid,
         clipping_fld, remark_fld, did, auto_save, auto_complete) = (dlg.edit_profile_name.text(),
                                                                     dlg.mid,
                                                                     dlg.combo_clipping_fld_name.currentIndex(),
                                                                     dlg.combo_remark_fld_name.currentIndex(),
                                                                     dlg.did,
                                                                     dlg.ck_auto_save.isChecked(),
                                                                     dlg.ck_auto_complete.isChecked(),
                                                                     )
        if old_profile_name and current_profile_name != old_profile_name:
            profiles.pop(old_profile_name)
        _current_profile = {mid: (clipping_fld, remark_fld, did, auto_save, auto_complete)}
        profiles[current_profile_name] = _current_profile
        Cnf.user_note_map = profiles
        self.load_profiles()

    def on_remove_profile_clicked(self, clicked):
        item = self.list_profiles.currentItem()
        if item:
            profiles = Cnf.user_note_map
            profiles.pop(item.text())
            Cnf.user_note_map = profiles
            self.load_profiles()


def GetMDXConfig(lang):
    _ = Cnf.mdx_files.get(lang, ['', '', '', '', ''])
#     if not plus_api().is_unlocked():
#         return [_[0], '', '', '', '']
    return _


class MDXDialog(QDialog):
    _last_selected_directory = ''

    def __init__(self, parent, lang):
        super(MDXDialog, self).__init__(parent)
        self.setWindowTitle(_trans("USE MDX"))
        # self.setMaximumWidth(300)
        # self.setMinimumWidth(300)
        self.lang = lang

        mdx1, mdx2, mdx3, mdx4, mdx5 = GetMDXConfig(self.lang)

        self._btn1 = QPushButton(self._get_mdx_btn_text(mdx1) if mdx1 else _trans("SELECT MDX"), self)
        self._btn2 = QPushButton(self._get_mdx_btn_text(mdx2) if mdx2 else _trans("SELECT MDX"), self)
        self._btn3 = QPushButton(self._get_mdx_btn_text(mdx3) if mdx3 else _trans("SELECT MDX"), self)
        self._btn4 = QPushButton(self._get_mdx_btn_text(mdx4) if mdx4 else _trans("SELECT MDX"), self)
        self._btn5 = QPushButton(self._get_mdx_btn_text(mdx5) if mdx5 else _trans("SELECT MDX"), self)

        self.lbl = QLabel(_trans("USE MDX LABEL"), self)
        self.lbl.setWordWrap(True)

        _bind_qt_slots(self._btn1.clicked, self.on_btn1_clicked)
        _bind_qt_slots(self._btn2.clicked, self.on_btn2_clicked)
        _bind_qt_slots(self._btn3.clicked, self.on_btn3_clicked)
        _bind_qt_slots(self._btn4.clicked, self.on_btn4_clicked)
        _bind_qt_slots(self._btn5.clicked, self.on_btn5_clicked)

        self.l = QVBoxLayout(self)
        self.l.addWidget(self._btn1)
        self.l.addWidget(self._btn2)
        self.l.addWidget(self._btn3)
        self.l.addWidget(self._btn4)
        self.l.addWidget(self._btn5)

        self.l.addWidget(kkLib.HLine())
        self.l.addWidget(self.lbl)
        self.l.setSpacing(10)
        self.adjustSize()

    def _get_mdx_btn_text(self, mdx_file):
        return u'[ %s ]' % (six.ensure_text(os.path.splitext(os.path.basename(mdx_file))[0]))

    def _suggest_purchase(self):
#         if not plus_api().is_unlocked():
#             call_purchase_dialog(self.parent(), type_=3)
#             return False
        return True

    def on_btn1_clicked(self, clicked):
        self.get_file(self._btn1)

    def on_btn2_clicked(self, clicked):
        self.get_file(self._btn2)

    def on_btn3_clicked(self, clicked):
#         if self._suggest_purchase():
        self.get_file(self._btn3)

    def on_btn4_clicked(self, clicked):
#         if self._suggest_purchase():
        self.get_file(self._btn4)

    def on_btn5_clicked(self, clicked):
#         if self._suggest_purchase():
        self.get_file(self._btn5)

    def get_file(self, btn):
        mdx_file = getFile(self, _trans("MDX TYPE"), lambda x: x, ("MDict (*.MDX)"),
                           os.path.join(os.path.dirname(__file__),
                                        u"resource") if not MDXDialog._last_selected_directory
                           else os.path.dirname(MDXDialog._last_selected_directory)
                           )
        if mdx_file:
            if isinstance(mdx_file, six.string_types) and not os.path.isfile(mdx_file):
                mdx_file = ''
        else:
            mdx_file = ''

        MDXDialog._last_selected_directory = os.path.dirname(mdx_file)
        btn.setText(self._get_mdx_btn_text(mdx_file) if mdx_file else _trans("SELECT MDX"))

        mdx_files = GetMDXConfig(self.lang)

        if btn is self._btn1:
            mdx_files[0] = mdx_file
        if btn is self._btn2:
            mdx_files[1] = mdx_file
        if btn is self._btn3:
            mdx_files[2] = mdx_file
        if btn is self._btn4:
            mdx_files[3] = mdx_file
        if btn is self._btn5:
            mdx_files[4] = mdx_file

        _ = Cnf.mdx_files
        _[self.lang] = mdx_files
        Cnf.mdx_files = _


class AddProfileDialog(QDialog):
    def __init__(self, parent, profile_dict={}):
        super(AddProfileDialog, self).__init__(parent)
        self.setWindowTitle(_trans("ADD QUICK SET MENU"))

        self.profile_dict = profile_dict

        self.btn_ok = QPushButton(_("OK"), self)
        _bind_qt_slots(self.btn_ok.clicked, self.on_btn_ok_clicked)

        # region Quick Menu Setting
        self.ck_auto_save = QCheckBox(_trans("AUTO SAVE CARD"), self)
        self.ck_auto_complete = QCheckBox(_trans("AUTO COMPLETE CLIPPING"), self)
        self.combo_notes = QComboBox(self)
        self.combo_decks = QComboBox(self)
        self.edit_profile_name = QLineEdit(self)
        self.combo_clipping_fld_name = QComboBox(self)
        self.combo_remark_fld_name = QComboBox(self)

        self.lb_profile_name = QLabel(_trans("QUICK MENU NAME"), self)
        self.lb_note_type = QLabel(_("Note Types"), self)
        self.lb_deck = QLabel(_("Decks"), self)
        self.lb_clipping = QLabel(_trans("CLIPPING") + u" >>", self)
        self.lb_remark = QLabel(_trans("REMARK") + u" >>", self)

        l_profile_labels = QVBoxLayout()
        l_profile_labels.addWidget(self.lb_profile_name)
        l_profile_labels.addWidget(self.lb_note_type)
        l_profile_labels.addWidget(self.lb_deck)
        l_profile_labels.addWidget(self.lb_clipping)
        l_profile_labels.addWidget(self.lb_remark)
        l_profile_labels.addSpacerItem(QSpacerItem(100, 2, QSizePolicy.Preferred, QSizePolicy.Minimum))

        l_profile_controls = QVBoxLayout()
        l_profile_controls.addWidget(self.edit_profile_name)
        l_profile_controls.addWidget(self.combo_notes)
        l_profile_controls.addWidget(self.combo_decks)
        l_profile_controls.addWidget(kkLib.HLine())
        l_profile_controls.addWidget(self.combo_clipping_fld_name)
        l_profile_controls.addWidget(self.combo_remark_fld_name)

        l_auto_save_controls = QHBoxLayout()
        l_auto_save_controls.addWidget(self.ck_auto_save)
        l_auto_save_controls.addWidget(self.ck_auto_complete)

        profile_layout = QHBoxLayout()
        profile_layout.addItem(l_profile_labels)
        profile_layout.addItem(l_profile_controls)
        for l_ in [profile_layout, l_profile_labels, l_profile_controls]:
            l_.setSpacing(20)
        # endregion

        l5_ok_btn = QHBoxLayout()
        l5_ok_btn.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        l5_ok_btn.addWidget(self.btn_ok)

        l = QVBoxLayout(self)
        l.addItem(profile_layout)
        l.addItem(l_auto_save_controls)
        l.addItem(l5_ok_btn)

        self.model = None
        self.mid = ''
        self.did = ''
        self.init_values()

    def init_values(self):
        self.combo_notes.clear()
        self.combo_notes.addItems(sorted(self.model_dict.keys()))

        self.combo_decks.clear()
        self.combo_decks.addItems(sorted(self.deck_dict.keys()))

        _bind_qt_slots(self.combo_notes.currentIndexChanged, self.on_note_changed)
        _bind_qt_slots(self.combo_decks.currentIndexChanged, self.on_deck_changed)

        self.on_note_changed(self.combo_notes.currentIndex())
        self.on_deck_changed(self.combo_decks.currentIndex())

        auto_save = False
        auto_complete = False
        if self.profile_dict:
            try:
                mid, (clipping_fld, remark_fld, did, auto_save, auto_complete) = list(self.profile_dict.items())[0]
            except:
                mid, (clipping_fld, remark_fld, did,) = list(self.profile_dict.items())[0]
            if mid in self.model_dict.values():
                self.combo_notes.setCurrentIndex(
                    self.combo_notes.findText({v: k for k, v in self.model_dict.items()}[mid])
                )
            else:
                self.combo_notes.setCurrentIndex(-1)

            if did in self.deck_dict.values():
                self.combo_decks.setCurrentIndex(
                    self.combo_decks.findText({v: k for k, v in self.deck_dict.items()}[did])
                )
            else:
                self.combo_decks.setCurrentIndex(-1)

            try:
                self.combo_clipping_fld_name.setCurrentIndex(clipping_fld)
            except:
                self.combo_clipping_fld_name.setCurrentIndex(-1)
            try:
                self.combo_remark_fld_name.setCurrentIndex(remark_fld)
            except:
                self.combo_remark_fld_name.setCurrentIndex(-1)

        _bind_qt_slots(self.ck_auto_save.clicked, self.on_ck_auto_save_clicked)

        self.ck_auto_complete.setChecked(auto_complete)
        self.ck_auto_save.setChecked(auto_save)
        self.on_ck_auto_save_clicked(False)

    def on_ck_auto_save_clicked(self, clicked):
        if not self.ck_auto_save.isChecked():
            self.ck_auto_complete.setEnabled(False)
            self.ck_auto_complete.setChecked(False)
        else:
            self.ck_auto_complete.setEnabled(True)

    def on_btn_ok_clicked(self, clicked):
        self.accept()

    def on_deck_changed(self, index):
        deck_name = self.combo_decks.itemText(index)
        self.did = self.deck_dict.get(deck_name)

    def on_note_changed(self, index):
        current_note_name = self.combo_notes.itemText(index)
        mid = self.model_dict.get(current_note_name)
        self.combo_clipping_fld_name.clear()
        self.combo_remark_fld_name.clear()
        if not mid:
            return
        self.mid = mid
        self.model = mw.col.models.get(mid)
        flds = [f['name'] for f in mw.col.models.get(mid)['flds']]
        self.combo_clipping_fld_name.addItems(flds)
        self.combo_remark_fld_name.addItems(flds)

    @property
    def decks(self):
        return mw.col.decks.decks

    @property
    def deck_dict(self):
        return {v['name']: int(k) for k, v in self.decks.items()}

    @property
    def models(self):
        return mw.col.models.models

    @property
    def model_dict(self):
        return {v['name']: k for k, v in self.models.items()}

    def accept(self):
        if not all([self.edit_profile_name.text(), ]):
            showCritical(_trans("INVALID QUICK MENU SETTING"), self, title=_trans("ADD QUICK SET MENU"))
            return
        return super(AddProfileDialog, self).accept()


# endregion

# region Plus-Configuration

@six.add_metaclass(kkLib.MetaConfigObj)
class Cnf:
    class Meta:
        __store_location__ = kkLib.MetaConfigObj.StoreLocation.Profile

    # other config
    is_ankindle_plus_first_run = True

    # plus config
    ankindle_clipping_set_tags = (True, True, True)  # set_ankindle_tag, set_book,set_author
    user_note_map = {}  # {profile_name: {mid: (clipping_fld,remark_fld)}}

    mark_complete_aft_add_card = False

    mdx_files = {"": []}


# endregion

# region verify sn

def get_trans(key, trans_map, lang=currentLang):
    """

    :param key:
    :param trans_map: {'ANKINDLE': {'zh_CN': u'AnKindle', 'en': u'AnKindle'},}
    :param lang:
    :return:
    """
    key = key.upper().strip()
    if lang != 'zh_CN' and lang != 'en' and lang != 'fr':
        lang = 'en'  # fallback

    if key not in trans_map or lang not in trans_map[key]:
        return key.capitalize()
    return trans_map[key][lang]


@six.add_metaclass(kkLib.MetaConfigObj)
class RegisterConf:
    class Meta:
        __store_location__ = kkLib.MetaConfigObj.StoreLocation.Profile

    kk_sn_dict = {}


# noinspection PyStatementEffect,PyBroadException
class SNRegDialog(QDialog):
    _Unlocked = None

    def _(self, key):
        return self.get_trans(key, self.trans, currentLang)

    def __init__(self, parent, addon, ):
        super(SNRegDialog, self).__init__(parent, )

        self.api = plus_api()
        self.register = self.api.register
        self.get_trans = self.api.get_trans
        self.trans = self.api.trans()
        self.status = {int(k): v for k, v in self.api.status().items()}
        self.user_acks = self.api.get_user_acks()
        self.is_network_available = lambda: True

        self.setWindowTitle(self._("REGISTER"))
        self.setWindowFlags(Qt.Dialog)

        self.user_email = mw.pm.profile.get('syncUser', '')
        self.addon = addon

        # group user notes
        self.grp_user_notes = QGroupBox(self._("USER ACK"))
        self.cks_user_ack = []
        for i, k in enumerate(self.user_acks):
            ck = QCheckBox(self._(k), self, )
            self.cks_user_ack.append(ck)
        l_user_ack = QVBoxLayout()
        for i, ck in enumerate(self.cks_user_ack):
            l_user_ack.addWidget(ck)
            if not i:
                ck.setEnabled(True)
            _bind_qt_slots(ck.clicked, self.enable_next)
        self.grp_user_notes.setLayout(l_user_ack)

        # group edits
        l_grp_edits = QHBoxLayout()
        self.grp_edits = QGroupBox(self._("ENTER CODE"))
        self.lb_eml = QLabel(self._("ANKI EMAIL"), self)
        self.lb_sn = QLabel(self._("SN"), self)
        lb_l = QVBoxLayout()
        lb_l.addWidget(self.lb_eml)
        lb_l.addWidget(self.lb_sn)

        self.edit_eml = QLineEdit(self.user_email, self)
        self.edit_eml.setEnabled(False)
        self.edit_sn = QLineEdit(self)
        edit_l = QVBoxLayout()
        edit_l.setSpacing(20)
        edit_l.addWidget(self.edit_eml)
        edit_l.addWidget(self.edit_sn)
        l_grp_edits.addItem(lb_l)
        l_grp_edits.addItem(edit_l)
        self.grp_edits.setLayout(l_grp_edits)

        # next btn
        self.btn_confirm = QPushButton(self._("CONFIRM"))
        self.btn_confirm.setVisible(False)
        _bind_qt_slots(self.btn_confirm.clicked, self.confirm_clicked)

        # overall layout
        l = QVBoxLayout()
        l.addWidget(self.grp_edits)
        l.addWidget(self.grp_user_notes)
        l.addWidget(self.btn_confirm)

        self.setLayout(l)

    def exec_(self):
        self.edit_eml.setText(self.user_email)
        self.edit_sn.setText(self.edit_sn.text())
        return super(SNRegDialog, self).exec_()

    def enable_next(self, checked):
        self.btn_confirm.setVisible(all([ck.isChecked() for ck in self.cks_user_ack]))

    def confirm_clicked(self, clicked):
        if not self.edit_eml.text():
            showInfo(self._("REGISTER ANKI"), self, self._("REGISTER"))
            return
        if not self.is_network_available():
            showWarning(self._("NETWORK UNAVAILABLE"), self, self._("REGISTER"))
            return
        # re-confirm
        reconfirm_msg = self._("RE-CONFIRM ACK") % (self.user_email,
                                                    self.edit_sn.text(),
                                                    "\n".join([u"{}. {}".format(i, self._(k)) for i, k in
                                                               enumerate(self.user_acks, 1)]),)
        if askUser(reconfirm_msg, self):
            status_cd, msg = self.register(self.edit_sn.text().strip().upper(), self.user_email, self.addon)
            if status_cd >= 90:
                showWarning(msg, self, title=self._("REGISTER"))
            if status_cd >= 10:
                showInfo(msg, self, title=self._("REGISTER"))
            if status_cd == 99:
                showCritical(msg, self, title=self._("REGISTER"))
            if status_cd in (11, 21):  # bind successfully
                reg_dict = RegisterConf.kk_sn_dict
                reg_dict[self.addon] = self.edit_sn.text()
                RegisterConf.kk_sn_dict = reg_dict
                self.accept()
                showInfo(self._("RESTART ALERT"), mw, )

# endregion
