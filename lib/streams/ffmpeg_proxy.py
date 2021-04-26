"""
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the “Software”), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

from lib.tvheadend.templates import tvh_templates
from .stream import Stream


class FFMpegProxy(Stream):

    def gen_response(self, _ch_num, _tuner):
        """
        Returns dict where the dict is consistent with
        the method do_dict_response requires as an argument
        A code other than 200 means do not tune
        dict also include a "tuner_index" that informs caller what tuner is allocated
        """
        index = self.find_tuner(_ch_num, _tuner)
        if index >= 0:
            return {
                'tuner': index,
                'code': 200,
                'headers': {'Content-type': 'video/mp2t; Transfer-Encoding: chunked codecs="avc1.4D401E'},
                'text': None}
        else:
            self.logger.warning('All tuners already in use')
            return {
                'tuner': index,
                'code': 400,
                'headers': {'Content-type': 'text/html'},
                'text': tvh_templates['htmlError'].format('400 - All tuners already in use.')}
