
# encoding: utf-8
import json
import oauth.oauth as oauth
import requests
import subprocess
import uuid

from urlparse import urlparse

MAAS_HOST = '127.0.0.1'
MAAS_USER = 'root'
SHELL_USER = 'ubuntu'


class MaasBaseClient(object):
    def __init__(self, api_url=None, token=None,
                 host=None, user=None,
                 shell_user=None):
        if not api_url:
            if not host:
                host = MAAS_HOST
        if not token:
            if not user:
                user = MAAS_USER
            if not shell_user:
                shell_user = SHELL_USER
        if not api_url:
            api_url = 'http://%s:5240/MAAS/api/1.0' % host
        if not host:
            host = urlparse(api_url).hostname
        if not token:
            token = self._get_token(host, user, shell_user)
        dissected_api_url = urlparse(api_url)
        self._token = token
        self._api_url = api_url
        self._base_url = '{0}://{1}'.format(dissected_api_url.scheme,
                                            dissected_api_url.netloc)

    def _auth(self):
        consumer_key, key, secret = self._token.split(':')
        resource_token = oauth.OAuthToken(key, secret)
        consumer_token = oauth.OAuthConsumer(consumer_key, '')
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            consumer_token,
            token=resource_token,
            http_url=self._api_url,
            parameters={
                'auth_nonce': uuid.uuid4().get_hex(),
            }
        )
        oauth_request.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
                                   consumer_token,
                                   resource_token)
        return oauth_request.to_header()

    def _get_token(self, host, user, shell_user):
        cmd = [
            'ssh', '%s@%s' % (shell_user, host),
            'sudo', 'maas-region-admin', 'apikey',
            '--username=%s' % user
        ]
        return subprocess.check_output(cmd).strip()

    def nodes(self):
        url = '%s/nodes/?op=list' % self._api_url
        rq = requests.get(url, headers=self._auth())
        rq.raise_for_status()
        return json.loads(rq.text)

    def update_node(self, system_id, params=None):
        # note: trailing slash is mandatory
        url = '%s/nodes/%s/' % (self._api_url, system_id)
        rq = requests.put(url, data=params, headers=self._auth())
        rq.raise_for_status()
