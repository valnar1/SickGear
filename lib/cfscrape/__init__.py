from base64 import b64encode, b64decode

from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from requests.models import Response
from requests.sessions import Session
from urllib3.util.ssl_ import create_urllib3_context

import logging
import random
import re
import ssl
import time

import js2py

try:
    from urlparse import urlparse
    from urlparse import urlunparse
except ImportError:
    # noinspection PyCompatibility
    from urllib.parse import urlparse
    # noinspection PyCompatibility
    from urllib.parse import urlunparse

DEFAULT_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/41.0.2228.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/50.0.2661.102 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/52.0.2743.116 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:46.0)'
    ' Gecko/20100101 Firefox/46.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0)'
    ' Gecko/20100101 Firefox/41.0'
]


class CloudflareError(RequestException):
    pass


class CloudflareScraper(Session):
    def __init__(self, **kwargs):
        super(CloudflareScraper, self).__init__()

        if 'requests' in self.headers['User-Agent']:
            # Set a random User-Agent if no custom User-Agent has been set
            self.headers['User-Agent'] = random.choice(DEFAULT_USER_AGENTS)
        self.cf_ua = self.headers['User-Agent']

        self.default_delay = 8
        self.delay = kwargs.pop('delay', self.default_delay)
        self.start_time = None

        self.cipher_suite = self.load_cipher_suite()
        self.mount('https://', CloudflareAdapter(self.cipher_suite))

    def request(self, method, url, *args, **kwargs):
        resp = super(CloudflareScraper, self).request(method, url, *args, **kwargs)

        # Check if anti-bot is on
        if (isinstance(resp, type(Response()))
                and resp.status_code in (503, 429, 403)):
            self.start_time = time.time()
            if (re.search('(?i)cloudflare', resp.headers.get('Server', ''))
                    and 'jschl_vc' in resp.content
                    and 'jschl_answer' in resp.content):
                resp = self.solve_cf_challenge(resp, **kwargs)
            elif 'ddgu' in resp.content:
                resp = self.solve_ddg_challenge(resp, **kwargs)

        # Otherwise, no anti-bot detected
        return resp

    def wait(self):
        delay = self.delay - (time.time() - self.start_time)
        time.sleep((0, delay)[0 < delay])  # required delay before solving the challenge

    def solve_ddg_challenge(self, resp, **original_kwargs):
        parsed_url = urlparse(resp.url)
        try:
            submit_url = parsed_url.scheme + ':' + re.findall('"frm"[^>]+?action="([^"]+)"', resp.text)[0]
            kwargs = {k: v for k, v in original_kwargs.items() if k not in ['hooks']}
            kwargs.setdefault('headers', {})
            kwargs.setdefault('data', dict(
                h=b64encode('%s://%s' % (parsed_url.scheme, parsed_url.hostname)),
                u=b64encode(parsed_url.path), p=b64encode(parsed_url.port or '')
            ))
            self.wait()
            resp = self.request('POST', submit_url, **kwargs)
        except(Exception, BaseException):
            pass
        return resp

    def solve_cf_challenge(self, resp, **original_kwargs):
        body = resp.text
        parsed_url = urlparse(resp.url)
        domain = parsed_url.netloc

        if '/cdn-cgi/l/chk_captcha' in body:
            raise CloudflareError(
                'Cloudflare captcha presented for %s, please notify SickGear for an update, ua: %s' %
                (domain, self.cf_ua), response=resp)

        submit_url = '%s://%s/cdn-cgi/l/chk_jschl' % (parsed_url.scheme, domain)

        cloudflare_kwargs = {k: v for k, v in original_kwargs.items() if k not in ['hooks']}
        params = cloudflare_kwargs.setdefault('params', {})
        headers = cloudflare_kwargs.setdefault('headers', {})
        headers['Referer'] = resp.url

        if self.delay == self.default_delay:
            try:
                # no instantiated delay, therefore check js for hard coded CF delay
                self.delay = float(re.search(r'submit\(\);[^0-9]*?([0-9]+)', body).group(1)) / float(1000)
            except(Exception, BaseException):
                pass

        for i in re.findall(r'(<input[^>]+?hidden[^>]+?>)', body):
            value = re.findall(r'value="([^"\']+?)["\']', i)
            name = re.findall(r'name="([^"\']+?)["\']', i)
            if all([name, value]):
                params[name[0]] = value[0]

        js = self.extract_js(body, domain)
        atob = (lambda s: b64decode('%s' % s).decode('utf-8'))
        try:
            # Eval the challenge algorithm
            params['jschl_answer'] = str(js2py.EvalJs({'atob': atob}).eval(js))
        except(Exception, BaseException):
            try:
                params['jschl_answer'] = str(js2py.EvalJs({'atob': atob}).eval(js))
            except(Exception, BaseException) as e:
                # Something is wrong with the page. This may indicate Cloudflare has changed their anti-bot technique.
                raise ValueError('Unable to parse Cloudflare anti-bot IUAM page: %s' % e.message)

        # Requests transforms any request into a GET after a redirect,
        # so the redirect has to be handled manually here to allow for
        # performing other types of requests even as the first request.
        method = resp.request.method
        cloudflare_kwargs['allow_redirects'] = False

        self.wait()
        redirect = self.request(method, submit_url, **cloudflare_kwargs)

        location = redirect.headers.get('Location')
        r = urlparse(location)
        if not r.netloc:
            location = urlunparse((parsed_url.scheme, domain, r.path, r.params, r.query, r.fragment))
        return self.request(method, location, **original_kwargs)

    @staticmethod
    def extract_js(body, domain):
        try:
            js = re.search(
                r'''(?x)
                setTimeout\(function\(\){\s*?(var\s*?
                (?:s,t,o,p,b,r,e,a,k,i,n,g|t,r,a),f.+?[\r\n\s\S]*?a\.value\s*=.+?)[\r\n]+
                ''', body).group(1)
        except(Exception, BaseException):
            raise RuntimeError('Error #1 Cloudflare anti-bots changed, please notify SickGear for an update')

        if not re.search(r'(?i)(toFixed|t\.length)', js):
            raise RuntimeError('Error #2 Cloudflare anti-bots changed, please notify SickGear for an update')

        js = re.sub(r'(;\s+);', r'\1', js)
        js = re.sub(r'([)\]];)(\w)', r'\1\n\n\2', js)
        js = re.sub(r'\s*\';\s*\d+\'\s*$', '', js)

        innerHTML = re.search(r'(?sim)<div(?: [^<>]*)? id="([^<>]*?)">([^<>]*?)</div>', body)
        innerHTML = '' if not innerHTML else innerHTML.group(2).strip()

        # Prefix the challenge with a fake document object.
        # Interpolate the domain, div contents, and JS challenge.
        # The `a.value` to be returned is tacked onto the end.
        return r'''
            var document = {
                createElement: function () {
                    return { firstChild: { href: 'https://%s/' } }
                },
                getElementById: function () {
                    return { innerHTML: '%s'};
                }
            };
            String.prototype.italics=function() {return '<i>' + this + '</i>';};
            %s;a.value
        ''' % (domain, innerHTML, js)

    @staticmethod
    def load_cipher_suite():

        suite = []
        if hasattr(ssl, 'PROTOCOL_TLS'):
            ctx = ssl.SSLContext(getattr(ssl, 'PROTOCOL_TLSv1_3', ssl.PROTOCOL_TLSv1_2))

            for cipher in (
                    ([], ['GREASE_3A', 'GREASE_6A', 'AES128-GCM-SHA256', 'AES256-GCM-SHA256', 'AES256-GCM-SHA384',
                          'CHACHA20-POLY1305-SHA256'])[hasattr(ssl, 'PROTOCOL_TLSv1_3')] +
                    ['ECDHE-ECDSA-AES128-GCM-SHA256', 'ECDHE-RSA-AES128-GCM-SHA256',
                     'ECDHE-ECDSA-AES256-GCM-SHA384',
                     'ECDHE-ECDSA-CHACHA20-POLY1305-SHA256', 'ECDHE-RSA-CHACHA20-POLY1305-SHA256',
                     'ECDHE-RSA-AES128-CBC-SHA', 'ECDHE-RSA-AES256-CBC-SHA', 'RSA-AES128-GCM-SHA256',
                     'RSA-AES256-GCM-SHA384', 'ECDHE-RSA-AES128-GCM-SHA256', 'RSA-AES256-SHA', '3DES-EDE-CBC']):
                try:
                    ctx.set_ciphers(cipher)
                    suite += [cipher]
                except ssl.SSLError:
                    pass

        return ':'.join(suite)

    @classmethod
    def create_scraper(cls, sess=None, **kwargs):
        """
        Convenience function for creating a ready-to-go CloudflareScraper object.
        """
        scraper = cls(**kwargs)

        if sess:
            attrs = ['auth', 'cert', 'cookies', 'headers', 'hooks', 'params', 'proxies', 'data']
            for attr in attrs:
                val = getattr(sess, attr, None)
                if val:
                    setattr(scraper, attr, val)

        return scraper

    # Functions for integrating cloudflare-scrape with other applications and scripts

    @classmethod
    def get_tokens(cls, url, user_agent=None, **kwargs):
        scraper = cls.create_scraper()
        if user_agent:
            scraper.headers['User-Agent'] = user_agent

        try:
            resp = scraper.get(url, **kwargs)
            resp.raise_for_status()
        except(Exception, BaseException):
            logging.error('[%s] returned an error. Could not collect tokens.' % url)
            raise

        domain = urlparse(resp.url).netloc

        for d in scraper.cookies.list_domains():
            if d.startswith('.') and d in ('.' + domain):
                cookie_domain = d
                break
        else:
            raise ValueError('Unable to find Cloudflare cookies.'
                             ' Does the site actually have Cloudflare IUAM (\'I\'m Under Attack Mode\') enabled?')

        return (
            {'__cfduid': scraper.cookies.get('__cfduid', '', domain=cookie_domain),
             'cf_clearance': scraper.cookies.get('cf_clearance', '', domain=cookie_domain)},
            scraper.headers['User-Agent'])

    @classmethod
    def get_cookie_string(cls, url, user_agent=None):
        """
        Convenience function for building a Cookie HTTP header value.
        """
        tokens, user_agent = cls.get_tokens(url, user_agent=user_agent, **kwargs)
        return '; '.join('='.join(pair) for pair in tokens.items()), user_agent


class CloudflareAdapter(HTTPAdapter):
    """
    HTTPS adapter that creates a SSL context with custom ciphers
    """
    def __init__(self, cipher_suite=None, **kwargs):
        self.cipher_suite = cipher_suite

        params = dict(ssl_version=ssl.PROTOCOL_TLSv1)
        if hasattr(ssl, 'PROTOCOL_TLS'):
            params = dict(ssl_version=getattr(ssl, 'PROTOCOL_TLSv1_3', ssl.PROTOCOL_TLSv1_2), ciphers=cipher_suite)
        self.ssl_context = create_urllib3_context(**params)

        super(CloudflareAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super(CloudflareAdapter, self).init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super(CloudflareAdapter, self).proxy_manager_for(*args, **kwargs)


create_scraper = CloudflareScraper.create_scraper
get_tokens = CloudflareScraper.get_tokens
get_cookie_string = CloudflareScraper.get_cookie_string