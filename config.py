# -*- coding: utf-8 -*-
# Created: 3/27/2018
# Project : AnKindle

# from anki.sync import os
import os
from .kkLib import MetaConfigObj
from .libs import six

path_join = os.path.join


@six.add_metaclass(MetaConfigObj)
class Config:
    class Meta:
        __store_location__ = MetaConfigObj.StoreLocation.Profile

    mdx_kindle_model_id = u''  # todo invalid
    mdx_kindle_deck_id = u''  # todo invalid
    mdx_kindle_mdx_path = u''  # todo invalid

    mdx_kindle_mdx_path_dict = {}  # todo lang_cd : mdx_path # invalid

    lang_config = {

    }  # lang_cd: {"mdx_kindle_model_id":u"","mdx_kindle_deck_id":u"","mdx_kindle_mdx_path":u"",}

    last_used_lang = u""
    last_used_db_path = u""
    last_used_clips_path = u""

    mdx_kindle_first_run = False
