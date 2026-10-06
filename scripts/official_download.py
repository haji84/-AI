"""Standard-library-only origin guard shared by acquisition collectors."""
import urllib.request
from urllib.parse import urljoin,urlsplit


def validate_origin(url,hosts):
    parsed=urlsplit(url)
    if not parsed.hostname or parsed.scheme!='https' or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in {None,443}:raise ValueError('official HTTPS retrieval origin refused')


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self,hosts):self.hosts=set(hosts)
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_origin(urljoin(req.full_url,newurl),self.hosts)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def open_official(request,*,timeout):
    hosts={urlsplit(request.full_url).hostname};validate_origin(request.full_url,hosts)
    opener=urllib.request.build_opener(OfficialRedirectHandler(hosts))
    response=opener.open(request,timeout=timeout)
    try:validate_origin(response.geturl(),hosts)
    except Exception:
        response.close();raise
    return response
