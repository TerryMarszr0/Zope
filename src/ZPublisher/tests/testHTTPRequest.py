import base64
from io import BytesIO
import sys
import unittest

from zExceptions import NotFound
from zope.component import provideAdapter
from zope.i18n.interfaces import IUserPreferredLanguages
from zope.i18n.interfaces.locales import ILocale
from zope.publisher.browser import BrowserLanguages
from zope.publisher.interfaces.http import IHTTPRequest
from zope.testing.cleanup import cleanUp

from ZPublisher.tests.testBaseRequest import TestRequestViewsBase

if sys.version_info >= (3, ):
    unicode = str


class RecordTests(unittest.TestCase):

    def test_repr(self):
        from ZPublisher.HTTPRequest import record
        rec = record()
        rec.a = 1
        rec.b = 'foo'
        r = repr(rec)
        d = eval(r)
        self.assertEqual(d, rec.__dict__)


class HTTPRequestFactoryMixin(object):

    def tearDown(self):
        cleanUp()

    def _getTargetClass(self):
        from ZPublisher.HTTPRequest import HTTPRequest
        return HTTPRequest

    def _makeOne(self, stdin=None, environ=None, response=None, clean=1):
        from ZPublisher.HTTPResponse import HTTPResponse
        if stdin is None:
            stdin = BytesIO()

        if environ is None:
            environ = {}

        if 'REQUEST_METHOD' not in environ:
            environ['REQUEST_METHOD'] = 'GET'

        if 'SERVER_NAME' not in environ:
            environ['SERVER_NAME'] = 'http://localhost'

        if 'SERVER_PORT' not in environ:
            environ['SERVER_PORT'] = '8080'

        if response is None:
            response = HTTPResponse(stdout=BytesIO())

        return self._getTargetClass()(stdin, environ, response, clean)


class HTTPRequestTests(unittest.TestCase, HTTPRequestFactoryMixin):

    def _processInputs(self, inputs):
        from six.moves.urllib.parse import quote_plus
        # Have the inputs processed, and return a HTTPRequest object
        # holding the result.
        # inputs is expected to be a list of (key, value) tuples, no CGI
        # encoding is required.

        query_string = []
        add = query_string.append
        for key, val in inputs:
            add("%s=%s" % (quote_plus(key), quote_plus(val)))
        query_string = '&'.join(query_string)

        env = {'SERVER_NAME': 'testingharnas', 'SERVER_PORT': '80'}
        env['QUERY_STRING'] = query_string
        req = self._makeOne(environ=env)
        req.processInputs()
        self._noFormValuesInOther(req)
        return req

    def _noTaintedValues(self, req):
        self.assertFalse(list(req.taintedform.keys()))

    def _valueIsOrHoldsTainted(self, val):
        # Recursively searches a structure for a TaintedString and returns 1
        # when one is found.
        # Also raises an Assertion if a string which *should* have been
        # tainted is found, or when a tainted string is not deemed dangerous.
        from ZPublisher.HTTPRequest import record
        from AccessControl.tainted import TaintedString

        retval = 0

        if isinstance(val, TaintedString):
            self.assertFalse(
                '<' not in val,
                "%r is not dangerous, no taint required." % val)
            retval = 1

        elif isinstance(val, record):
            for attr, value in list(val.__dict__.items()):
                rval = self._valueIsOrHoldsTainted(attr)
                if rval:
                    retval = 1
                rval = self._valueIsOrHoldsTainted(value)
                if rval:
                    retval = 1

        elif type(val) in (list, tuple):
            for entry in val:
                rval = self._valueIsOrHoldsTainted(entry)
                if rval:
                    retval = 1

        elif type(val) in (str, unicode):
            self.assertFalse(
                '<' in val,
                "'%s' is dangerous and should have been tainted." % val)

        return retval

    def _noFormValuesInOther(self, req):
        for key in list(req.taintedform.keys()):
            self.assertFalse(
                key in req.other,
                'REQUEST.other should not hold tainted values at first!')

        for key in list(req.form.keys()):
            self.assertFalse(
                key in req.other,
                'REQUEST.other should not hold form values at first!')

    def _onlyTaintedformHoldsTaintedStrings(self, req):
        for key, val in list(req.taintedform.items()):
            self.assertTrue(
                self._valueIsOrHoldsTainted(key) or
                self._valueIsOrHoldsTainted(val),
                'Tainted form holds item %s that is not tainted' % key)

        for key, val in list(req.form.items()):
            if key in req.taintedform:
                continue
            self.assertFalse(
                self._valueIsOrHoldsTainted(key) or
                self._valueIsOrHoldsTainted(val),
                'Normal form holds item %s that is tainted' % key)

    def _taintedKeysAlsoInForm(self, req):
        for key in list(req.taintedform.keys()):
            self.assertTrue(
                key in req.form,
                "Found tainted %s not in form" % key)
            self.assertEqual(
                req.form[key], req.taintedform[key],
                "Key %s not correctly reproduced in tainted; expected %r, "
                "got %r" % (key, req.form[key], req.taintedform[key]))

    def test_no_docstring_on_instance(self):
        env = {'SERVER_NAME': 'testingharnas', 'SERVER_PORT': '80'}
        req = self._makeOne(environ=env)
        self.assertTrue(req.__doc__ is None)

    def test___bobo_traverse___raises(self):
        env = {'SERVER_NAME': 'testingharnas', 'SERVER_PORT': '80'}
        req = self._makeOne(environ=env)
        self.assertRaises(KeyError, req.__bobo_traverse__, 'REQUEST')
        self.assertRaises(KeyError, req.__bobo_traverse__, 'BODY')
        self.assertRaises(KeyError, req.__bobo_traverse__, 'BODYFILE')
        self.assertRaises(KeyError, req.__bobo_traverse__, 'RESPONSE')

    def test_processInputs_wo_query_string(self):
        env = {'SERVER_NAME': 'testingharnas', 'SERVER_PORT': '80'}
        req = self._makeOne(environ=env)
        req.processInputs()
        self._noFormValuesInOther(req)
        self.assertEqual(req.form, {})

    def test_processInputs_wo_marshalling(self):
        inputs = (
            ('foo', 'bar'), ('spam', 'eggs'),
            ('number', '1'),
            ('spacey key', 'val'), ('key', 'spacey val'),
            ('multi', '1'), ('multi', '2'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(
            formkeys,
            ['foo', 'key', 'multi', 'number', 'spacey key', 'spam'])
        self.assertEqual(req['number'], '1')
        self.assertEqual(req['multi'], ['1', '2'])
        self.assertEqual(req['spacey key'], 'val')
        self.assertEqual(req['key'], 'spacey val')

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_simple_marshalling(self):
        from DateTime.DateTime import DateTime
        inputs = (
            ('num:int', '42'), ('fract:float', '4.2'), ('bign:long', '45'),
            ('words:string', 'Some words'), ('2tokens:tokens', 'one two'),
            ('aday:date', '2002/07/23'),
            ('accountedfor:required', 'yes'),
            ('multiline:lines', 'one\ntwo'),
            ('morewords:text', 'one\ntwo\n'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(
            formkeys,
            ['2tokens', 'accountedfor', 'aday', 'bign',
             'fract', 'morewords', 'multiline', 'num', 'words'])

        self.assertEqual(req['2tokens'], ['one', 'two'])
        self.assertEqual(req['accountedfor'], 'yes')
        self.assertEqual(req['aday'], DateTime('2002/07/23'))
        self.assertEqual(req['bign'], 45)
        self.assertEqual(req['fract'], 4.2)
        self.assertEqual(req['morewords'], 'one\ntwo\n')
        self.assertEqual(req['multiline'], ['one', 'two'])
        self.assertEqual(req['num'], 42)
        self.assertEqual(req['words'], 'Some words')

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_unicode_conversions(self):
        inputs = (('ustring:ustring:utf8', 'test\xc2\xae'),
                  ('utext:utext:utf8', 'test\xc2\xae\ntest\xc2\xae\n'),
                  ('utokens:utokens:utf8', 'test\xc2\xae test\xc2\xae'),
                  ('ulines:ulines:utf8', 'test\xc2\xae\ntest\xc2\xae'),
                  ('nouconverter:string:utf8', 'test\xc2\xae'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(
            formkeys,
            ['nouconverter', 'ulines', 'ustring', 'utext', 'utokens'])

        self.assertEqual(req['ustring'], u'test\u00AE')
        self.assertEqual(req['utext'], u'test\u00AE\ntest\u00AE\n')
        self.assertEqual(req['utokens'], [u'test\u00AE', u'test\u00AE'])
        self.assertEqual(req['ulines'], [u'test\u00AE', u'test\u00AE'])

        # expect a utf-8 encoded version
        self.assertEqual(req['nouconverter'], 'test\xc2\xae')

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_simple_containers(self):
        inputs = (
            ('oneitem:list', 'one'),
            ('alist:list', 'one'), ('alist:list', 'two'),
            ('oneitemtuple:tuple', 'one'),
            ('atuple:tuple', 'one'), ('atuple:tuple', 'two'),
            ('onerec.foo:record', 'foo'), ('onerec.bar:record', 'bar'),
            ('setrec.foo:records', 'foo'), ('setrec.bar:records', 'bar'),
            ('setrec.foo:records', 'spam'), ('setrec.bar:records', 'eggs'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(
            formkeys,
            ['alist', 'atuple', 'oneitem', 'oneitemtuple', 'onerec', 'setrec'])

        self.assertEqual(req['oneitem'], ['one'])
        self.assertEqual(req['oneitemtuple'], ('one',))
        self.assertEqual(req['alist'], ['one', 'two'])
        self.assertEqual(req['atuple'], ('one', 'two'))
        self.assertEqual(req['onerec'].foo, 'foo')
        self.assertEqual(req['onerec'].bar, 'bar')
        self.assertEqual(len(req['setrec']), 2)
        self.assertEqual(req['setrec'][0].foo, 'foo')
        self.assertEqual(req['setrec'][0].bar, 'bar')
        self.assertEqual(req['setrec'][1].foo, 'spam')
        self.assertEqual(req['setrec'][1].bar, 'eggs')

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_marshalling_into_sequences(self):
        inputs = (
            ('ilist:int:list', '1'), ('ilist:int:list', '2'),
            ('ilist:list:int', '3'),
            ('ftuple:float:tuple', '1.0'), ('ftuple:float:tuple', '1.1'),
            ('ftuple:tuple:float', '1.2'),
            ('tlist:tokens:list', 'one two'), ('tlist:list:tokens', '3 4'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(formkeys, ['ftuple', 'ilist', 'tlist'])

        self.assertEqual(req['ilist'], [1, 2, 3])
        self.assertEqual(req['ftuple'], (1.0, 1.1, 1.2))
        self.assertEqual(req['tlist'], [['one', 'two'], ['3', '4']])

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_records_w_sequences(self):
        inputs = (
            ('onerec.name:record', 'foo'),
            ('onerec.tokens:tokens:record', 'one two'),
            ('onerec.ints:int:record', '1'),
            ('onerec.ints:int:record', '2'),

            ('setrec.name:records', 'first'),
            ('setrec.ilist:list:int:records', '1'),
            ('setrec.ilist:list:int:records', '2'),
            ('setrec.ituple:tuple:int:records', '1'),
            ('setrec.ituple:tuple:int:records', '2'),
            ('setrec.name:records', 'second'),
            ('setrec.ilist:list:int:records', '1'),
            ('setrec.ilist:list:int:records', '2'),
            ('setrec.ituple:tuple:int:records', '1'),
            ('setrec.ituple:tuple:int:records', '2'))
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(formkeys, ['onerec', 'setrec'])

        self.assertEqual(req['onerec'].name, 'foo')
        self.assertEqual(req['onerec'].tokens, ['one', 'two'])
        # Implicit sequences and records don't mix.
        self.assertEqual(req['onerec'].ints, 2)

        self.assertEqual(len(req['setrec']), 2)
        self.assertEqual(req['setrec'][0].name, 'first')
        self.assertEqual(req['setrec'][1].name, 'second')

        for i in range(2):
            self.assertEqual(req['setrec'][i].ilist, [1, 2])
            self.assertEqual(req['setrec'][i].ituple, (1, 2))

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_defaults(self):
        inputs = (
            ('foo:default:int', '5'),

            ('alist:int:default', '3'),
            ('alist:int:default', '4'),
            ('alist:int:default', '5'),
            ('alist:int', '1'),
            ('alist:int', '2'),

            ('explicitlist:int:list:default', '3'),
            ('explicitlist:int:list:default', '4'),
            ('explicitlist:int:list:default', '5'),
            ('explicitlist:int:list', '1'),
            ('explicitlist:int:list', '2'),

            ('bar.spam:record:default', 'eggs'),
            ('bar.foo:record:default', 'foo'),
            ('bar.foo:record', 'baz'),

            ('setrec.spam:records:default', 'eggs'),
            ('setrec.foo:records:default', 'foo'),
            ('setrec.foo:records', 'baz'),
            ('setrec.foo:records', 'ham'),
        )
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(
            formkeys, ['alist', 'bar', 'explicitlist', 'foo', 'setrec'])

        self.assertEqual(req['alist'], [1, 2, 3, 4, 5])
        self.assertEqual(req['explicitlist'], [1, 2, 3, 4, 5])

        self.assertEqual(req['foo'], 5)
        self.assertEqual(req['bar'].spam, 'eggs')
        self.assertEqual(req['bar'].foo, 'baz')

        self.assertEqual(len(req['setrec']), 2)
        self.assertEqual(req['setrec'][0].spam, 'eggs')
        self.assertEqual(req['setrec'][0].foo, 'baz')
        self.assertEqual(req['setrec'][1].spam, 'eggs')
        self.assertEqual(req['setrec'][1].foo, 'ham')

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_wo_marshalling_w_Taints(self):
        inputs = (
            ('foo', 'bar'), ('spam', 'eggs'),
            ('number', '1'),
            ('tainted', '<tainted value>'),
            ('<tainted key>', 'value'),
            ('spacey key', 'val'), ('key', 'spacey val'),
            ('tinitmulti', '<1>'), ('tinitmulti', '2'),
            ('tdefermulti', '1'), ('tdefermulti', '<2>'),
            ('tallmulti', '<1>'), ('tallmulti', '<2>'))
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['<tainted key>', 'tainted',
             'tallmulti', 'tdefermulti', 'tinitmulti'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_simple_marshalling_w_taints(self):
        inputs = (
            ('<tnum>:int', '42'), ('<tfract>:float', '4.2'),
            ('<tbign>:long', '45'),
            ('twords:string', 'Some <words>'),
            ('t2tokens:tokens', 'one <two>'),
            ('<taday>:date', '2002/07/23'),
            ('taccountedfor:required', '<yes>'),
            ('tmultiline:lines', '<one\ntwo>'),
            ('tmorewords:text', '<one\ntwo>\n'))
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['<taday>', '<tbign>', '<tfract>',
             '<tnum>', 't2tokens', 'taccountedfor', 'tmorewords', 'tmultiline',
             'twords'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_unicode_w_taints(self):
        inputs = (
            ('tustring:ustring:utf8', '<test\xc2\xae>'),
            ('tutext:utext:utf8', '<test\xc2\xae>\n<test\xc2\xae\n>'),

            ('tinitutokens:utokens:utf8', '<test\xc2\xae> test\xc2\xae'),
            ('tinitulines:ulines:utf8', '<test\xc2\xae>\ntest\xc2\xae'),

            ('tdeferutokens:utokens:utf8', 'test\xc2\xae <test\xc2\xae>'),
            ('tdeferulines:ulines:utf8', 'test\xc2\xae\n<test\xc2\xae>'),

            ('tnouconverter:string:utf8', '<test\xc2\xae>'),
        )
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['tdeferulines', 'tdeferutokens',
             'tinitulines', 'tinitutokens', 'tnouconverter', 'tustring',
             'tutext'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_simple_containers_w_taints(self):
        inputs = (
            ('toneitem:list', '<one>'),
            ('<tkeyoneitem>:list', 'one'),
            ('tinitalist:list', '<one>'), ('tinitalist:list', 'two'),
            ('tdeferalist:list', 'one'), ('tdeferalist:list', '<two>'),

            ('toneitemtuple:tuple', '<one>'),
            ('tinitatuple:tuple', '<one>'), ('tinitatuple:tuple', 'two'),
            ('tdeferatuple:tuple', 'one'), ('tdeferatuple:tuple', '<two>'),

            ('tinitonerec.foo:record', '<foo>'),
            ('tinitonerec.bar:record', 'bar'),
            ('tdeferonerec.foo:record', 'foo'),
            ('tdeferonerec.bar:record', '<bar>'),

            ('tinitinitsetrec.foo:records', '<foo>'),
            ('tinitinitsetrec.bar:records', 'bar'),
            ('tinitinitsetrec.foo:records', 'spam'),
            ('tinitinitsetrec.bar:records', 'eggs'),

            ('tinitdefersetrec.foo:records', 'foo'),
            ('tinitdefersetrec.bar:records', '<bar>'),
            ('tinitdefersetrec.foo:records', 'spam'),
            ('tinitdefersetrec.bar:records', 'eggs'),

            ('tdeferinitsetrec.foo:records', 'foo'),
            ('tdeferinitsetrec.bar:records', 'bar'),
            ('tdeferinitsetrec.foo:records', '<spam>'),
            ('tdeferinitsetrec.bar:records', 'eggs'),

            ('tdeferdefersetrec.foo:records', 'foo'),
            ('tdeferdefersetrec.bar:records', 'bar'),
            ('tdeferdefersetrec.foo:records', 'spam'),
            ('tdeferdefersetrec.bar:records', '<eggs>'))
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['<tkeyoneitem>', 'tdeferalist',
             'tdeferatuple', 'tdeferdefersetrec', 'tdeferinitsetrec',
             'tdeferonerec', 'tinitalist', 'tinitatuple', 'tinitdefersetrec',
             'tinitinitsetrec', 'tinitonerec', 'toneitem', 'toneitemtuple'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_records_w_sequences_tainted(self):
        inputs = (
            ('tinitonerec.tokens:tokens:record', '<one> two'),
            ('tdeferonerec.tokens:tokens:record', 'one <two>'),

            ('tinitsetrec.name:records', 'first'),
            ('tinitsetrec.ilist:list:records', '<1>'),
            ('tinitsetrec.ilist:list:records', '2'),
            ('tinitsetrec.ituple:tuple:int:records', '1'),
            ('tinitsetrec.ituple:tuple:int:records', '2'),
            ('tinitsetrec.name:records', 'second'),
            ('tinitsetrec.ilist:list:records', '1'),
            ('tinitsetrec.ilist:list:records', '2'),
            ('tinitsetrec.ituple:tuple:int:records', '1'),
            ('tinitsetrec.ituple:tuple:int:records', '2'),

            ('tdeferfirstsetrec.name:records', 'first'),
            ('tdeferfirstsetrec.ilist:list:records', '1'),
            ('tdeferfirstsetrec.ilist:list:records', '<2>'),
            ('tdeferfirstsetrec.ituple:tuple:int:records', '1'),
            ('tdeferfirstsetrec.ituple:tuple:int:records', '2'),
            ('tdeferfirstsetrec.name:records', 'second'),
            ('tdeferfirstsetrec.ilist:list:records', '1'),
            ('tdeferfirstsetrec.ilist:list:records', '2'),
            ('tdeferfirstsetrec.ituple:tuple:int:records', '1'),
            ('tdeferfirstsetrec.ituple:tuple:int:records', '2'),

            ('tdefersecondsetrec.name:records', 'first'),
            ('tdefersecondsetrec.ilist:list:records', '1'),
            ('tdefersecondsetrec.ilist:list:records', '2'),
            ('tdefersecondsetrec.ituple:tuple:int:records', '1'),
            ('tdefersecondsetrec.ituple:tuple:int:records', '2'),
            ('tdefersecondsetrec.name:records', 'second'),
            ('tdefersecondsetrec.ilist:list:records', '1'),
            ('tdefersecondsetrec.ilist:list:records', '<2>'),
            ('tdefersecondsetrec.ituple:tuple:int:records', '1'),
            ('tdefersecondsetrec.ituple:tuple:int:records', '2'),
        )
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['tdeferfirstsetrec', 'tdeferonerec',
             'tdefersecondsetrec', 'tinitonerec', 'tinitsetrec'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_defaults_w_taints(self):
        inputs = (
            ('tfoo:default', '<5>'),

            ('doesnnotapply:default', '<4>'),
            ('doesnnotapply', '4'),

            ('tinitlist:default', '3'),
            ('tinitlist:default', '4'),
            ('tinitlist:default', '5'),
            ('tinitlist', '<1>'),
            ('tinitlist', '2'),

            ('tdeferlist:default', '3'),
            ('tdeferlist:default', '<4>'),
            ('tdeferlist:default', '5'),
            ('tdeferlist', '1'),
            ('tdeferlist', '2'),

            ('tinitbar.spam:record:default', 'eggs'),
            ('tinitbar.foo:record:default', 'foo'),
            ('tinitbar.foo:record', '<baz>'),
            ('tdeferbar.spam:record:default', '<eggs>'),
            ('tdeferbar.foo:record:default', 'foo'),
            ('tdeferbar.foo:record', 'baz'),

            ('rdoesnotapply.spam:record:default', '<eggs>'),
            ('rdoesnotapply.spam:record', 'eggs'),

            ('tinitsetrec.spam:records:default', 'eggs'),
            ('tinitsetrec.foo:records:default', 'foo'),
            ('tinitsetrec.foo:records', '<baz>'),
            ('tinitsetrec.foo:records', 'ham'),

            ('tdefersetrec.spam:records:default', '<eggs>'),
            ('tdefersetrec.foo:records:default', 'foo'),
            ('tdefersetrec.foo:records', 'baz'),
            ('tdefersetrec.foo:records', 'ham'),

            ('srdoesnotapply.foo:records:default', '<eggs>'),
            ('srdoesnotapply.foo:records', 'baz'),
            ('srdoesnotapply.foo:records', 'ham'))
        req = self._processInputs(inputs)

        taintedformkeys = list(req.taintedform.keys())
        taintedformkeys.sort()
        self.assertEqual(
            taintedformkeys,
            ['tdeferbar', 'tdeferlist',
             'tdefersetrec', 'tfoo', 'tinitbar', 'tinitlist', 'tinitsetrec'])

        self._taintedKeysAlsoInForm(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_tainted_attribute_raises(self):
        input = ('taintedattr.here<be<taint:record', 'value',)

        self.assertRaises(ValueError, self._processInputs, input)

    def test_processInputs_w_tainted_values_cleans_exceptions(self):
        # Feed tainted garbage to the conversion methods, and any exception
        # returned should be HTML safe
        from DateTime.interfaces import SyntaxError
        from ZPublisher.Converters import type_converters
        for type, convert in list(type_converters.items()):
            try:
                convert('<html garbage>')
            except Exception as e:
                self.assertFalse(
                    '<' in e.args,
                    '%s converter does not quote unsafe value!' % type)
            except SyntaxError as e:
                self.assertFalse(
                    '<' in e,
                    '%s converter does not quote unsafe value!' % type)

    def test_processInputs_w_dotted_name_as_tuple(self):
        # Collector #500
        inputs = (
            ('name.:tuple', 'name with dot as tuple'),)
        req = self._processInputs(inputs)

        formkeys = list(req.form.keys())
        formkeys.sort()
        self.assertEqual(formkeys, ['name.'])

        self.assertEqual(req['name.'], ('name with dot as tuple',))

        self._noTaintedValues(req)
        self._onlyTaintedformHoldsTaintedStrings(req)

    def test_processInputs_w_cookie_parsing(self):
        env = {'SERVER_NAME': 'testingharnas', 'SERVER_PORT': '80'}

        env['HTTP_COOKIE'] = 'foo=bar; baz=gee'
        req = self._makeOne(environ=env)
        self.assertEqual(req.cookies['foo'], 'bar')
        self.assertEqual(req.cookies['baz'], 'gee')

        env['HTTP_COOKIE'] = 'foo=bar; baz="gee, like, e=mc^2"'
        req = self._makeOne(environ=env)
        self.assertEqual(req.cookies['foo'], 'bar')
        self.assertEqual(req.cookies['baz'], 'gee, like, e=mc^2')

        # Collector #1498: empty cookies
        env['HTTP_COOKIE'] = 'foo=bar; hmm; baz=gee'
        req = self._makeOne(environ=env)
        self.assertEqual(req.cookies['foo'], 'bar')
        self.assertEqual(req.cookies['hmm'], '')
        self.assertEqual(req.cookies['baz'], 'gee')

        # Unquoted multi-space cookies
        env['HTTP_COOKIE'] = 'single=cookie data; ' \
                             'quoted="cookie data with unquoted spaces"; ' \
                             'multi=cookie data with unquoted spaces; ' \
                             'multi2=cookie data with unquoted spaces'
        req = self._makeOne(environ=env)
        self.assertEqual(req.cookies['single'], 'cookie data')
        self.assertEqual(req.cookies['quoted'],
                         'cookie data with unquoted spaces')
        self.assertEqual(req.cookies['multi'],
                         'cookie data with unquoted spaces')
        self.assertEqual(req.cookies['multi2'],
                         'cookie data with unquoted spaces')

    def test_postProcessInputs(self):
        from ZPublisher.HTTPRequest import default_encoding

        _NON_ASCII = u'\xc4\xd6\xdc'
        req = self._makeOne()
        req.form = {'foo': _NON_ASCII.encode(default_encoding),
                    'foo_list': [_NON_ASCII.encode(default_encoding), 'SPAM'],
                    'foo_tuple': (_NON_ASCII.encode(default_encoding), 'HAM'),
                    'foo_dict': {'foo': _NON_ASCII, 'bar': 'EGGS'}}
        req.postProcessInputs()
        self.assertTrue(isinstance(req.form['foo'], unicode))
        self.assertEqual(req.form['foo'], _NON_ASCII)
        self.assertTrue(isinstance(req.form['foo_list'], list))
        self.assertTrue(isinstance(req.form['foo_list'][0], unicode))
        self.assertEqual(req.form['foo_list'][0], _NON_ASCII)
        self.assertTrue(isinstance(req.form['foo_list'][1], unicode))
        self.assertEqual(req.form['foo_list'][1], u'SPAM')
        self.assertTrue(isinstance(req.form['foo_tuple'], tuple))
        self.assertTrue(isinstance(req.form['foo_tuple'][0], unicode))
        self.assertEqual(req.form['foo_tuple'][0], _NON_ASCII)
        self.assertTrue(isinstance(req.form['foo_tuple'][1], unicode))
        self.assertEqual(req.form['foo_tuple'][1], u'HAM')
        self.assertTrue(isinstance(req.form['foo_dict'], dict))
        self.assertTrue(isinstance(req.form['foo_dict']['foo'], unicode))
        self.assertEqual(req.form['foo_dict']['foo'], _NON_ASCII)
        self.assertTrue(isinstance(req.form['foo_dict']['bar'], unicode))
        self.assertEqual(req.form['foo_dict']['bar'], u'EGGS')

    def test_close_removes_stdin_references(self):
        # Verifies that all references to the input stream go away on
        # request.close().  Otherwise a tempfile may stick around.
        s = BytesIO(TEST_FILE_DATA)
        start_count = sys.getrefcount(s)

        req = self._makeOne(stdin=s, environ=TEST_ENVIRON.copy())
        req.processInputs()
        self.assertNotEqual(start_count, sys.getrefcount(s))  # Precondition
        req.close()
        self.assertEqual(start_count, sys.getrefcount(s))  # The test

    def test_processInputs_w_large_input_gets_tempfile(self):
        # checks fileupload object supports the filename
        s = BytesIO(TEST_LARGEFILE_DATA)

        req = self._makeOne(stdin=s, environ=TEST_ENVIRON.copy())
        req.processInputs()
        f = req.form.get('file')
        self.assertTrue(f.name)

    def test_processInputs_with_file_upload_gets_iterator(self):
        # checks fileupload object supports the iterator protocol
        # collector entry 1837
        s = BytesIO(TEST_FILE_DATA)

        req = self._makeOne(stdin=s, environ=TEST_ENVIRON.copy())
        req.processInputs()
        f = req.form.get('file')
        self.assertEqual(list(f), ['test\n'])
        f.seek(0)
        self.assertEqual(next(f), 'test\n')

    def test__authUserPW_simple(self):
        user_id = 'user'
        password = 'password'
        encoded = base64.encodestring('%s:%s' % (user_id, password))
        auth_header = 'basic %s' % encoded

        environ = {'HTTP_AUTHORIZATION': auth_header}
        request = self._makeOne(environ=environ)

        user_id_x, password_x = request._authUserPW()

        self.assertEqual(user_id_x, user_id)
        self.assertEqual(password_x, password)

    def test__authUserPW_with_embedded_colon(self):
        # http://www.zope.org/Collectors/Zope/2039
        user_id = 'user'
        password = 'embedded:colon'
        encoded = base64.encodestring('%s:%s' % (user_id, password))
        auth_header = 'basic %s' % encoded

        environ = {'HTTP_AUTHORIZATION': auth_header}
        request = self._makeOne(environ=environ)

        user_id_x, password_x = request._authUserPW()

        self.assertEqual(user_id_x, user_id)
        self.assertEqual(password_x, password)

    def test_debug_not_in_qs_still_gets_attr(self):
        from zope.publisher.base import DebugFlags
        # when accessing request.debug we will see the DebugFlags instance
        request = self._makeOne()
        self.assertTrue(isinstance(request.debug, DebugFlags))
        # It won't be available through dictonary lookup, though
        self.assertTrue(request.get('debug') is None)

    def test_debug_in_qs_gets_form_var(self):
        env = {'QUERY_STRING': 'debug=1'}

        # request.debug will actually yield a 'debug' form variable
        # if it exists
        request = self._makeOne(environ=env)
        request.processInputs()
        self.assertEqual(request.debug, '1')
        self.assertEqual(request.get('debug'), '1')
        self.assertEqual(request['debug'], '1')

        # we can still override request.debug with a form variable or directly

    def test_debug_override_via_form_other(self):
        request = self._makeOne()
        request.processInputs()
        request.form['debug'] = '1'
        self.assertEqual(request.debug, '1')
        request['debug'] = '2'
        self.assertEqual(request.debug, '2')

    def test_locale_property_accessor(self):
        from ZPublisher.HTTPRequest import _marker

        provideAdapter(BrowserLanguages, [IHTTPRequest],
                       IUserPreferredLanguages)

        env = {'HTTP_ACCEPT_LANGUAGE': 'en'}
        request = self._makeOne(environ=env)

        # before accessing request.locale for the first time, request._locale
        # is still a marker
        self.assertTrue(request._locale is _marker)

        # when accessing request.locale we will see an ILocale
        self.assertTrue(ILocale.providedBy(request.locale))

        # and request._locale has been set
        self.assertTrue(request._locale is request.locale)

        # It won't be available through dictonary lookup, though
        self.assertTrue(request.get('locale') is None)

    def test_locale_in_qs(self):
        provideAdapter(BrowserLanguages, [IHTTPRequest],
                       IUserPreferredLanguages)

        # request.locale will actually yield a 'locale' form variable
        # if it exists
        env = {'HTTP_ACCEPT_LANGUAGE': 'en', 'QUERY_STRING': 'locale=1'}
        request = self._makeOne(environ=env)
        request.processInputs()

        self.assertEqual(request.locale, '1')
        self.assertEqual(request.get('locale'), '1')
        self.assertEqual(request['locale'], '1')

    def test_locale_property_override_via_form_other(self):
        provideAdapter(BrowserLanguages, [IHTTPRequest],
                       IUserPreferredLanguages)
        env = {'HTTP_ACCEPT_LANGUAGE': 'en'}

        # we can still override request.locale with a form variable
        request = self._makeOne(environ=env)
        request.processInputs()

        self.assertTrue(ILocale.providedBy(request.locale))

        request.form['locale'] = '1'
        self.assertEqual(request.locale, '1')

        request['locale'] = '2'
        self.assertEqual(request.locale, '2')

    def test_locale_semantics(self):
        provideAdapter(BrowserLanguages, [IHTTPRequest],
                       IUserPreferredLanguages)
        env_ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

        # we should also test the correct semantics of the locale
        for httplang in ('it', 'it-ch', 'it-CH', 'IT', 'IT-CH', 'IT-ch'):
            env = env_.copy()
            env['HTTP_ACCEPT_LANGUAGE'] = httplang
            request = self._makeOne(environ=env)
            locale = request.locale
            self.assertTrue(ILocale.providedBy(locale))
            parts = httplang.split('-')
            lang = parts.pop(0).lower()
            territory = variant = None
            if parts:
                territory = parts.pop(0).upper()
            if parts:
                variant = parts.pop(0).upper()
            self.assertEqual(locale.id.language, lang)
            self.assertEqual(locale.id.territory, territory)
            self.assertEqual(locale.id.variant, variant)

    def test_locale_fallback(self):
        provideAdapter(BrowserLanguages, [IHTTPRequest],
                       IUserPreferredLanguages)

        env = {'HTTP_ACCEPT_LANGUAGE': 'en', 'HTTP_ACCEPT_LANGUAGE': 'xx'}

        # Now test for non-existant locale fallback
        request = self._makeOne(environ=env)
        locale = request.locale

        self.assertTrue(ILocale.providedBy(locale))
        self.assertTrue(locale.id.language is None)
        self.assertTrue(locale.id.territory is None)
        self.assertTrue(locale.id.variant is None)

    def test_method_GET(self):
        env = {'REQUEST_METHOD': 'GET'}
        request = self._makeOne(environ=env)
        self.assertEqual(request.method, 'GET')

    def test_method_POST(self):
        env = {'REQUEST_METHOD': 'POST'}
        request = self._makeOne(environ=env)
        self.assertEqual(request.method, 'POST')

    def test_getClientAddr_wo_trusted_proxy(self):
        env = {'REMOTE_ADDR': '127.0.0.1',
               'HTTP_X_FORWARDED_FOR': '10.1.20.30, 192.168.1.100'}
        request = self._makeOne(environ=env)
        self.assertEqual(request.getClientAddr(), '127.0.0.1')

    def test_getClientAddr_one_trusted_proxy(self):
        from ZPublisher.HTTPRequest import trusted_proxies
        env = {'REMOTE_ADDR': '127.0.0.1',
               'HTTP_X_FORWARDED_FOR': '10.1.20.30, 192.168.1.100'}

        orig = trusted_proxies[:]
        try:
            trusted_proxies.append('127.0.0.1')
            request = self._makeOne(environ=env)
            self.assertEqual(request.getClientAddr(), '192.168.1.100')
        finally:
            trusted_proxies[:] = orig

    def test_getClientAddr_trusted_proxy_last(self):
        from ZPublisher.HTTPRequest import trusted_proxies
        env = {'REMOTE_ADDR': '192.168.1.100',
               'HTTP_X_FORWARDED_FOR': '10.1.20.30, 192.168.1.100'}

        orig = trusted_proxies[:]
        try:
            trusted_proxies.append('192.168.1.100')
            request = self._makeOne(environ=env)
            self.assertEqual(request.getClientAddr(), '10.1.20.30')
        finally:
            trusted_proxies[:] = orig

    def test_getClientAddr_trusted_proxy_no_REMOTE_ADDR(self):
        from ZPublisher.HTTPRequest import trusted_proxies
        env = {'HTTP_X_FORWARDED_FOR': '10.1.20.30, 192.168.1.100'}

        orig = trusted_proxies[:]
        try:
            trusted_proxies.append('192.168.1.100')
            request = self._makeOne(environ=env)
            self.assertEqual(request.getClientAddr(), '')
        finally:
            trusted_proxies[:] = orig

    def test_getHeader_exact(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('content-type'),
                         'multipart/form-data; boundary=12345')

    def test_getHeader_case_insensitive(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('Content-Type'),
                         'multipart/form-data; boundary=12345')

    def test_getHeader_underscore_is_dash(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('content_type'),
                         'multipart/form-data; boundary=12345')

    def test_getHeader_literal_turns_off_case_normalization(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('Content-Type', literal=True), None)

    def test_getHeader_nonesuch(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('none-such'), None)

    def test_getHeader_nonesuch_with_default(self):
        request = self._makeOne(environ=TEST_ENVIRON.copy())
        self.assertEqual(request.getHeader('Not-existant', default='Whatever'),
                         'Whatever')

    def test_clone_updates_method_to_GET(self):
        request = self._makeOne(environ={'REQUEST_METHOD': 'POST'})
        request['PARENTS'] = [object()]
        clone = request.clone()
        self.assertEqual(clone.method, 'GET')

    def test_clone_keeps_preserves__auth(self):
        request = self._makeOne()
        request['PARENTS'] = [object()]
        request._auth = 'foobar'
        clone = request.clone()
        self.assertEqual(clone._auth, 'foobar')

    def test_clone_doesnt_re_clean_environ(self):
        request = self._makeOne()
        request.environ['HTTP_CGI_AUTHORIZATION'] = 'lalalala'
        request['PARENTS'] = [object()]
        clone = request.clone()
        self.assertEqual(clone.environ['HTTP_CGI_AUTHORIZATION'], 'lalalala')

    def test_clone_keeps_only_last_PARENT(self):
        PARENTS = [object(), object()]
        request = self._makeOne()
        request['PARENTS'] = PARENTS
        clone = request.clone()
        self.assertEqual(clone['PARENTS'], PARENTS[1:])

    def test_clone_preserves_response_class(self):
        class DummyResponse:
            pass
        request = self._makeOne(None, TEST_ENVIRON.copy(), DummyResponse())
        request['PARENTS'] = [object()]
        clone = request.clone()
        self.assertTrue(isinstance(clone.response, DummyResponse))

    def test_clone_preserves_request_subclass(self):
        class SubRequest(self._getTargetClass()):
            pass
        request = SubRequest(None, TEST_ENVIRON.copy(), None)
        request['PARENTS'] = [object()]
        clone = request.clone()
        self.assertTrue(isinstance(clone, SubRequest))

    def test_clone_preserves_direct_interfaces(self):
        from zope.interface import directlyProvides
        from zope.interface import Interface

        class IFoo(Interface):
            pass
        request = self._makeOne()
        request['PARENTS'] = [object()]
        directlyProvides(request, IFoo)
        clone = request.clone()
        self.assertTrue(IFoo.providedBy(clone))

    def test_resolve_url_doesnt_send_endrequestevent(self):
        import zope.event
        events = []
        zope.event.subscribers.append(events.append)
        request = self._makeOne()
        request['PARENTS'] = [object()]
        try:
            request.resolve_url(request.script + '/')
        finally:
            zope.event.subscribers.remove(events.append)
        self.assertFalse(
            len(events),
            "HTTPRequest.resolve_url should not emit events")

    def test_resolve_url_errorhandling(self):
        # Check that resolve_url really raises the same error
        # it received from ZPublisher.BaseRequest.traverse
        request = self._makeOne()
        request['PARENTS'] = [object()]
        self.assertRaises(
            NotFound, request.resolve_url, request.script + '/does_not_exist')

    def test_parses_json_cookies(self):
        # https://bugs.launchpad.net/zope2/+bug/563229
        # reports cookies in the wild with embedded double quotes (e.g,
        # JSON-encoded data structures.
        env = {
            'SERVER_NAME': 'testingharnas',
            'SERVER_PORT': '80',
            'HTTP_COOKIE': 'json={"intkey":123,"stringkey":"blah"}; '
                           'anothercookie=boring; baz'
        }
        req = self._makeOne(environ=env)
        self.assertEqual(req.cookies['json'],
                         '{"intkey":123,"stringkey":"blah"}')
        self.assertEqual(req.cookies['anothercookie'], 'boring')

    def test_getVirtualRoot(self):
        # https://bugs.launchpad.net/zope2/+bug/193122
        req = self._makeOne()

        req._script = []
        self.assertEqual(req.getVirtualRoot(), '')

        req._script = ['foo', 'bar']
        self.assertEqual(req.getVirtualRoot(), '/foo/bar')


class TestHTTPRequestZope3Views(TestRequestViewsBase):

    def _makeOne(self, root):
        from zope.interface import directlyProvides
        from zope.publisher.browser import IDefaultBrowserLayer
        request = HTTPRequestFactoryMixin()._makeOne()
        request['PARENTS'] = [root]
        # The request needs to implement the proper interface
        directlyProvides(request, IDefaultBrowserLayer)
        return request

    def test_no_traversal_of_view_request_attribute(self):
        # make sure views don't accidentally publish the 'request' attribute
        root, _ = self._makeRootAndFolder()

        # make sure the view itself is traversable:
        view = self._makeOne(root).traverse('folder/@@meth')
        from ZPublisher.HTTPRequest import HTTPRequest
        self.assertEqual(view.request.__class__, HTTPRequest,)

        # but not the request:
        self.assertRaises(
            NotFound,
            self._makeOne(root).traverse, 'folder/@@meth/request'
        )

TEST_ENVIRON = {
    'CONTENT_TYPE': 'multipart/form-data; boundary=12345',
    'REQUEST_METHOD': 'POST',
    'SERVER_NAME': 'localhost',
    'SERVER_PORT': '80',
}

TEST_FILE_DATA = '''
--12345
Content-Disposition: form-data; name="file"; filename="file"
Content-Type: application/octet-stream

test

--12345--
'''

TEST_LARGEFILE_DATA = '''
--12345
Content-Disposition: form-data; name="file"; filename="file"
Content-Type: application/octet-stream

test %s

''' % ('test' * 1000)
